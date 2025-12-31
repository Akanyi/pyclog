# pyclog/tests/test_reader_writer.py

import pytest
import os
import logging
import struct
from datetime import datetime, timedelta

from pyclog.writer import ClogWriter
from pyclog.reader import ClogReader
from pyclog.handler import ClogFileHandler
from pyclog import constants
from pyclog.exceptions import InvalidClogFileError, UnsupportedCompressionError, ClogReadError, ClogWriteError

@pytest.fixture
def temp_clog_file(tmp_path):
    """为测试提供一个临时 .clog 文件路径。"""
    return tmp_path / "test_integration.clog"

def generate_test_records(num_records):
    """生成指定数量的测试日志记录。"""
    records = []
    for i in range(num_records):
        timestamp = (datetime.now() + timedelta(seconds=i)).isoformat()
        level = "INFO" if i % 2 == 0 else "DEBUG"
        message = f"Test log message {i} with some random data: {'a' * (i % 50)}"
        records.append((timestamp, level, message))
    return records

def write_and_read_test(file_path, compression_code, num_records):
    """辅助函数：写入记录并尝试读取。"""
    expected_records = generate_test_records(num_records)

    # 写入
    # 设置 buffer_flush_records 为 1，确保每条记录都生成一个块，便于测试准确性
    with ClogWriter(file_path, compression_code=compression_code, buffer_flush_records=1) as writer:
        for ts, level, msg in expected_records:
            writer.write_record(level, msg) # 注意：writer.write_record 只接受 level 和 message

    # 读取
    actual_records = []
    with ClogReader(file_path) as reader:
        for ts, level, msg in reader.read_records():
            actual_records.append((ts, level, msg))
    
    # 验证
    assert len(actual_records) == len(expected_records)
    for i in range(num_records):
        # 时间戳可能因为毫秒精度有差异，只比较级别和消息
        assert actual_records[i][1] == expected_records[i][1] # level
        assert actual_records[i][2] == expected_records[i][2] # message
        # 验证时间戳格式是否正确 (ISO8601)
        try:
            datetime.fromisoformat(actual_records[i][0])
        except ValueError:
            pytest.fail(f"时间戳格式不正确: {actual_records[i][0]}")

def test_integration_no_compression(temp_clog_file):
    """测试无压缩模式下的写入和读取集成。"""
    write_and_read_test(temp_clog_file, constants.COMPRESSION_NONE, 10)
    write_and_read_test(temp_clog_file, constants.COMPRESSION_NONE, 1) # 单条记录
    write_and_read_test(temp_clog_file, constants.COMPRESSION_NONE, 0) # 空文件

def test_integration_gzip_compression(temp_clog_file):
    """测试 Gzip 压缩模式下的写入和读取集成。"""
    write_and_read_test(temp_clog_file, constants.COMPRESSION_GZIP, 50)
    write_and_read_test(temp_clog_file, constants.COMPRESSION_GZIP, 1)
    write_and_read_test(temp_clog_file, constants.COMPRESSION_GZIP, 0)

def test_integration_zstandard_compression(temp_clog_file):
    """测试 Zstandard 压缩模式下的写入和读取集成。"""
    try:
        import zstandard as zstd
    except ImportError:
        pytest.skip("Zstandard 库未安装，跳过此测试。")
    
    write_and_read_test(temp_clog_file, constants.COMPRESSION_ZSTANDARD, 100)
    write_and_read_test(temp_clog_file, constants.COMPRESSION_ZSTANDARD, 1)
    write_and_read_test(temp_clog_file, constants.COMPRESSION_ZSTANDARD, 0)

def test_reader_invalid_magic_bytes(tmp_path):
    """测试读取无效 Magic Bytes 的文件。"""
    bad_file = tmp_path / "bad.clog"
    with open(bad_file, 'wb') as f:
        f.write(b'BAD!' + struct.pack('<H', constants.FORMAT_VERSION) + struct.pack('<2s', constants.COMPRESSION_GZIP) + constants.RESERVED_BYTES)
    
    with pytest.raises(InvalidClogFileError, match="无效的 Magic Bytes"):
        ClogReader(bad_file)

def test_reader_unsupported_compression_code(tmp_path):
    """测试读取不支持的压缩代码的文件。"""
    bad_file = tmp_path / "unsupported.clog"
    with open(bad_file, 'wb') as f:
        f.write(constants.MAGIC_BYTES + struct.pack('<H', constants.FORMAT_VERSION) + struct.pack('<2s', b'\x99') + constants.RESERVED_BYTES)
    
    with pytest.raises(UnsupportedCompressionError, match="不支持的压缩算法代码"):
        ClogReader(bad_file)

