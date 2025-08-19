"""
pyclog.handler
~~~~~~~~~~~~~~

此模块提供 `ClogFileHandler` 类，这是一个 `logging.Handler` 的实现，
用于将 Python `logging` 模块生成的日志记录写入自定义的 .clog 文件格式。
"""

import logging
import os  
from datetime import datetime # 新增导入
from .writer import ClogWriter
from . import constants
from .exceptions import ClogWriteError
class ClogFileHandler(logging.Handler):
    """
    一个用于将日志记录写入 .clog 文件的 logging Handler。

    此处理程序将标准的 `logging.LogRecord` 对象转换为 `ClogWriter`
    可以处理的格式，并将其写入指定的 .clog 文件。它支持追加模式
    和不同的压缩算法，这些都由底层的 `ClogWriter` 处理。
    """
    def __init__(self, filename, mode='a', encoding=None, compression_code=constants.COMPRESSION_GZIP):
        """
        初始化 ClogFileHandler 实例。

        Args:
            filename (str): 要写入的 .clog 文件的路径。
            mode (str, optional): 文件打开模式。'w' 表示写入（覆盖现有文件），
                                  'a' 表示追加（如果文件存在，则追加到末尾）。
                                  默认为 'a'。
            encoding (str, optional): 此参数被忽略，因为 ClogWriter 内部强制使用 UTF-8 编码。
            compression_code (bytes, optional): 用于压缩日志数据的算法代码。
                                                支持 `constants.COMPRESSION_NONE` (无压缩),
                                                `constants.COMPRESSION_GZIP` (Gzip 压缩),
                                                `constants.COMPRESSION_ZSTANDARD` (Zstandard 压缩)。
                                                默认为 `constants.COMPRESSION_GZIP`。

        Raises:
            ClogWriteError: 如果无法初始化底层的 ClogWriter。
        """
        super().__init__()
        self.filename = filename
        self.mode = mode 
        self.encoding = encoding
        self.compression_code = compression_code
        self.clog_writer = None
        self._open_writer()

    def _open_writer(self):
        """
        初始化 ClogWriter 实例。

        此方法尝试创建并打开一个 `ClogWriter` 实例。如果失败，
        它会记录一个错误并确保 `clog_writer` 属性为 None。
        """
        try:
            self.clog_writer = ClogWriter(self.filename, self.mode, self.compression_code)
        except ClogWriteError as e:
            import sys
            ei = sys.exc_info()
            self.handleError(logging.LogRecord(self.name, logging.CRITICAL, __file__, 0, f"无法初始化 ClogWriter: {e}", None, ei))
            self.clog_writer = None

    def emit(self, record):
        """
        将格式化后的日志记录写入 .clog 文件。

        此方法是 `logging.Handler` 接口的核心部分。它使用处理程序的格式化器
        将 `LogRecord` 转换为字符串，然后通过 `ClogWriter` 写入文件。
        任何写入过程中发生的异常都会被捕获并传递给 `handleError`。

        Args:
            record (logging.LogRecord): 要处理的日志记录对象。
        """
        try:
            if self.clog_writer is None:
                self._open_writer()
            # 如果尝试后仍然不存在，则无法写入，直接返回
            if self.clog_writer is None:
                return

            # 使用 Handler 的 formatter 格式化记录
            msg = self.format(record)
            self.clog_writer.write_record(record.levelname, msg)
        except Exception:
            # 捕获异常信息并传递给 handleError
            import sys
            record.exc_info = sys.exc_info()
            self.handleError(record) # 调用 logging.Handler 的 handleError 方法

    def close(self):
        """
        关闭 ClogWriter 和父类 Handler。

        此方法确保底层的 `ClogWriter` 被正确关闭，从而刷新所有待处理的日志数据
        并释放文件资源。然后调用父类的 `close` 方法。
        """
        if self.clog_writer:
            self.clog_writer.close()
            self.clog_writer = None
        super().close()


class ClogRotatingFileHandler(ClogFileHandler):
    """
    一个支持基于文件大小进行轮转的 ClogFileHandler。
    采用“先检查，后写入”的健壮逻辑。
    """
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0,
                 encoding=None, compression_code=constants.COMPRESSION_GZIP):
        self.maxBytes = maxBytes
        self.backupCount = backupCount
        # 调用父类的构造函数
        super().__init__(filename, mode, encoding, compression_code)

    def doRollover(self):
        """
        执行日志轮转。
        """
        # 首先，关闭当前的 writer，这会将缓冲区刷新到待轮转的文件中
        if self.clog_writer:
            self.clog_writer.close()
            self.clog_writer = None

        if self.backupCount > 0 and os.path.exists(self.filename):
            # 从最旧的备份开始，依次重命名
            for i in range(self.backupCount - 1, 0, -1):
                sfn = f"{self.filename}.{i}"
                dfn = f"{self.filename}.{i + 1}"
                if os.path.exists(sfn):
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            
            # 将当前日志文件重命名为 .1
            dfn = f"{self.filename}.1"
            if os.path.exists(dfn):
                os.remove(dfn)
            os.rename(self.filename, dfn)
        
    def shouldRollover(self, record):
        """
        判断是否应该执行轮转。
        """
        if self.maxBytes <= 0:
            return False
        
        # 如果 writer 不存在，意味着这是第一次写入。
        # 我们让父类的 emit 去创建它，本次不轮转。
        if self.clog_writer is None:
            return False

        msg = self.format(record)
        
        timestamp = datetime.now().isoformat()
        record_str = f"{timestamp}{constants.FIELD_DELIMITER.decode()}{record.levelname}{constants.FIELD_DELIMITER.decode()}{msg}{constants.RECORD_DELIMITER.decode()}"
        predicted_record_size = len(record_str.encode('utf-8'))

        # 计算预估总大小
        try:
            current_file_size = os.path.getsize(self.filename)
        except FileNotFoundError:
            current_file_size = 0

        predicted_total_size = current_file_size + self.clog_writer.buffer_current_size + predicted_record_size
        
        return predicted_total_size >= self.maxBytes

    def emit(self, record):
        """
        发出一条记录。
        先检查是否需要轮转，然后再执行写入操作。
        """
        try:
            if self.shouldRollover(record):
                self.doRollover()
            
            # 调用父类 emit
            super().emit(record)
        except Exception:
            import sys
            record.exc_info = sys.exc_info()
            self.handleError(record)
