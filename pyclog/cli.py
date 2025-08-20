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

def open_output_file(filepath, compression_format):
    """
    根据压缩格式打开输出文件并返回文件对象。
    """
    if compression_format == "none":
        return open(filepath, "w", encoding="utf-8")
    elif compression_format == "gzip":
        return gzip.open(filepath, "wt", encoding="utf-8")
    elif compression_format == "zstd":
        if zstd is None:
            raise UnsupportedCompressionError("Zstandard 压缩不可用，因为 'python-zstandard' 库未安装。")
        # 对于 Zstandard，我们需要一个二进制文件对象来写入压缩数据
        return open(filepath, "wb")
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
            output_file_obj = open_output_file(output_file, output_compression)
            
            first_record = True
            
            if output_format == "json":
                # 对于 Zstandard 压缩的 JSON，需要流式写入
                if output_compression == "zstd":
                    cctx = zstd.ZstdCompressor()
                    # 对于 Zstandard 压缩的 JSON，我们需要将整个 JSON 数组作为单个流进行压缩
                    # 这意味着我们不能在压缩流中手动添加 '[' 和 ']'
                    # 而是需要先构建完整的 JSON 字符串，然后一次性压缩
                    # 这与流式处理的初衷相悖，但对于 JSON 数组的有效性是必要的
                    # 否则，每个 JSON 对象都会被单独压缩，解压后无法直接形成一个有效的 JSON 数组
                    # 因此，对于 Zstandard 压缩的 JSON，我们暂时回退到先收集再压缩的方案
                    # 这是一个权衡，因为 Zstandard 的 stream_writer 期望的是连续的未压缩数据流
                    # 而 JSON 数组的结构（逗号分隔和方括号）使得直接流式压缩每个对象变得复杂
                    json_strings = []
                    for timestamp, level, message in reader.read_records():
                        record = {
                            "timestamp": timestamp,
                            "level": level,
                            "message": message.replace('\v', '\n')
                        }
                        json_strings.append(json.dumps(record, ensure_ascii=False))
                    
                    full_json_array = "[" + ",".join(json_strings) + "]"
                    compressed_bytes = cctx.compress(full_json_array.encode('utf-8'))
                    output_file_obj.write(compressed_bytes)
                else:
                    output_file_obj.write('[') # 开始 JSON 数组
                    for timestamp, level, message in reader.read_records():
                        if not first_record:
                            output_file_obj.write(',')
                        record = {
                            "timestamp": timestamp,
                            "level": level,
                            "message": message.replace('\v', '\n')
                        }
                        output_file_obj.write(json.dumps(record, ensure_ascii=False))
                        first_record = False
                    output_file_obj.write(']') # 结束 JSON 数组
            
            elif output_format == "text":
                # 对于 Zstandard 压缩的 TEXT，需要先收集所有文本行再压缩
                if output_compression == "zstd":
                    text_lines = []
                    for timestamp, level, message in reader.read_records():
                        padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                        aligned_message = message.replace('\v', '\n' + padding)
                        text_lines.append(f"{timestamp}|{level}|{aligned_message}")
                    
                    full_text_content = "\n".join(text_lines)
                    cctx = zstd.ZstdCompressor()
                    compressed_bytes = cctx.compress(full_text_content.encode('utf-8'))
                    output_file_obj.write(compressed_bytes)
                else:
                    for timestamp, level, message in reader.read_records():
                        if not first_record:
                            output_file_obj.write('\n')
                        
                        padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                        aligned_message = message.replace('\v', '\n' + padding)
                        output_file_obj.write(f"{timestamp}|{level}|{aligned_message}")
                        first_record = False
            
            # stream_writer 会自动关闭底层文件对象，但为了确保所有情况下的文件关闭，我们将其放在 finally 块中
        
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
    finally:
        if 'output_file_obj' in locals() and not output_file_obj.closed:
            output_file_obj.close()
            
if __name__ == "__main__":
    main()
