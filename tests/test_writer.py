# pyclog/tests/test_writer.py

import os
import pytest
import struct
import gzip
from datetime import datetime, timedelta

from pyclog.writer import ClogWriter
from pyclog import constants
from pyclog.exceptions import ClogWriteError, UnsupportedCompressionError

@pytest.fixture
def temp_clog_file(tmp_path):
    """为测试提供一个临时 .clog 文件路径。"""
    return tmp_path / "test.clog"

def test_writer_initialization_and_header(temp_clog_file):
    """测试 ClogWriter 初始化时是否正确写入文件头。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_GZIP) as writer:
        pass # 确保文件被创建和关闭

    assert temp_clog_file.exists()
    with open(temp_clog_file, 'rb') as f:
        header = f.read(16)
        # 0-4 Magic
        assert header[0:4] == constants.MAGIC_BYTES
        # 4-6 Version (2 bytes, unsigned short)
        version = struct.unpack('<H', header[4:6])[0]
        assert version == constants.FORMAT_VERSION
        # 6-8 Compression (2 bytes string)
        compression = header[6:8]
        # pack('2s', ...) pads with nulls if needed. GZIP is b'\x01'.
        expected_compression = struct.pack('<2s', constants.COMPRESSION_GZIP)
        assert compression == expected_compression
        # 8-16 Reserved
        assert header[8:16] == constants.RESERVED_BYTES

def test_writer_no_compression(temp_clog_file):
    """测试无压缩模式下的写入。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE) as writer:
        writer.write_record("INFO", "Hello, world!")
        writer.write_record("DEBUG", "Another log entry.")
    
    with open(temp_clog_file, 'rb') as f:
        f.read(16) # 跳过文件头
        
        # 读取第一个块头
        chunk_header = f.read(12)
        compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header)
        assert record_count == 2 # 两个记录
        
        # 读取块数据
        chunk_data = f.read(compressed_size)
        assert len(chunk_data) == uncompressed_size # 无压缩时，压缩大小等于未压缩大小

        records = chunk_data.split(constants.RECORD_DELIMITER)
        assert len(records) == 3 # 2条记录 + 末尾可能有的空行
        assert records[0].decode('utf-8').endswith("INFO\tHello, world!")
        assert records[1].decode('utf-8').endswith("DEBUG\tAnother log entry.")

def test_writer_gzip_compression(temp_clog_file):
    """测试 Gzip 压缩模式下的写入。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_GZIP) as writer:
        writer.write_record("INFO", "Test Gzip compression.")
        writer.write_record("WARNING", "This is a warning.")
    
    with open(temp_clog_file, 'rb') as f:
        f.read(16) # 跳过文件头
        
        chunk_header = f.read(12)
        compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header)
        assert record_count == 2
        
        compressed_data = f.read(compressed_size)
        decompressed_data = gzip.decompress(compressed_data)
        
        records = decompressed_data.split(constants.RECORD_DELIMITER)
        assert len(records) == 3
        assert records[0].decode('utf-8').endswith("INFO\tTest Gzip compression.")
        assert records[1].decode('utf-8').endswith("WARNING\tThis is a warning.")
        assert len(decompressed_data) == uncompressed_size

def test_writer_zstandard_compression(temp_clog_file):
    """测试 Zstandard 压缩模式下的写入。"""
    try:
        import zstandard as zstd
    except ImportError:
        pytest.skip("Zstandard 库未安装，跳过此测试。")

    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_ZSTANDARD) as writer:
        writer.write_record("INFO", "Test Zstandard compression.")
        writer.write_record("DEBUG", "Another Zstd entry.")
    
    with open(temp_clog_file, 'rb') as f:
        f.read(16) # 跳过文件头
        
        chunk_header = f.read(12)
        compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header)
        assert record_count == 2
        
        compressed_data = f.read(compressed_size)
        dctx = zstd.ZstdDecompressor()
        decompressed_data = dctx.decompress(compressed_data)
        
        records = decompressed_data.split(constants.RECORD_DELIMITER)
        assert len(records) == 3
        assert records[0].decode('utf-8').endswith("INFO\tTest Zstandard compression.")
        assert records[1].decode('utf-8').endswith("DEBUG\tAnother Zstd entry.")
        assert len(decompressed_data) == uncompressed_size

def test_writer_unsupported_compression_raises_error(temp_clog_file):
    """测试不持的压缩算法是否抛出错误。"""
    with pytest.raises(UnsupportedCompressionError):
        with ClogWriter(temp_clog_file, compression_code=b'\x99') as writer:
            writer.write_record("INFO", "Should not be written.")

def test_writer_flush_on_close(temp_clog_file):
    """测试关闭时是否刷新缓冲区。"""
    writer = ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE)
    writer.write_record("INFO", "Record 1")
    writer.write_record("INFO", "Record 2")
    # 不手动调用 _flush_chunk，直接关闭
    writer.close()

    with open(temp_clog_file, 'rb') as f:
        f.read(16) # 跳过文件头
        chunk_header = f.read(12)
        compressed_size, uncompressed_size, record_count = struct.unpack('<III', chunk_header)
        assert record_count == 2
        chunk_data = f.read(compressed_size)
        records = chunk_data.split(constants.RECORD_DELIMITER)
        assert len(records) == 3
        assert records[0].decode('utf-8').endswith("INFO\tRecord 1")
        assert records[1].decode('utf-8').endswith("INFO\tRecord 2")

def test_writer_multiple_chunks(temp_clog_file):
    """测试写入多个块。"""
    # 设置 buffer_flush_records 为 1，确保每条记录都生成一个块
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE, buffer_flush_records=1) as writer:
        writer.write_record("INFO", "Record A") # 写入第一个块
        writer.write_record("INFO", "Record B") # 写入第二个块
        writer.write_record("INFO", "Record C") # 写入第三个块
    
    with open(temp_clog_file, 'rb') as f:
        f.read(16) # 跳过文件头

        # 读取第一个块
        chunk1_header = f.read(12)
        cs1, us1, rc1 = struct.unpack('<III', chunk1_header)
        assert rc1 == 1
        chunk1_data = f.read(cs1)
        assert chunk1_data.decode('utf-8').endswith("INFO\tRecord A\n")

        # 读取第二个块
        chunk2_header = f.read(12)
        cs2, us2, rc2 = struct.unpack('<III', chunk2_header)
        assert rc2 == 1
        chunk2_data = f.read(cs2)
        assert chunk2_data.decode('utf-8').endswith("INFO\tRecord B\n")

        # 取第三个块
        chunk3_header = f.read(12)
        cs3, us3, rc3 = struct.unpack('<III', chunk3_header)
        assert rc3 == 1
        chunk3_data = f.read(cs3)
        assert chunk3_data.decode('utf-8').endswith("INFO\tRecord C\n")

        assert not f.read() # 确保文件结束

def test_writer_empty_file(temp_clog_file):
    """测试写入空文件（只包含头）。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE) as writer:
        pass # 不写入任何记录

    assert temp_clog_file.exists()
    with open(temp_clog_file, 'rb') as f:
        header = f.read(16)
        assert len(header) == 16
        assert not f.read() # 确保文件除了头没有其他内容