def test_reader_truncated_file_header(tmp_path):
    """测试读取文件头不完整的 .clog 文件。"""
    truncated_file = tmp_path / "truncated.clog"
    with open(truncated_file, 'wb') as f:
        f.write(constants.MAGIC_BYTES) # 只写入部分头
    
    with pytest.raises(InvalidClogFileError, match="文件太短"):
        ClogReader(truncated_file)

def test_reader_truncated_chunk_header(temp_clog_file):
    """测试读取块头不完整的 .clog 文件。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE) as writer:
        writer.write_record("INFO", "Test record.")
    
    # 手动截断文件，使其块头不完整
    with open(temp_clog_file, 'r+b') as f:
        f.seek(16) # 跳过文件头
        f.truncate(f.tell() + 5) # 只保留块头的一部分 (12字节，这里只保留5字节)

    with pytest.raises(ClogReadError, match="文件意外结束，无法读取完整的块头"):
        with ClogReader(temp_clog_file) as reader:
            list(reader.read_records())

def test_reader_truncated_chunk_data(temp_clog_file):
    """测试读取块数据不完整的 .clog 文件。"""
    with ClogWriter(temp_clog_file, compression_code=constants.COMPRESSION_NONE) as writer:
        writer.write_record("INFO", "Test record.")
    
    # 手动截断文件，使其块数据不完整
    with open(temp_clog_file, 'r+b') as f:
        f.seek(16 + 12) # 跳过文件头和块头
        f.truncate(f.tell() + 5) # 只保留块数据的一部分

    with pytest.raises(ClogReadError, match="文件意外结束，无法读取完整的块数据"):
        with ClogReader(temp_clog_file) as reader:
            list(reader.read_records())

def test_clog_file_handler_integration(temp_clog_file):
    """测试 ClogFileHandler 与 logging 模块的集成。"""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    
    # 移除可能存在的其他 handler
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = ClogFileHandler(temp_clog_file, compression_code=constants.COMPRESSION_GZIP)
    formatter = logging.Formatter('%(asctime)s\t%(levelname)s\t%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("Log message 1 from handler.")
    logger.warning("Log message 2 from handler.")
    logger.debug("This debug message should not be written.") # 级别低于 INFO

    handler.close() # 确保所有日志被刷新到文件

    # 验证写入的日志
    read_records = []
    with ClogReader(temp_clog_file) as reader:
        for ts, level, msg in reader.read_records():
            read_records.append((level, msg))
    
    assert len(read_records) == 2
    assert read_records[0][0] == "INFO"
    assert "Log message 1 from handler." in read_records[0][1]
    assert read_records[1][0] == "WARNING"
    assert "Log message 2 from handler." in read_records[1][1]



from unittest.mock import MagicMock, patch

def test_clog_file_handler_emit_error(tmp_path):
    """测试 ClogFileHandler 在 emit 失败时调用 handleError。"""
    # 为这个测试创建另一个独立的 logger
    logger = logging.getLogger("test_emit_error_logger")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # 准备一个 mock ClogWriter 实例，它将在调用 write_record 时失败
    mock_writer_instance = MagicMock(spec=ClogWriter)
    mock_writer_instance.write_record.side_effect = ClogWriteError("模拟写入失败")
    mock_writer_instance.file = MagicMock() # 模拟 file 属性

    # patch ClogWriter 类，让它在被调用时返回 mock 实例
    with patch('pyclog.handler.ClogWriter', return_value=mock_writer_instance):
        handler = ClogFileHandler(tmp_path / "emit_error.clog")
        # 验证 writer 初始为 None (Lazy loading)
        assert handler.clog_writer is None

        # patch 这个 handler 实例的 handleError 方法
        with patch.object(handler, 'handleError') as mock_handle_error:
            logger.addHandler(handler)

            # 触发日志，这将导致 emit 失败
            logger.info("This log should cause an error.")

            # 验证 handleError 被调用
            mock_handle_error.assert_called_once()
            record = mock_handle_error.call_args[0][0]
            assert record.exc_info is not None
            assert isinstance(record.exc_info[1], ClogWriteError)
            assert "模拟写入失败" in str(record.exc_info[1])

        handler.close()
        # 验证 handler 在关闭时也调用了 writer 的 close
        mock_writer_instance.close.assert_called_once()
