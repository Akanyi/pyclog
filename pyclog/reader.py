# pyclog/reader.py

import gzip
import struct
from datetime import datetime

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from . import constants
from .exceptions import ClogReadError, InvalidClogFileError, UnsupportedCompressionError

class ClogReader:
    """
    用于读取 .clog 文件的类。
    它支持分块解压缩，并能流式读取日志记录。
    """
    def __init__(self, file_path):
        self.file_path = file_path
        self.file = None
        self.compression_code = None
        self.format_version = None

        self._open_file()
        self._read_header()

    def _open_file(self):
        """打开文件以二进制读取模式。"""
        try:
            self.file = open(self.file_path, 'rb')
        except IOError as e:
            raise ClogReadError(f"无法打开文件 '{self.file_path}' 进行读取: {e}")

    def _read_header(self):
        """读取并解析16字节文件头。"""
        try:
            header = self.file.read(16)
            if len(header) < 16:
                raise InvalidClogFileError("文件太短，无法读取完整的 .clog 文件头。")

            magic_bytes = header[0:4]
            format_version = header[4:5]
            compression_code = header[5:6]
            # reserved_bytes = header[6:16] # 暂时不使用

            if magic_bytes != constants.MAGIC_BYTES:
                raise InvalidClogFileError(f"无效的 Magic Bytes: {magic_bytes.hex()}。期望: {constants.MAGIC_BYTES.hex()}")
            
            if format_version != constants.FORMAT_VERSION_V1:
                raise InvalidClogFileError(f"不支持的格式版本: {format_version.hex()}。期望: {constants.FORMAT_VERSION_V1.hex()}")

            self.compression_code = compression_code
            self.format_version = format_version

        except IOError as e:
            raise ClogReadError(f"读取文件头失败: {e}")
        except Exception as e:
            raise InvalidClogFileError(f"解析文件头失败: {e}")

    def _decompress_chunk(self, compressed_data, uncompressed_size):
        """
        根据压缩算法解压数据。
        返回: 解压后的原始字节串。
        """
        if self.compression_code == constants.COMPRESSION_NONE:
            return compressed_data
        elif self.compression_code == constants.COMPRESSION_GZIP:
            try:
                return gzip.decompress(compressed_data)
            except Exception as e:
                raise ClogReadError(f"Gzip 解压失败: {e}")
        elif self.compression_code == constants.COMPRESSION_ZSTANDARD:
            if zstd is None:
                raise UnsupportedCompressionError("Zstandard 解压库未安装。请安装 'python-zstandard'。")
            try:
                dctx = zstd.ZstdDecompressor()
                return dctx.decompress(compressed_data, max_output_size=uncompressed_size)
            except Exception as e:
                raise ClogReadError(f"Zstandard 解压失败: {e}")
        else:
            raise UnsupportedCompressionError(f"不支持的压缩算法代码: {self.compression_code.hex()}")

    def read_chunks(self):
        """
        迭代读取文件中的所有数据块。
        yields: 解压后的原始数据 (字节串) 和记录条数。
        """
        while True:
            chunk_header_bytes = self.file.read(12) # 块头固定12字节 (3个UINT32)
            if not chunk_header_bytes: # 文件结束
                break
            if len(chunk_header_bytes) < 12:
                raise ClogReadError("文件意外结束，无法读取完整的块头。")

            try:
                compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header_bytes)
            except struct.error as e:
                raise ClogReadError(f"解析块头失败: {e}")

            compressed_data = self.file.read(compressed_size)
            if len(compressed_data) < compressed_size:
                raise ClogReadError("文件意外结束，无法读取完整的块数据。")
            
            decompressed_data = self._decompress_chunk(compressed_data, uncompressed_size)
            yield decompressed_data, record_count

    def read_records(self):
        """
        流式读取并解析文件中的所有日志记录。
        yields: (timestamp_str, level_str, message_str)
        """
        for decompressed_data, _ in self.read_chunks():
            records_bytes = decompressed_data.split(constants.RECORD_DELIMITER)
            for record_bytes in records_bytes:
                if not record_bytes: # 过空行 (例如文件末尾的空行)
                    continue
                
                try:
                    record_str = record_bytes.decode('utf-8')
                    parts = record_str.split(constants.FIELD_DELIMITER.decode(), 2) # 最多分割2次
                    if len(parts) == 3:
                        timestamp_str, level_str, message_str = parts
                        yield timestamp_str, level_str, message_str
                    else:
                        # 如果格式不正确，可以记录警告或抛出异常
                        # 这里选择跳过，避免中断整个读取过程
                        # print(f"警告: 无法解析的日志记录格式: {record_str}")
                        pass
                except UnicodeDecodeError as e:
                    raise ClogReadError(f"解码日志记录失败: {e}")
                except Exception as e:
                    raise ClogReadError(f"解析日志记录失败: {e}")

    def close(self):
        """关闭文件句柄。"""
        if self.file:
            try:
                self.file.close()
            except IOError as e:
                raise ClogReadError(f"关闭文件失败: {e}")
            self.file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
