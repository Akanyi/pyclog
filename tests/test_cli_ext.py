
import unittest
import os
import shutil
import tempfile
import threading
import time
import subprocess
import sys
from pyclog import ClogFileHandler, ClogReader, constants

class TestCLIExtensions(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.test_dir, "test_cli.clog")
        self.handler = ClogFileHandler(self.log_file, compression_code=constants.COMPRESSION_NONE)
        # 预先写入一些数据
        for i in range(20):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"Message {i}", None, None)
            record.created = time.time()  # Ensure timestamp is set
            self.handler.emit(record)
        self.handler.close()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run_cli(self, args, timeout=5):
        """Helper to run CLI command"""
        cmd = [sys.executable, "-m", "pyclog.cli"] + args
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            timeout=timeout,
            env=env
        )
        return result

    def test_tail_n(self):
        """Test 'tail -n' behavior"""
        # 期望：只输出最后 5 行
        result = self._run_cli(["tail", "-n", "5", self.log_file])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn("Message 19", lines[-1])
        self.assertIn("Message 15", lines[0])

    def test_grep_pattern(self):
        """Test 'grep' behavior"""
        # 期望：只输出匹配 "Message 1" 的行 (1, 10-19) -> 共 11 行
        result = self._run_cli(["grep", "Message 1", self.log_file])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 11)
        self.assertIn("Message 1", lines[0])
        self.assertIn("Message 10", lines[1])

    def test_legacy_mode(self):
        """Test backward compatibility (default export)"""
        output_file = os.path.join(self.test_dir, "legacy_export.txt")
        result = self._run_cli(["-i", self.log_file, "-o", output_file])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(output_file))

    def test_tail_follow(self):
        """Test 'tail -f' behavior"""
        # 这个测试比较 trick，需要启动子进程后，主进程再写文件
        
        # 1. 启动 tail -f 子进程
        cmd = [sys.executable, "-m", "pyclog.cli", "tail", "-f", "-n", "0", self.log_file]
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1, # Line buffered
            env=env
        )

        try:
            # 2. 等待子进程启动
            time.sleep(1)
            
            # 3. 写入新日志
            handler = ClogFileHandler(self.log_file, compression_code=constants.COMPRESSION_NONE)
            record = logging.LogRecord("test", logging.INFO, "", 0, "New Follow Message", None, None)
            record.created = time.time()
            handler.emit(record)
            handler.close()

            # 4. 读取子进程输出 (通过 timeout 避免死等)
            # 注意：readline 可能会阻塞，这里简单起见用 communicate 的 timeout
            # 但 communicate 会等待进程结束，所以不能直接用。
            # 我们尝试读一行
            output_line = process.stdout.readline()
            
            self.assertIn("New Follow Message", output_line)

        finally:
            process.terminate()
            process.wait()

import logging
