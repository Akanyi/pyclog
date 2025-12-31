
import unittest
import os
import shutil
import tempfile
import logging
import time
from pyclog import ClogFileHandler, AsyncClogHandler, ClogReader, constants

class TestAsyncLogging(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.test_dir, "test_async.clog")
        self.logger = logging.getLogger("test_async")
        self.logger.setLevel(logging.INFO)
        
        # Setup handlers
        self.target_handler = ClogFileHandler(self.log_file, compression_code=constants.COMPRESSION_NONE)
        self.target_handler.setFormatter(logging.Formatter('%(message)s'))
        
        self.async_handler = AsyncClogHandler(self.target_handler)
        self.logger.addHandler(self.async_handler)

    def tearDown(self):
        self.async_handler.close() # 这应该会停止 listener 并关闭 target_handler
        self.logger.removeHandler(self.async_handler)
        shutil.rmtree(self.test_dir)

    def test_async_write(self):
        msg = "Async log message"
        self.logger.info(msg)
        
        # 由于是异步的，我们等待一小会儿确保后台线程处理了队列
        # QueueListener 是基于 block=True 的，应该很快
        time.sleep(0.5)
        
        # 强制停止以刷新
        self.async_handler.stop()
        
        # 验证文件内容
        self.assertTrue(os.path.exists(self.log_file))
        with ClogReader(self.log_file) as reader:
            records = list(reader.read_records())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0][2], msg)

if __name__ == '__main__':
    unittest.main()
