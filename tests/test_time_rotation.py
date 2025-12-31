
import unittest
import os
import shutil
import tempfile
import time
import logging
from pyclog import ClogTimedRotatingFileHandler, constants, ClogReader

class TestTimeRotation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.test_dir, "test_time.clog")
        self.logger = logging.getLogger("test_time_rotation")
        self.logger.setLevel(logging.INFO)
        # 清理之前的 handler
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

    def tearDown(self):
        # 关闭所有 handler
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
        
        shutil.rmtree(self.test_dir)

    def test_rotation_seconds(self):
        # 设置每秒轮转，保留 3 个备份
        handler = ClogTimedRotatingFileHandler(
            self.log_file, when='S', interval=1, backupCount=3, compression_code=constants.COMPRESSION_NONE
        )
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # 写入初始日志
        self.logger.info("Log 1")
        time.sleep(1.1)
        self.logger.info("Log 2") # 应该触发第一次轮转
        time.sleep(1.1)
        self.logger.info("Log 3") # 应该触发第二次轮转
        time.sleep(1.1)
        self.logger.info("Log 4") # 应该触发第三次轮转

        handler.close()

        # 验证文件是否存在
        # 当前文件
        self.assertTrue(os.path.exists(self.log_file))
        
        # 备份文件
        files = os.listdir(self.test_dir)
        backups = [f for f in files if f.startswith("test_time.clog.") and f != "test_time.clog" and not f.endswith(".lock")]
        backups.sort()
        
        # 因为我们写了 4 条日志，触发了 3 次轮转
        # Log 1 -> archive
        # Log 2 -> archive
        # Log 3 -> archive
        # Log 4 -> current
        
        # 应该有 3 个备份文件
        self.assertEqual(len(backups), 3)

        # 验证内容 (简单的检查，确保没有完全丢失)
        # 读取当前文件
        with ClogReader(self.log_file) as reader:
            records = list(reader.read_records())
            self.assertEqual(len(records), 1)
            self.assertIn("Log 4", records[0][2])

if __name__ == '__main__':
    unittest.main()
