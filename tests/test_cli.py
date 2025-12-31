import unittest
import os
import sys
import tempfile
import shutil
import json
import gzip
import io 
import argparse 
from unittest.mock import patch

try:
    import zstandard as zstd
except ImportError:
    zstd = None

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pyclog.cli import main as cli_main, handle_export
from pyclog.writer import ClogWriter
from pyclog import constants

class TestCli(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.input_clog_path = os.path.join(self.test_dir, "test.clog")
        self.output_file_path = os.path.join(self.test_dir, "output")

        # 创建一个用于测试的 .clog 文件
        with ClogWriter(self.input_clog_path, compression_code=constants.COMPRESSION_NONE) as writer:
            writer.write_record("INFO", "这是一条测试日志消息 1。")
            writer.write_record("WARNING", "这是第二条日志消息。")
            writer.write_record("ERROR", "第三条日志消息，包含一些特殊字符：!@#$%^&*()。")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run_cli(self, args):
        """辅助函数，用于运行 CLI main 函数并捕获 stdout/stderr"""
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
                with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(**args)):
                    try:
                        cli_main()
                    except SystemExit as e:
                        self.assertEqual(e.code, 0, f"CLI exited with error code {e.code}: {mock_stderr.getvalue()}")
                return mock_stdout.getvalue(), mock_stderr.getvalue()

    def test_export_to_text_none_compression(self):
        output_path = self.output_file_path + ".txt"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "text",
            "compress": "none",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("这是一条测试日志消息 1。", content)
            self.assertIn("这是第二条日志消息。", content)
            self.assertIn("第三条日志消息，包含一些特殊字符：!@#$%^&*()。", content)
            self.assertEqual(len(content.strip().split('\n')), 3)

    def test_export_to_json_none_compression(self):
        output_path = self.output_file_path + ".json"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "json",
            "compress": "none",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        with open(output_path, "r", encoding="utf-8") as f:
            content = json.load(f)
            self.assertEqual(len(content), 3)
            self.assertEqual(content[0]["level"], "INFO")
            self.assertIn("测试日志消息 1", content[0]["message"])
            self.assertEqual(content[2]["level"], "ERROR")
            self.assertIn("特殊字符", content[2]["message"])

    def test_export_to_text_gzip_compression(self):
        output_path = self.output_file_path + ".txt.gz"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "text",
            "compress": "gzip",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        with gzip.open(output_path, "rt", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("这是一条测试日志消息 1。", content)
            self.assertEqual(len(content.strip().split('\n')), 3)

    def test_export_to_json_gzip_compression(self):
        output_path = self.output_file_path + ".json.gz"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "json",
            "compress": "gzip",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        with gzip.open(output_path, "rt", encoding="utf-8") as f:
            content = json.load(f)
            self.assertEqual(len(content), 3)
            self.assertEqual(content[0]["level"], "INFO")

    @unittest.skipUnless(zstd, "python-zstandard 库安装")
    def test_export_to_text_zstd_compression(self):
        output_path = self.output_file_path + ".txt.zst"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "text",
            "compress": "zstd",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        dctx = zstd.ZstdDecompressor()
        with open(output_path, "rb") as f:
            with dctx.stream_reader(f) as reader:
                decompressed_content = reader.read().decode('utf-8')
        
        self.assertIn("这是一条测试日志消息 1。", decompressed_content)
        self.assertEqual(len(decompressed_content.strip().split('\n')), 3)

    @unittest.skipUnless(zstd, "python-zstandard 库未安装")
    def test_export_to_json_zstd_compression(self):
        output_path = self.output_file_path + ".json.zst"
        args = {
            "input": self.input_clog_path,
            "output": output_path,
            "format": "json",
            "compress": "zstd",
            "command": "export",
            "func": handle_export
        }
        stdout, stderr = self._run_cli(args)
        self.assertIn("成功将", stdout)
        self.assertTrue(os.path.exists(output_path))

        dctx = zstd.ZstdDecompressor()
        with open(output_path, "rb") as f:
            with dctx.stream_reader(f) as reader:
                decompressed_content = reader.read().decode('utf-8')
        
        content = json.loads(decompressed_content)
        self.assertEqual(len(content), 3)
        self.assertEqual(content[0]["level"], "INFO")

    def test_input_file_not_found(self):
        output_path = self.output_file_path + ".txt"
        args = {
            "input": "non_existent.clog",
            "output": output_path,
            "format": "text",
            "compress": "none",
            "command": "export",
            "func": handle_export
        }
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
                with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(**args)):
                    with self.assertRaises(SystemExit) as cm:
                        cli_main()
                    self.assertEqual(cm.exception.code, 1)
                    error_msg = mock_stderr.getvalue()
                    self.assertIn("处理 .clog 文件时发生错误", error_msg)
                    self.assertIn("无法打开文件", error_msg)
                    self.assertIn("non_existent.clog", error_msg)

    def test_invalid_clog_file(self):
        # 创建一个无效的 .clog 文件
        invalid_clog_path = os.path.join(self.test_dir, "invalid.clog")
        with open(invalid_clog_path, "wb") as f:
            f.write(b"NOTCLOGFILE") # 无效的魔术字节，并且长度不足

        output_path = self.output_file_path + ".txt"
        args = {
            "input": invalid_clog_path,
            "output": output_path,
            "format": "text",
            "compress": "none",
            "command": "export",
            "func": handle_export
        }
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
                with patch('argparse.ArgumentParser.parse_args', return_value=argparse.Namespace(**args)):
                    with self.assertRaises(SystemExit) as cm:
                        cli_main()
                    self.assertEqual(cm.exception.code, 1)
                    # 对于这个特定的测试文件，正确的错误应该是“文件太短”
                    self.assertIn("文件太短，无法读取完整的 .clog 文件头", mock_stderr.getvalue())

if __name__ == '__main__':
    unittest.main()
