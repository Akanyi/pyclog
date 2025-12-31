# pyclog

`pyclog` 是一个 Python 包，提供简单易用的 API 来读写 `.clog` 文件，并与 Python 标准 `logging` 模块无缝集成。

[Github](https://github.com/Akanyi/pyclog)

## `.clog` 文件格式

`.clog` 文件旨在提供一种高效、可流式处理的日志存储格式，支持压缩以节省空间。

### 核心设计思想

* **文件头 (Header)**: 用于快速识别文件类型、版本和压缩算法。
* **数据块 (Chunk)**: 将多条日志记录组合在一起进行压缩，以获得高压缩率。
* **流式处理**: 可以一条一条地写入，也可以一个块一个块地读取，无需将整个文件加载到内存。

### 文件结构

```code
[ File Header (16 bytes) ]
[ Chunk 1 ]
[ Chunk 2 ]
...
[ Chunk N ]
```

#### 1. 文件头 (File Header) - 固定16字节

| 偏移量 (Bytes) | 长度 (Bytes) | 字段名 | 描述 |
| :--- | :--- | :--- | :--- |
| 0-3 | 4 | Magic Bytes | 固定的 `b'CLOG'` (0x43, 0x4C, 0x4F, 0x47)，用于快速识别文件类型。 |
| 4 | 1 | Format Version | 格式版本号，例如 `\x01` 代表版本1。 |
| 5 | 1 | Compression Code | 压缩算法代码。`\x00`: 无压缩, `\x01`: Gzip, `\x02`: Zstandard。 |
| 6-15 | 10 | Reserved | 保留字节，用 `\x00` 填充，为未来扩展预留。 |

#### 2. 数据块 (Chunk) - 变长

每个数据块由 **块头 (Chunk Header)** 和 **块数据 (Chunk Data)** 组成。

| 组成分 | 长度 (Bytes) | 字段名 | 描述 |
| :--- | :--- | :--- | :--- |
| 块头 | 4 | Compressed Size | 块数据的压缩后字节数。 |
| | 4 | Uncompressed Size | 块数据解压后的原始字节数。 |
| | 4 | Record Count | 这个块中包含的日志记录条数。 |
| 块数据 (压缩) | Compressed Size | Compressed Log Data | 多条日志记录序列化后，使用文件头中指定的压缩算法进行压缩得到的数据。 |

#### 3. 块内日志记录的序列化

**记录结构**: `timestamp<FIELD_DELIMITER>level<FIELD_DELIMITER>message<RECORD_DELIMITER>`

* **字段分隔符**: 默认为制表符 `\t` (`b'\t'`)。
* **记录分隔符**: 默认为换行符 `\n` (`b'\n'`)。
* **多行消息处理**: 为了可靠地分隔记录，日志消息体内的所有换行符 `\n` 会被内部替换为垂直制表符 `\v`。在读取或导出时，`\v` 会被自动转换回 `\n`，从而完整保留多行日志的格式。

## 安装

**基础安装 (支持 Gzip 和无压缩):**

```bash
pip install pyclog
```

**安装并支持 Zstandard 压缩:**
`pyclog` 使用可选依赖来支持 Zstandard 压缩。

```bash
pip install 'pyclog[zstandard]'
```

>*在某些 shell (如 zsh) 中，你可能需要使用引号来防止方括号被解释*

## 使用示例

### 写入 `.clog` 文件

`ClogWriter` 是线程安全的。它内部使用缓冲区来优化写入性能，可以通过 `buffer_flush_size` (字节大小) 和 `buffer_flush_records` (记录数) 参数进行调整。

```python
from pyclog import ClogWriter, constants
from pyclog.exceptions import UnsupportedCompressionError

# 使用 gzip 压缩写入
with ClogWriter("my_log.clog", compression_code=constants.COMPRESSION_GZIP) as writer:
    writer.write_record("INFO", "这是一个信息日志。")
    writer.write_record("WARNING", "这是一个警告日志，带有特殊字符：!@#$%^&*()")
    # 支持多行日志
    writer.write_record("ERROR", "发生了一个错误。\n这是错误的第二行。")

# 使用无压缩写入 (用于调试)
with ClogWriter("my_debug_log.clog", compression_code=constants.COMPRESSION_NONE) as writer:
    writer.write_record("DEBUG", "这是调试日志。")

# 如果安装了 zstandard 依赖，可以使用 Zstandard 压缩
try:
    with ClogWriter("my_zstd_log.clog", compression_code=constants.COMPRESSION_ZSTANDARD) as writer:
        writer.write_record("INFO", "这是 Zstandard 压缩的日志。")
except UnsupportedCompressionError as e:
    print(f"错误: {e}. 请运行 'pip install pyclog[zstandard]' 来安装支持。")
```

### 读取 `.clog` 文件

```python
from pyclog import ClogReader

with ClogReader("my_log.clog") as reader:
    for timestamp, level, message in reader.read_records():
        # 读取时，多行日志的换行符会被自动还原
        print(f"[{timestamp}] [{level}] {message}")
```

### 与 Python `logging` 模块集成

#### 基本用法 (`ClogFileHandler`)

`pyclog` 可以无缝替换标准的 `logging.FileHandler`。

**重要提示**: `ClogFileHandler` 会自动处理时间戳和日志级别。因此，传递给它的 `logging.Formatter` 应该只包含消息本身，例如 `logging.Formatter('%(message)s')`，以避免信息重复。

```python
import logging
from pyclog import ClogFileHandler, constants

logger = logging.getLogger("my_app")
logger.setLevel(logging.INFO)

# 创建 ClogFileHandler 实例
handler = ClogFileHandler("app.clog", compression_code=constants.COMPRESSION_GZIP)

# 设置日志格式 (关键：只格式化消息本身)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# 记录日志
logger.info("应用程序启动。")
logger.warning("发现一个潜在问题。")
logger.error("处理请求时发生异常。", exc_info=True)

handler.close()
```

#### 日志轮转 (`ClogRotatingFileHandler`)

`pyclog` 还提供了 `ClogRotatingFileHandler`，它增加了基于文件大小的日志轮转功能，类似于 `logging.handlers.RotatingFileHandler`。

```python
import logging
import time
from pyclog import ClogRotatingFileHandler, constants

logger = logging.getLogger("my_rotating_app")
logger.setLevel(logging.DEBUG)

# 创建 ClogRotatingFileHandler 实例
# 当文件大小接近 256 字节时进行轮转，最多保留 3 个备份文件。
handler = ClogRotatingFileHandler(
    "rotating_app.clog",
    mode='w',
    maxBytes=256,
    backupCount=3,
    compression_code=constants.COMPRESSION_GZIP
)

formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# 记录日志直到触发轮转
for i in range(20):
    logger.info(f"这是第 {i+1} 条测试日志。")
    time.sleep(0.01)

handler.close()
print("日志已写入并根据需要进行了轮转。")
```

## 命令行工具 (CLI)

`pyclog` 提供了一个命令行工具，用于将 `.clog` 文件导出为其他格式（JSON 或纯文本），并支持对输出文件进行压缩。

**基本用法：**

```bash
pyclog --input <input_file.clog> --output <output_file> [--format <json|text>] [--compress <none|gzip|zstd>]
```

**参数说明：**

* `--input`, `-i`：**必需**。要读取的 `.clog` 文件路径。
* `--output`, `-o`：**必需**。导出文件的输出路径。
* `--format`, `-f`：导出格式。`json` 或 `text`。默认为 `text`。
  * `json`：将日志导出为 JSON 对象数组。
  * `text`：将日志导出为 `时间戳|日志级别|日志消息` 格式的纯文本，并对多行日志进行智能对齐。
* `--compress`, `-c`：导出文件的压缩格式。`none`, `gzip`, `zstd`。默认为 `none`。
  * 选择 `zstd` 需要安装 `zstandard` 库。

**示例：**

1. **将 `.clog` 文件导出为纯文本文件：**

    ```bash
    pyclog -i my_log.clog -o my_log.txt -f text
    ```

2. **将 `.clog` 文件导出为 Gzip 压缩的 JSON 文件：**

    ```bash
    pyclog -i my_log.clog -o my_log.json.gz -f json -c gzip
    ```

3. **将 `.clog` 文件导出为 Zstandard 压缩的 JSON 文件：**

    ```bash
    pyclog -i my_log.clog -o my_log.json.zst -f json -c zstd
    ```

## 开发与贡献

欢迎贡献！请确保安装开发和测试所需的依赖。

**设置开发环境:**

```bash
# 克隆仓库
git clone https://github.com/Akanyi/pyclog.git
cd pyclog

# 以可编辑模式安装包，并包含 test 和 zstandard 依赖
pip install -e .[test,zstandard]
```

**运行测试:**

```bash
pytest
```

## 许可证

本项目根据 [MIT 许可证](LICENSE) 发布。
