# pyclog/cli.py

import argparse
import json
import gzip
import os
import sys
import contextlib
import io

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from .reader import ClogReader
from . import constants
from .exceptions import ClogReadError, InvalidClogFileError, UnsupportedCompressionError

class TextToBytesWrapper:
    """
    一个简单的包装器，将字符串写入转换为 UTF-8 编码的字节写入。
    用于适配 zstandard 的 stream_writer (只接受字节)。
    """
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        if isinstance(data, str):
            return self.stream.write(data.encode('utf-8'))
        return self.stream.write(data)
    
    def flush(self):
        if hasattr(self.stream, 'flush'):
            self.stream.flush()

@contextlib.contextmanager
def open_output_stream(filepath, compression_format):
    """
    根据压缩格式打开输出流的上下文管理器。
    始终产生一个接受字符串的 file-like 对象 (TextIO)。
    """
    if compression_format == "none":
        f = open(filepath, "w", encoding="utf-8")
        try:
            yield f
        finally:
            f.close()
            
    elif compression_format == "gzip":
        f = gzip.open(filepath, "wt", encoding="utf-8")
        try:
            yield f
        finally:
            f.close()
            
    elif compression_format == "zstd":
        if zstd is None:
            raise UnsupportedCompressionError("Zstandard 压缩不可用，因为 'python-zstandard' 库未安装。")
        
        f = open(filepath, "wb")
        try:
            cctx = zstd.ZstdCompressor()
            with cctx.stream_writer(f) as compressor:
                # 包装为文本写入接口
                yield TextToBytesWrapper(compressor)
        finally:
            f.close()
            
    else:
        raise ValueError(f"不支持的压缩格式: {compression_format}")

def main():
    parser = argparse.ArgumentParser(
        description="将 .clog 文件导出为 JSON 或纯文本格式。"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="要读取的 .clog 文件路径。"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="导出文件的输出路径。"
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        choices=["json", "text"],
        default="text",
        help="导出格式：'json' 或 'text'。默认为 'text'。"
    )
    parser.add_argument(
        "--compress",
        "-c",
        type=str,
        choices=["none", "gzip", "zstd"],
        default="none",
        help="导出文件的压缩格式：'none' (不压缩), 'gzip', 'zstd'。默认为 'none'。"
    )

    args = parser.parse_args()

    input_file = args.input
    output_file = args.output
    output_format = args.format
    output_compression = args.compress

    if output_compression == "zstd" and zstd is None:
        print("错误: 选择了 Zstandard 压缩，但 'python-zstandard' 库未安装。", file=sys.stderr)
        sys.exit(1)

    try:
        with ClogReader(input_file) as reader:
            with open_output_stream(output_file, output_compression) as output_stream:
                
                first_record = True
                
                if output_format == "json":
                    output_stream.write('[') # 开始 JSON 数组
                    
                    for timestamp, level, message in reader.read_records():
                        if not first_record:
                            output_stream.write(',')
                        
                        record = {
                            "timestamp": timestamp,
                            "level": level,
                            "message": message.replace('\v', '\n')
                        }
                        # 直接写入 JSON 字符串
                        output_stream.write(json.dumps(record, ensure_ascii=False))
                        first_record = False
                        
                    output_stream.write(']') # 结束 JSON 数组
                
                elif output_format == "text":
                    for timestamp, level, message in reader.read_records():
                        # 对于第一条记录之后的每一条，先写入换行符
                        if not first_record:
                            output_stream.write('\n')
                        
                        padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                        aligned_message = message.replace('\v', '\n' + padding)
                        # 逐行写入
                        output_stream.write(f"{timestamp}|{level}|{aligned_message}")
                        first_record = False
        
        print(f"成功将 '{input_file}' 导出到 '{output_file}' (格式: {output_format}, 压缩: {output_compression})。")

    except FileNotFoundError:
        print(f"错误: 输入文件 '{input_file}' 未找到。", file=sys.stderr)
        sys.exit(1)
    except (ClogReadError, InvalidClogFileError, UnsupportedCompressionError, ValueError) as e:
        print(f"处理 .clog 文件时发生错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"发生意外错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
