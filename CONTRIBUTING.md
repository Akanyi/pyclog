# 贡献指南

感谢您对 `pyclog` 项目的兴趣！我们欢迎并感谢所有形式的贡献，无论是报告 Bug、提出新功能、改进文档还是提交代码。

请花一些时间阅读以下指南，以确保您的贡献能够顺利地被采纳。

## 行为准则

我们致力于为每个人提供一个开放和包容的环境。

## 如何贡献

### 报告 Bug

如果您发现 Bug，请通过 [GitHub Issues](https://github.com/Akanyi/pyclog/issues) 提交一个 Issue。在报告 Bug 时，请提供以下信息：

* **重现步骤**：详细说明如何重现 Bug。
* **预期行为**：您期望发生什么。
* **实际行为**：实际发生了什么。
* **环境信息**：您的操作系统、Python 版本以及 `pyclog` 版本。
* **错误消息**：任何相关的错误消息或堆栈跟踪。

### 提出新功能或改进

如果您有新功能或改进的建议，请通过 [GitHub Issues](https://github.com/Akanyi/pyclog/issues) 提交一个 Issue。请详细描述您的想法，包括：

* **问题描述**：您希望解决什么问题。
* **解决方案建议**：您认为如何解决这个问题。
* **用例**：说明您的建议将如何被使用。

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
    * 确保您安装了 Python 3.8+。
    * 安装依赖：

        ```bash
        pip install -e .
        pip install -r requirements-dev.txt # 如果有开发依赖文件
        ```

5. **编写代码**：
    * 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 编码规范。
    * 为您的代码添加文档字符串（遵循 [PEP 257](https://www.python.org/dev/peps/pep-0257/)）。
    * 为新功能或 Bug 修复编写测试。
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

    * 在 GitHub 上，导航到您的 Fork 仓库，然后点击 "New pull request" 按钮。
    * 确保您的 PR 目标是 `pyclog` 仓库的 `main` 分支。
    * 提供清晰的 PR 描述，说明您的更改、解决了哪个 Issue（如果适用）以及任何其他相关信息。
    * 请确保您的 PR 通过了所有 CI/CD 检查。

## 编码规范

* **文档字符串**：所有模块、类、函数和方法都应包含符合 [PEP 257](https://www.python.org/dev/peps/pep-0257/) 规范的文档字符串。
* **类型提示**：尽可能使用 [类型提示](https://docs.python.org/3/library/typing.html)。

## 许可证

通过贡献到 `pyclog`，您同意您的贡献将根据项目的 [LICENSE](LICENSE) 文件进行许可。

再次感谢您的贡献！
