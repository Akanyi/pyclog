# pyclog/writer.py

import gzip
import struct
import time
from datetime import datetime

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from . import constants
from .exceptions import ClogWriteError, UnsupportedCompressionError

class ClogWriter:
    """
    用于写入 .clog 文件的类。
    它支持分块压缩，并能将多条日志记录序列化到每个块中。
    """
    def __init__(self, file_path, compression_code=constants.COMPRESSION_GZIP):
        self.file_path = file_path
        self.compression_code = compression_code
        self.file = None
        self.buffer = []  # 存储待写入的日志记录 (字符串)
        self.buffer_size = 0  # 缓冲区当前字节大小 (近似值)
        self.record_count = 0  # 缓冲区中的记录条数

        self._open_file()
        self._write_header()

    def _open_file(self):
        """打开文件以二进制写入模式。"""
        try:
            self.file = open(self.file_path, 'wb')
        except IOError as e:
            raise ClogWriteError(f"无法打开文件 '{self.file_path}' 进行写入: {e}")

    def _write_header(self):
        """写入固定的16字节文件头。"""
        header = constants.MAGIC_BYTES + \
                 constants.FORMAT_VERSION_V1 + \
                 self.compression_code + \
                 constants.RESERVED_BYTES
        try:
            self.file.write(header)
        except IOError as e:
            raise ClogWriteError(f"写入文件头失败: {e}")

    def _compress_chunk(self, records_data):
        """
        将原始日志数据进行压缩。
        records_data: 已经拼接好的字节串。
        返回: 压缩后的数据, 原始数据大小, 记录条数。
        """
        uncompressed_size = len(records_data)
        
        if self.compression_code == constants.COMPRESSION_NONE:
            compressed_data = records_data
        elif self.compression_code == constants.COMPRESSION_GZIP:
            compressed_data = gzip.compress(records_data)
        elif self.compression_code == constants.COMPRESSION_ZSTANDARD:
            if zstd is None:
                raise UnsupportedCompressionError("Zstandard 压缩库未安装。请安装 'python-zstandard'。")
            cctx = zstd.ZstdCompressor()
            compressed_data = cctx.compress(records_data)
        else:
            raise UnsupportedCompressionError(f"不支持的压缩算法代码: {self.compression_code}")
        
        return compressed_data, uncompressed_size, len(self.buffer) # len(self.buffer) 是当前块的记录数

    def write_record(self, level, message):
        """
        写入一条日志记录。
        level: 日志级别 (字符串)。
        message: 日志消息 (字符串)。
        """
        timestamp = datetime.now().isoformat()
        record_str = f"{timestamp}{constants.FIELD_DELIMITER.decode()}{level}{constants.FIELD_DELIMITER.decode()}{message}{constants.RECORD_DELIMITER.decode()}"
        record_bytes = record_str.encode('utf-8')
        
        self.buffer.append(record_bytes)
        self.buffer_size += len(record_bytes)
        self.record_count += 1

        # 当缓冲区达到一定大小或记录数量时，刷新块
        # 这里的阈值可以根据实际需求调整
        if self.buffer_size >= 1024 * 1024 or self.record_count >= 1000: # 1MB 或 1000 条记录
            self._flush_chunk()

    def _flush_chunk(self):
        """
        将缓冲区中的日志记录压缩并写入文件。
        """
        if not self.buffer:
            return

        # 将所有记录拼接成一个字节串
        records_data = b''.join(self.buffer)
        
        compressed_data, uncompressed_size, record_count_in_chunk = self._compress_chunk(records_data)
        compressed_size = len(compressed_data)

        # 写入块头 (Compressed Size, Uncompressed Size, Record Count)
        # 使用 little-endian (LE) 字节序
        chunk_header = struct.pack('<III', compressed_size, uncompressed_size, record_count_in_chunk)
        
        try:
            self.file.write(chunk_header)
            self.file.write(compressed_data)
        except IOError as e:
            raise ClogWriteError(f"写入数据块失败: {e}")
        
        # 清空缓冲区
        self.buffer = []
        self.buffer_size = 0
        self.record_count = 0

    def close(self):
        """
        关闭文件。在关闭前确保所有缓冲区中的记录都被写入文件。
        """
        if self.file:
            self._flush_chunk() # 确保所有剩余数据被写入
            try:
                self.file.close()
            except IOError as e:
                raise ClogWriteError(f"关闭文件失败: {e}")
            self.file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
