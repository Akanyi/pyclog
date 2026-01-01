# 开发文档

欢迎来到 `pyclog` 的开发文档！本文档旨在为所有希望理解、使用、贡献或扩展 `pyclog` 项目的开发者提供全面的指导。

`pyclog` 是一个 Python 包，提供简单易用的 API 来读写 `.clog` 文件，并与 Python 标准 `logging` 模块无缝集成。

## 项目结构

```text
pyclog/
├── pyclog/                 # 核心库
│   ├── __init__.py         # 模块导出
│   ├── constants.py        # 常量定义 (魔术字节、压缩代码等)
│   ├── exceptions.py       # 自定义异常
│   ├── reader.py           # ClogReader - 读取 .clog 文件
│   ├── writer.py           # ClogWriter - 写入 .clog 文件
│   ├── handler.py          # logging Handler 实现 (File/Rotating/TimedRotating)
│   ├── async_handler.py    # 异步日志处理器
│   ├── locking.py          # 跨进程文件锁
│   └── cli.py              # 命令行工具
├── tests/                  # 测试套件
│   ├── test_reader_writer.py
│   ├── test_writer.py
│   ├── test_cli.py
│   ├── test_cli_ext.py
│   ├── test_async.py
│   ├── test_locking.py
│   ├── test_rotating_handler.py
│   └── test_time_rotation.py
├── README.md
├── DEVELOPMENT.md
├── LICENSE
└── pyproject.toml
```

## 架构概览

```text
┌───────────────────────────────────────────────────────────────┐
│                    Python logging 模块                        │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│  ClogFileHandler / ClogRotatingFileHandler / ClogTimed...     │
│  AsyncClogHandler (后台线程包装)                               │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│                      ClogWriter                               │
│  • 缓冲区管理 (大小/记录数/时间触发刷新)                         │
│  • 压缩 (None/Gzip/Zstandard)                                 │
│  • 线程安全                                                    │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│                    .clog 文件格式                              │
│  [Header 16B] [Chunk1] [Chunk2] ... [ChunkN]                  │
└───────────────────────────────────────────────────────────────┘
```

## 如何贡献

### 报告 Bug

如果您发现 Bug，请通过 [GitHub Issues](https://github.com/Akanyi/pyclog/issues) 提交一个 Issue。在报告 Bug 时，请提供以下信息：

- **重现步骤**：详细说明如何重现 Bug。
- **预期行为**：您期望发生什么。
- **实际行为**：实际发生了什么。
- **环境信息**：您的操作系统、Python 版本以及 `pyclog` 版本。
- **错误消息**：任何相关的错误消息或堆栈跟踪。

### 提出新功能或改进

如果您有新功能或改进的建议，请通过 [GitHub Issues](https://github.com/Akanyi/pyclog/issues) 提交一个 Issue。请详细描述您的想法，包括：

- **问题描述**：您希望解决什么问题。
- **解决方案建议**：您认为如何解决这个问题。
- **用例**：说明您的建议将如何被使用。

### 提交代码

我们欢迎代码贡献！请遵循以下步骤：

1. **Fork 仓库**：在 GitHub 上 Fork `pyclog` 仓库。
2. **克隆仓库**：将 Fork 后的仓库克隆到本地：

   ```bash
   git clone https://github.com/your-username/pyclog.git
   cd pyclog
   ```

3. **创建分支**：为您的贡献创建一个新的分支。请使用有意义的名称，例如 `feature/your-feature-name` 或 `bugfix/issue-number`。

   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **设置开发环境**：

   - 确保您安装了 **Python 3.10+**。
   - 安装依赖：

     ```bash
     pip install -e .[test,zstandard]
     ```

5. **编写代码**：

   - 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 编码规范。
   - 为您的代码添加文档字符串（遵循 [PEP 257](https://www.python.org/dev/peps/pep-0257/)）。
   - 为新功能或 Bug 修复编写测试。

6. **运行测试**：在提交之前，请确保所有测试都通过：

   ```bash
   pytest
   ```

7. **提交更改**：

   ```bash
   git add .
   git commit -m "feat: Add your feature" # 或 "fix: Fix your bug"
   ```

   请使用清晰简洁的提交消息。我们推荐使用 [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) 规范。

8. **推送到您的 Fork**：

   ```bash
   git push origin feature/your-feature-name
   ```

9. **创建 Pull Request (PR)**：

   - 在 GitHub 上，导航到您的 Fork 仓库，然后点击 "New pull request" 按钮。
   - 确保您的 PR 目标是 `pyclog` 仓库的 `main` 分支。
   - 提供清晰的 PR 描述，说明您的更改、解决了哪个 Issue（如果适用）以及任何其他相关信息。
   - 请确保您的 PR 通过了所有 CI/CD 检查。

## 编码规范

- **文档字符串**：所有模块、类、函数和方法都应包含符合 [PEP 257](https://www.python.org/dev/peps/pep-0257/) 规范的文档字符串。
- **类型提示**：尽可能使用 [类型提示](https://docs.python.org/3/library/typing.html)。
- **常量命名**：在 `constants.py` 中定义所有魔法数字和配置常量。

## 许可证

通过贡献到 `pyclog`，您同意您的贡献将根据项目的 [LICENSE](LICENSE) 文件进行许可。

再次感谢您的贡献！
