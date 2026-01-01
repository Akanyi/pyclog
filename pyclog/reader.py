# pyclog/reader.py

"""
此模块提供 `ClogReader` 类，用于从 .clog 文件中读取和解析日志记录。
它支持多种压缩算法和分块读取，并能流式处理日志数据。
"""

import gzip
import struct
import time
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

    `ClogReader` 负责从自定义的 .clog 文件格式中读取和解压日志记录。
    它能够处理无压缩、Gzip 和 Zstandard 压缩的数据块，并提供迭代器
    以流式方式访问原始数据块或解析后的日志记录。

    文件格式概览:
    - 文件头 (16 字节): 包含魔术字节、格式版本、压缩代码和保留字节。
    - 数据块: 每个数据块包含一个块头和压缩后的日志数据。
        - 块头 (12 字节): 包含压缩数据大小、未压缩数据大小和块中记录条数。
        - 压缩数据: 实际的日志记录数据，经过选定算法压缩。

    日志记录格式:
    每条日志记录由时间戳、日志级别和消息组成，并由特定分隔符连接。
    例如: "2023-10-27T10:00:00.123456|INFO|这是一条日志消息。"
    """
    def __init__(self, file_path):
        """
        初始化 ClogReader 实例。

        Args:
            file_path (str): 要读取的 .clog 文件的路径。

        Raises:
            ClogReadError: 如果文件无法打开。
            InvalidClogFileError: 如果文件头无效或损坏。
            UnsupportedCompressionError: 如果文件使用的压缩算法不受支持或缺少必要的库。
        """
        self.file_path = file_path
        self.file = None
        self.compression_code = None
        self.format_version = None

        try:
            self._open_file()
            self._read_header()
        except Exception:
            if self.file:
                self.file.close()
            raise

    def _open_file(self):
        """
        打开文件以二进制读取模式。

        Raises:
            ClogReadError: 如果文件无法打开。
        """
        try:
            self.file = open(self.file_path, 'rb')
        except IOError as e:
            raise ClogReadError(f"无法打开文件 '{self.file_path}' 进行读取: {e}")

    def _read_header(self):
        """
        读取并解析16字节文件头。

        验证魔术字节、格式版本和压缩代码。

        Raises:
            InvalidClogFileError: 如果文件太短、魔术字节不匹配、格式版本不支持或解析失败。
            UnsupportedCompressionError: 如果文件使用的压缩算法不受支持或缺少必要的库。
            ClogReadError: 如果读取文件头时发生 I/O 错误。
        """
        try:
            header = self.file.read(constants.HEADER_SIZE)
            if len(header) < constants.HEADER_SIZE:
                raise InvalidClogFileError("文件太短，无法读取完整的 .clog 文件头。")

            try:
                magic_bytes, format_version, compression_code_padded, _ = struct.unpack('<4sH2s8s', header)
            except struct.error:
                raise InvalidClogFileError("文件头格式错误")

            if magic_bytes != constants.MAGIC_BYTES:
                raise InvalidClogFileError(f"无效的 Magic Bytes: {magic_bytes.hex()}。期望: {constants.MAGIC_BYTES.hex()}")
            
            if format_version != constants.FORMAT_VERSION:
                raise InvalidClogFileError(f"不支持的格式版本: {format_version}。期望: {constants.FORMAT_VERSION}")

            # 压缩代码字段为2字节，但实际代码通常是1字节（如 b'\x01'）
            # 所以使用 struct.unpack('2s') 读取后会得到 b'\x01\x00'
            # 第一个字节即可代表压缩算法
            self.compression_code = compression_code_padded[0:1]
            self.format_version = format_version

            if self.compression_code not in [
                constants.COMPRESSION_NONE,
                constants.COMPRESSION_GZIP,
                constants.COMPRESSION_ZSTANDARD
            ]:
                raise UnsupportedCompressionError(f"不支持的压缩算法代码: {self.compression_code.hex()}")
            
            if self.compression_code == constants.COMPRESSION_ZSTANDARD and zstd is None:
                raise UnsupportedCompressionError("Zstandard 压缩库未安装，无法读取 Zstandard 压缩文件。")

        except IOError as e:
            raise ClogReadError(f"读取文件头失败: {e}")
        except UnsupportedCompressionError:
            raise
        except Exception as e:
            raise InvalidClogFileError(f"解析文件头失败: {e}")

    def _decompress_chunk(self, compressed_data, uncompressed_size):
        """
        根据文件头中指定的压缩算法解压数据块。

        Args:
            compressed_data (bytes): 压缩后的数据字节串。
            uncompressed_size (int): 原始未压缩数据的大小（字节）。

        Returns:
            bytes: 解压后的原始字节串。

        Raises:
            UnsupportedCompressionError: 如果文件使用的压缩算法不受支持或缺少必要的库。
            ClogReadError: 如果解压过程中发生错误。
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

    def read_chunks(self, follow=False, interval=0.1):
        """
        迭代读取文件中的所有数据块。

        每个数据块都包含一个块头（指示压缩大小、未压缩大小和记录数）
        和实际的压缩数据。此方法负责读取这些块并解压数据。

        Yields:
            tuple: 包含以下元素的元组：
                - decompressed_data (bytes): 解压后的原始数据字节串。
                - record_count (int): 当前块中的记录条数。

        Raises:
            ClogReadError: 如果文件意外结束或块头解析失败。
        """
        while True:
            chunk_header_bytes = self.file.read(constants.CHUNK_HEADER_SIZE)
            if not chunk_header_bytes:
                if follow:
                    time.sleep(interval)
                    continue
                else:
                    break
            if len(chunk_header_bytes) < constants.CHUNK_HEADER_SIZE:
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

    def read_records(self, follow=False, interval=0.1):
        """
        流式读取并解析文件中的所有日志记录。

        此方法通过迭代数据块，将每个解压后的数据块分割成单独的日志记录，
        并解析出时间戳、日志级别和消息。

        Yields:
            tuple: 包含以下元素的元组：
                - timestamp_str (str): 日志记录的时间戳字符串。
                - level_str (str): 日志记录的级别字符串。
                - message_str (str): 日志记录的消息字符串。

        Raises:
            ClogReadError: 如果解码或解析日志记录失败。
        """
        for decompressed_data, _ in self.read_chunks(follow=follow, interval=interval):
            records_bytes = decompressed_data.split(constants.RECORD_DELIMITER)
            for record_bytes in records_bytes:
                if not record_bytes:
                    continue
                
                try:
                    record_str = record_bytes.decode('utf-8')
                    parts = record_str.split(constants.FIELD_DELIMITER.decode(), 2)
                    if len(parts) == 3:
                        timestamp_str, level_str, message_str = parts
                        yield timestamp_str, level_str, message_str
                    else:
                        pass
                except UnicodeDecodeError as e:
                    raise ClogReadError(f"解码日志记录失败: {e}")
                except Exception as e:
                    raise ClogReadError(f"解析日志记录失败: {e}")

    def tail(self, n):
        """
        高效读取最后 n 条记录。
        
        通过扫描块头而不是解压整个文件来实现。
        扫描所有块的 header，记录位置和 count，然后只解压最后需要的几个块。
        
        Returns:
            list: 包含最后 n 条记录的 list (timestamp, level, message)。
        """
        # 保存当前文件位置，以便恢复（如果需要，不过通常 tail 后继续读也合理）
        try:
            self.file.seek(constants.HEADER_SIZE) # Skip file header
        except IOError:
             return [] # Empty file or error?

        chunks_map = [] # (offset_of_data, compressed_size, uncompressed_size, record_count)
        
        while True:
            try:
                # 记录 Chunk Header 开始位置
                header_offset = self.file.tell()
                chunk_header_bytes = self.file.read(constants.CHUNK_HEADER_SIZE)
                if not chunk_header_bytes or len(chunk_header_bytes) < constants.CHUNK_HEADER_SIZE:
                    break
                
                compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header_bytes)
                
                # 数据真正开始的位置
                data_offset = self.file.tell()
                
                chunks_map.append({
                    "data_offset": data_offset,
                    "compressed_size": compressed_size,
                    "uncompressed_size": uncompressed_size,
                    "count": record_count
                })
                
                # 跳过数据块，不解压
                self.file.seek(compressed_size, 1)
                
            except struct.error:
                break
            except IOError:
                break
                
        # 从后往前数，找到需要的 chunks
        needed_count = n
        chunks_to_read = []
        
        for chunk_info in reversed(chunks_map):
            chunks_to_read.insert(0, chunk_info)
            needed_count -= chunk_info["count"]
            if needed_count <= 0:
                break
        
        # 读取这些 chunks
        results = []
        for chunk_info in chunks_to_read:
            self.file.seek(chunk_info["data_offset"])
            compressed_data = self.file.read(chunk_info["compressed_size"])
            
            # 复用内部解压逻辑
            decompressed_data = self._decompress_chunk(compressed_data, chunk_info["uncompressed_size"])
            
            # 解析记录
            records_bytes = decompressed_data.split(constants.RECORD_DELIMITER)
            for record_bytes in records_bytes:
                if not record_bytes:
                    continue
                try:
                    record_str = record_bytes.decode('utf-8')
                    parts = record_str.split(constants.FIELD_DELIMITER.decode(), 2)
                    if len(parts) == 3:
                        results.append(tuple(parts))
                except Exception:
                    pass
                    
        # 确保文件指针回到 EOF。
        # tail 操作中我们会 seek 回去读取旧的数据块，
        # 为了支持后续的 follow (tail -f) 操作，必须重置指针到文件末尾。
        self.file.seek(0, 2) 
        
        return results[-n:] if n > 0 else []

    def close(self):
        """
        关闭文件句柄。

        确保文件资源被正确释放。

        Raises:
            ClogReadError: 如果关闭文件失败。
        """
        if self.file:
            try:
                self.file.close()
            except IOError as e:
                raise ClogReadError(f"关闭文件失败: {e}")
            self.file = None

    def __enter__(self):
        """
        支持上下文管理器协议。

        Returns:
            ClogReader: 当前 ClogReader 实例。
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
