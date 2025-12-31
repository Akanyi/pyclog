# pyclog/writer.py

"""
此模块提供 `ClogWriter` 类，用于创建和写入 .clog 文件。
它支持多种压缩算法和分块写入，以优化性能和文件大小。
"""

import gzip
import struct
import time
import os
import threading  
from datetime import datetime

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from . import constants
from .exceptions import ClogWriteError, UnsupportedCompressionError, InvalidClogFileError

class ClogWriter:
    """
    用于写入 .clog 文件的类。

    `ClogWriter` 负责将日志记录序列化并写入自定义的 .clog 文件格式。
    它支持多种压缩算法（无压缩、Gzip、Zstandard）和分块写入，
    以高效地处理大量日志数据。文件可以以写入 ('w') 或追加 ('a') 模式打开。

    文件格式概览:
    - 文件头 (16 字节): 包含魔术字节、格式版本、压缩代码和保留字节。
    - 数据块: 每个数据块包含一个块头和压缩后的日志数据。
        - 块头 (12 字节): 包含压缩数据大小、未压缩数据大小和块中记录条数。
        - 压缩数据: 实际的日志记录数据，经过选定算法压缩。

    日志记录格式:
    每条日志记录由时间戳、日志级别和消息组成，并由特定分隔符连接。
    例如: "2023-10-27T10:00:00.123456|INFO|这是一条日志消息。"
    """
    def __init__(self, file_path, mode='w', compression_code=constants.COMPRESSION_GZIP,
                 buffer_flush_size=4 * 1024 * 1024, buffer_flush_records=20000,
                 flush_interval=5.0):
        """
        初始化 ClogWriter 实例。

        Args:
            file_path (str): 要写入的 .clog 文件的路径。
            mode (str, optional): 文件打开模式。'w' 表示写入（覆盖现有文件），
                                  'a' 表示追加（如果文件存在，则追加到末尾）。
                                  默认为 'w'。
            compression_code (bytes, optional): 用于压缩日志数据的算法代码。
                                                支持 `constants.COMPRESSION_NONE` (无压缩),
                                                `constants.COMPRESSION_GZIP` (Gzip 压缩),
                                                `constants.COMPRESSION_ZSTANDARD` (Zstandard 压缩)。
                                                默认为 `constants.COMPRESSION_GZIP`。
            buffer_flush_size (int, optional): 缓冲区达到此字节大小时刷新。默认为 4MB。
            buffer_flush_records (int, optional): 缓冲区达到此记录数时刷新。默认为 20000 条记录。
            flush_interval (float, optional): 被动刷新间隔（秒）。如果自上次刷新以来超过此时间，
                                              则在写入下一条记录时强制刷新。默认为 5.0 秒。

        Raises:
            ClogWriteError: 如果文件无法打开或在追加模式下文件头验证失败。
            UnsupportedCompressionError: 如果选择了 Zstandard 但未安装相关库。
        """
        self.file_path = file_path
        self.mode = mode
        self.compression_code = compression_code
        self.buffer_flush_size = buffer_flush_size
        self.buffer_flush_records = buffer_flush_records
        self.flush_interval = flush_interval
        self.file = None
        self.buffer = []
        self.buffer_current_size = 0
        self.buffer_current_records = 0
        self.last_flush_time = time.time()
        self.lock = threading.Lock()  

        try:
            self._open_file()
        except Exception:
            if self.file:
                self.file.close()
            raise

    def _open_file(self):
        """
        打开文件并验证/写入文件头。
        """
        if self.mode == 'a':
            if os.path.exists(self.file_path):
                self.file = open(self.file_path, 'r+b')
                self._validate_header_for_append()
                self.file.seek(0, 2) # Move to end of file
            else:
                self.file = open(self.file_path, 'wb')
                self._write_header()
        else:
            self.file = open(self.file_path, 'wb')
            self._write_header()

    def _validate_header_for_append(self):
        """
        验证现有文件的头部是否与当前配置匹配。
        """
        try:
            self.file.seek(0)
            header = self.file.read(16)
            if len(header) < 16:
                 raise InvalidClogFileError("文件太小，不是有效的 .clog 文件")
            
            magic, version, compression_code, _ = struct.unpack('<4sH2s8s', header)
            
            if magic != constants.MAGIC_BYTES:
                raise InvalidClogFileError("无效的魔术字节")
            
            if version != constants.FORMAT_VERSION:
                # 以后可能支持向后兼容，但现在必须严格匹配
                 raise InvalidClogFileError(f"不支持的版本: {version}")
                 
            if compression_code.rstrip(b'\x00') != self.compression_code.rstrip(b'\x00'):
                 # 可以选择在这里警告而不是报错，但混合压缩格式可能会使读取器复杂化
                 raise ClogWriteError(f"压缩格式不匹配: 文件是 {compression_code}, 当前配置是 {self.compression_code}")

        except struct.error:
             raise InvalidClogFileError("无法解析文件头")

    def _write_header(self):
        """
        写入 .clog 文件头。
        """
        header = struct.pack('<4sH2s8s', 
                             constants.MAGIC_BYTES, 
                             constants.FORMAT_VERSION, 
                             self.compression_code, 
                             b'\x00' * 8) # Reserved
        self.file.write(header)

    def _compress_chunk(self, data):
        """
        压缩数据块。

        Args:
            data (bytes): 要压缩的原始数据。

        Returns:
            tuple: (compressed_data, uncompressed_size, record_count)
                   compressed_data (bytes): 压缩后的数据。
                   uncompressed_size (int): 原始数据大小。
                   record_count (int): 数据块中的记录数（这里传递的是 current buffer count，
                   但在 _flush_chunk 中已经在 buffer_current_records 中知道了，
                   实际上这个 helper 主要负责压缩逻辑）。
                   
                   Wait, _flush_chunk calls this.
                   Let's align with usage in _flush_chunk:
                   compressed_data, uncompressed_size, record_count_in_chunk = self._compress_chunk(records_data)
        """
        uncompressed_size = len(data)
        record_count = self.buffer_current_records # Using instance variable as the context

        if self.compression_code == constants.COMPRESSION_NONE:
            return data, uncompressed_size, record_count
        
        elif self.compression_code == constants.COMPRESSION_GZIP:
            compressed_data = gzip.compress(data)
            return compressed_data, uncompressed_size, record_count
            
        elif self.compression_code == constants.COMPRESSION_ZSTANDARD:
            if zstd is None:
                raise UnsupportedCompressionError("Zstandard 库未安装")
            cctx = zstd.ZstdCompressor()
            compressed_data = cctx.compress(data)
            return compressed_data, uncompressed_size, record_count
        
        else:
             # Should be unreachable if validated correctly
             raise UnsupportedCompressionError(f"未知的压缩代码: {self.compression_code}")

    def write_record(self, level, message):
        """
        写入一条日志记录。此方法是线程安全的。

        将给定的日志级别和消息与当前时间戳组合，形成一条完整的日志记录。
        这条记录会被添加到内部缓冲区。当缓冲区达到预设的 `buffer_flush_size`
        或 `buffer_flush_records` 阈值时，或者自上次刷新以来超过了 `flush_interval`，
        缓冲区内容会自动被压缩并写入文件。

        Args:
            level (str): 日志级别（例如 "INFO", "WARNING", "ERROR"）。
            message (str): 日志消息内容。
        """
        target_flush_needed = False
        
        with self.lock:
            timestamp = datetime.now().isoformat()
            
            # 将消息中的换行符替换为内部表示（垂直制表符 \v），以支持多行日志
            processed_message = message.replace('\n', '\v')

            record_str = (
                f"{timestamp}{constants.FIELD_DELIMITER.decode()}"
                f"{level}{constants.FIELD_DELIMITER.decode()}"
                f"{processed_message}{constants.RECORD_DELIMITER.decode()}"
            )
            record_bytes = record_str.encode('utf-8')
            
            self.buffer.append(record_bytes)
            self.buffer_current_size += len(record_bytes)
            self.buffer_current_records += 1

            # 检查刷新条件
            now = time.time()
            time_since_flush = now - self.last_flush_time
            
            if (self.buffer_current_size >= self.buffer_flush_size or 
                self.buffer_current_records >= self.buffer_flush_records or
                (self.buffer and time_since_flush >= self.flush_interval)):
                target_flush_needed = True

            if target_flush_needed:
                self._flush_chunk()
                self.last_flush_time = time.time()

    def _flush_chunk(self):
        """
        将缓冲区中的日志记录压缩并写入文件。

        此方法将当前缓冲区中的所有日志记录拼接成一个字节串，
        然后根据配置的压缩算法进行压缩，并将压缩后的数据连同块头写入文件。
        写入完成后，缓冲区将被清空。

        Raises:
            ClogWriteError: 如果写入数据块失败。
        """
        if not self.buffer:
            return

        records_data = b''.join(self.buffer)
        
        compressed_data, uncompressed_size, record_count_in_chunk = self._compress_chunk(records_data)
        compressed_size = len(compressed_data)

        chunk_header = struct.pack('<III', compressed_size, uncompressed_size, record_count_in_chunk)
        
        try:
            self.file.write(chunk_header)
            self.file.write(compressed_data)
        except IOError as e:
            raise ClogWriteError(f"写入数据块失败: {e}")
        
        self.buffer = []
        self.buffer_current_size = 0
        self.buffer_current_records = 0

    def close(self):
        """
        关闭文件。

        在关闭文件句柄之前，此方法会确保所有缓冲区中剩余的日志记录都被刷新并写入文件。
        """
        with self.lock:
            if self.file:
                try:
                    self._flush_chunk()
                except ClogWriteError as e:
                    print(f"警告: 关闭文件前刷新缓冲区失败: {e}")
                finally:
                    try:
                        self.file.close()
                    except IOError as e:
                        raise ClogWriteError(f"关闭文件失败: {e}")
                    self.file = None

    def __enter__(self):
        """
        支持上下文管理器协议。

        Returns:
            ClogWriter: 当前 ClogWriter 实例。
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        支持上下文管理器协议。

        在退出上下文时关闭文件。

        Args:
            exc_type: 异常类型（如果有）。
            exc_val: 异常值（如果有）。
            exc_tb: 异常回溯（如果有）。
        """
        self.close()