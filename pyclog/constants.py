# pyclog/constants.py

# 文件头 (File Header) 常量
MAGIC_BYTES = b'CLOG'  # 固定的 b'CLOG' (0x43, 0x4C, 0x4F, 0x47)
FORMAT_VERSION_V1 = b'\x01'  # 格式版本号

# 压缩算法代码
COMPRESSION_NONE = b'\x00'  # 无压缩 (用于调试)
COMPRESSION_GZIP = b'\x01'  # Gzip 压缩
COMPRESSION_ZSTANDARD = b'\x02'  # Zstandard 压缩

RESERVED_BYTES = b'\x00' * 10  # 保留字节，用 \x00 填充

# 块内日志记录的序列化格式
RECORD_DELIMITER = b'\n'  # 记录分隔符
FIELD_DELIMITER = b'\t'  # 字段分隔符
