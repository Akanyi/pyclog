# pyclog/handler.py

import logging
from .writer import ClogWriter
from . import constants
from .exceptions import ClogWriteError

class ClogFileHandler(logging.Handler):
    """
    一个用于将日志记录写入 .clog 文件的 logging Handler。
    """
    def __init__(self, filename, mode='a', encoding=None, compression_code=constants.COMPRESSION_GZIP):
        # logging.Handler.__init__(self) # Python 3.x 推荐使用 super()
        super().__init__()
        self.filename = filename
        self.mode = mode # 'a' for append, 'w' for write (not fully supported by ClogWriter yet, always creates new)
        self.encoding = encoding # ClogWriter 内部处理编码为 utf-8
        self.compression_code = compression_code
        self.clog_writer = None
        self._open_writer()

    def _open_writer(self):
        """初始化 ClogWriter 实例。"""
        try:
            # ClogWriter 总是以 'wb' 模式打开，所以 'mode' 参数在这里主要是为了兼容 logging.FileHandler 的签名
            # 实际行为是每次创建新文件或覆盖现有文件，除非 ClogWriter 内部支持追加模式
            self.clog_writer = ClogWriter(self.filename, self.compression_code)
        except ClogWriteError as e:
            self.handleError(logging.LogRecord(self.name, logging.CRITICAL, __file__, 0, f"无法初始化 ClogWriter: {e}", None, None))
            self.clog_writer = None # 确保在初始化失败时设置为 None

    def emit(self, record):
        """
        将格式化后的日志记录写入 .clog 文件。
        """
        if self.clog_writer is None:
            return # 如果 writer 未成功初始化，则不写入

        try:
            # 使用 Handler 的 formatter 格式化记录
            msg = self.format(record)
            self.clog_writer.write_record(record.levelname, msg)
        except Exception as e:
            self.handleError(record) # 调用 logging.Handler 的 handleError 方法

    def close(self):
        """
        关闭 ClogWriter 和父类 Handler。
        """
        if self.clog_writer:
            self.clog_writer.close()
            self.clog_writer = None
        super().close()
