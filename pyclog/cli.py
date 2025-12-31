
import argparse
import json
import gzip
import os
import sys
import contextlib
import re
from .reader import ClogReader
from .exceptions import ClogReadError, InvalidClogFileError, UnsupportedCompressionError

try:
    import zstandard as zstd
except ImportError:
    zstd = None

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

def handle_export(args):
    """处理导出命令"""
    input_file = args.input
    output_file = args.output
    output_format = args.format
    output_compression = args.compress

    try:
        with ClogReader(input_file) as reader:
            with open_output_stream(output_file, output_compression) as output_stream:
                
                first_record = True
                
                if output_format == "json":
                    output_stream.write('[\n') # 开始 JSON 数组
                    
                    for timestamp, level, message in reader.read_records():
                        if not first_record:
                            output_stream.write(',\n')
                        
                        record = {
                            "timestamp": timestamp,
                            "level": level,
                            "message": message.replace('\v', '\n')
                        }
                        # 直接写入 JSON 字符串
                        output_stream.write('  ' + json.dumps(record, ensure_ascii=False))
                        first_record = False
                        
                    output_stream.write('\n]') # 结束 JSON 数组
                
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

    except Exception as e:
        _handle_error(e, input_file)

def handle_tail(args):
    """处理 tail 命令"""
    file_path = args.file
    n_lines = args.lines
    follow = args.follow
    
    try:
        with ClogReader(file_path) as reader:
            # 优化实现：使用 reader.tail() 快速读取最后 N 行
            # 这比全量读取要快得多，尤其是对于大文件
            last_records = reader.tail(n_lines)
            
            for timestamp, level, message in last_records:
                padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                aligned_message = message.replace('\v', '\n' + padding)
                print(f"{timestamp}|{level}|{aligned_message}")
            
            if follow:
                # 刷新 stdout 确保用户看到历史日志
                sys.stdout.flush()
                
                # 继续读取
                # 再次调用 read_records(follow=True) 即可继续从当前 file 指针位置（EOF）开始尝试读取
                for timestamp, level, message in reader.read_records(follow=True):
                    padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                    aligned_message = message.replace('\v', '\n' + padding)
                    print(f"{timestamp}|{level}|{aligned_message}")
                    sys.stdout.flush()

    except Exception as e:
        _handle_error(e, file_path)
    except KeyboardInterrupt:
        sys.exit(0)

def handle_grep(args):
    """处理 grep 命令"""
    file_path = args.file
    pattern = args.pattern
    ignore_case = args.ignore_case
    
    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    
    try:
        regex = re.compile(pattern, flags)
        with ClogReader(file_path) as reader:
            for timestamp, level, message in reader.read_records():
                 # 构造完整行用于匹配
                 padding = ' ' * (len(timestamp) + 1 + len(level) + 1)
                 aligned_message = message.replace('\v', '\n' + padding)
                 line = f"{timestamp}|{level}|{aligned_message}"
                 
                 # 如果匹配成功，输出
                 if regex.search(line):
                     print(line)

    except Exception as e:
        _handle_error(e, file_path)
    except KeyboardInterrupt:
        sys.exit(0)

def _handle_error(e, filepath):
    """统一错误处理"""
    if isinstance(e, FileNotFoundError):
        print(f"错误: 无法打开文件 '{filepath}': 文件不存在。", file=sys.stderr)
        sys.exit(1)
    elif isinstance(e, (ClogReadError, InvalidClogFileError, UnsupportedCompressionError, ValueError)):
        print(f"处理 .clog 文件时发生错误: {e}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"发生未预期的错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="pyclog 命令行工具 - 导出、查看和搜索 .clog 日志文件。"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # Export Command
    parser_export = subparsers.add_parser('export', help='导出 .clog 文件')
    parser_export.add_argument('--input', '-i', required=True, help='输入 .clog 文件')
    parser_export.add_argument('--output', '-o', required=True, help='输出文件')
    parser_export.add_argument('--format', '-f', choices=['json', 'text'], default='text', help='输出格式')
    parser_export.add_argument('--compress', '-c', choices=['none', 'gzip', 'zstd'], default='none', help='输出压缩')
    parser_export.set_defaults(func=handle_export)

    # Tail Command
    parser_tail = subparsers.add_parser('tail', help='实时查看日志')
    parser_tail.add_argument('file', help='输入 .clog 文件')
    parser_tail.add_argument('-n', '--lines', type=int, default=10, help='显示最后 N 行')
    parser_tail.add_argument('-f', '--follow', action='store_true', help='实时追踪新日志')
    parser_tail.set_defaults(func=handle_tail)

    # Grep Command
    parser_grep = subparsers.add_parser('grep', help='搜索日志内容')
    parser_grep.add_argument('pattern', help='正则表达式模式')
    parser_grep.add_argument('file', help='输入 .clog 文件')
    parser_grep.add_argument('-i', '--ignore-case', action='store_true', help='忽略大小写')
    parser_grep.set_defaults(func=handle_grep)

    # Legacy Arguments (Global)
    # 为了兼容 `pyclog -i ...`，我们在主 parser 添加可选参数，并设为非必填
    # 这样 parse_args 不会报错，在后面手动逻辑判断
    parser.add_argument('--input', '-i', help=argparse.SUPPRESS) 
    parser.add_argument('--output', '-o', help=argparse.SUPPRESS)
    parser.add_argument('--format', '-f', choices=['json', 'text'], help=argparse.SUPPRESS)
    parser.add_argument('--compress', '-c', choices=['none', 'gzip', 'zstd'], help=argparse.SUPPRESS)

    # 如果没有任何参数，打印帮助
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if args.command:
        # 子命令模式
        args.func(args)
    else:
        # 遗留模式检查
        if args.input and args.output:
            # 应用默认值
            if not args.format: args.format = 'text'
            if not args.compress: args.compress = 'none'
            
            handle_export(args)
        else:
            # 如果没有子命令也不符合遗留模式（例如只输了 -i 没有 -o），
            # 提示错误，打印帮助
            if args.input or args.output:
                 print("Error: Legacy export requires both --input/-i and --output/-o.", file=sys.stderr)
            parser.print_help()
            sys.exit(1)

if __name__ == "__main__":
    main()
