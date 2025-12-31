import argparse
import json
import gzip
import os
import sys

try:
    import zstandard as zstd
except ImportError:
    zstd = None

from .reader import ClogReader
from . import constants
from .exceptions import ClogReadError, InvalidClogFileError, UnsupportedCompressionError

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
            records = []
            for timestamp, level, message in reader.read_records():
                records.append({
                    "timestamp": timestamp,
                    "level": level,
                    "message": message
                })

        output_data = ""
        if output_format == "json":
            # JSON格式会正确处理 \n，但我们的内部表示是 \v，需要转换回来
            for record in records:
                record['message'] = record['message'].replace('\v', '\n')
            output_data = json.dumps(records, indent=2, ensure_ascii=False)

        elif output_format == "text":
            output_lines = []
            for r in records:
                timestamp = r['timestamp']
                level = r['level']
                message = r['message']
                
                # 为多行日志的对齐计算所需的填充
                padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                
                # 将内部换行符 \v 替换为真正的换行符和对齐填充
                aligned_message = message.replace('\v', '\n' + padding)
                
                output_lines.append(f"{timestamp}|{level}|{aligned_message}")
            
            output_data = "\n".join(output_lines)

        if output_compression == "none":
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(output_data)
        elif output_compression == "gzip":
            with gzip.open(output_file, "wt", encoding="utf-8") as f:
                f.write(output_data)
        elif output_compression == "zstd":
            cctx = zstd.ZstdCompressor()
            compressed_bytes = cctx.compress(output_data.encode('utf-8'))
            with open(output_file, "wb") as f:
                f.write(compressed_bytes)

        print(f"成功将 '{input_file}' 导出到 '{output_file}' (格式: {output_format}, 压缩: {output_compression})。")

    except FileNotFoundError:
        print(f"错误: 输入文件 '{input_file}' 未找到。", file=sys.stderr)
        sys.exit(1)
    except (ClogReadError, InvalidClogFileError, UnsupportedCompressionError) as e:
        print(f"读取 .clog 文件时发生错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"发生意外错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()