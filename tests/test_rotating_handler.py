# pyclog/tests/test_rotating_handler.py
import logging
import os
from pyclog import ClogRotatingFileHandler, ClogReader, constants

def test_rotating_handler_rollover(tmp_path):
    """测试 ClogRotatingFileHandler 在真实场景下是否正确执行轮转。"""
    log_file = tmp_path / "rotate_test.clog"

    handler = ClogRotatingFileHandler(
        log_file,
        maxBytes=1000,
        backupCount=2,
        compression_code=constants.COMPRESSION_NONE
    )

    logger = logging.getLogger("test_rotate_final")
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(handler)

    for i in range(10):
        logger.info(f"Log message {i} with a lot of padding to ensure file size increases significantly - AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    handler.close()

    # --- 断言 ---
    assert os.path.exists(log_file), "当前日志文件应该存在"
    assert os.path.exists(f"{log_file}.1"), "备份文件 .1 应该存在"

    # 验证备份文件的内容
    with ClogReader(f"{log_file}.1") as reader:
        records = list(reader.read_records())
    
    assert len(records) == 5, f"备份文件应该有 5 条记录, 实际有 {len(records)}"
    assert "Log message 0" in records[0][2], "备份文件的第一条记录应该是 message 0"
    assert "Log message 4" in records[4][2], "备份文件的最后一条记录应该是 message 4"

    # 验证当前日志文件的内容
    with ClogReader(log_file) as reader:
        current_records = list(reader.read_records())

    assert len(current_records) == 5, f"当前日志文件应该有 5 条记录, 实际有 {len(current_records)}"
    assert "Log message 5" in current_records[0][2], "当前文件的第一条记录应该是 message 5"
    assert "Log message 9" in current_records[-1][2], "当前文件的最后一条记录应该是 message 9"