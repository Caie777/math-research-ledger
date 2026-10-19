# Structured Math Research

[English](README.md) | [简体中文](README.zh-CN.md)

一个面向长期数学研究的本地工作空间：

**结构化记忆 → 检索 / 上下文构建 → 长程 Research Agent**

让数学研究过程可追溯，并从结构化研究状态中继续工作。

## 核心能力

- **Structured Research Memory：** 归档 Research Episodes，审阅拟议的 Claims、Proofs、Gaps 和失败尝试。模型输出在 Human Review 前均为待确认内容。
- **Retrieval / Context Construction：** 检索已有工作，结合来源与研究状态构建有长度限制的上下文。
- **长程 Research Agent：** 显式启动、停止和恢复有预算限制的研究任务，保留 checkpoint 和公开进展。

## 快速开始

Windows：Python 3.11+，以及 Node.js 20.19+ 或 22.12+。

```powershell
git clone https://github.com/Caie777/structured-math-research.git
cd structured-math-research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[openai,anthropic]"
npm --prefix web ci
.\start.bat
```

之后双击 `start.bat` 即可启动。它会在需要时构建前端、初始化缺失的工作空间，
启动本地后端并打开浏览器。请保持诊断控制台开启；Ctrl+C 可停止服务。
如果端口被占用，可使用 `start.bat --port 8001`。服务仅绑定本机回环接口。

手动启动：先运行 `npm --prefix web run build` 构建前端，再运行
`math-research init` 初始化，最后在已激活的环境中运行 `math-research serve`。

## 模型配置

打开 **Research Settings → Models**，为 `coordinator` 和 `research` 选择自己的模型；
`cheap_semantic` 为预留角色。Web 支持的传输方式包括 OpenAI、Anthropic、Mistral 和本地 Ollama。
云端 provider 使用**你自己的 API 凭据**。

Settings 中的密钥仅可写入，保存在本地已被 Git 忽略的 `.local/` 中，不进入研究记忆。
保存配置不会调用模型。浏览、确定性查询和 Episode 导入无需配置模型；模型操作需要先完成配置。

**Codex/operator 是可选入口：** 需显式选择，使用你自己已安装并登录的 Codex CLI
及适用的产品额度，无需 API key。Web API 角色不共享 Codex 订阅凭据。

## 使用方式

1. 创建一个 Problem，导入小型[合成 Episode](examples/demo_research_episode.md)，或在 **Import Research Episode** 中粘贴自己的 Markdown。确认导入前先预览。
2. 审阅提案以建立正式记忆。向 Coordinator 输入 `/portfolio`、`/state P1` 或 `/recall square` 查看已有工作；`/import` 可打开导入界面。
3. 选择尚未解决的 Claim/Gap，显式启动 Research Agent。在 **Progress** 中查看进展，按需停止，或按原有预算恢复中断的 run。

研究数据保存在已被 Git 忽略的 `.math-research/` 中；请勿公开研究数据或凭据。
审阅决定和生成的证明不构成形式化验证证书。

## 架构

```text
Episode → deterministic parsing → Proposals → Human Review → Memory
                                                           ↓
                                              Retrieval / Context
                                                           ↓
                                                 Research Agent
                                                           ↓
                                                Episode + Progress
```

React 使用同源 `/api/*`；FastAPI 提供构建后的 Web 应用和本地研究服务。
模型角色通过现有 provider 传输方式解析。代码位于 `src/math_research/` 和 `web/src/`。

运行小型离线核心测试：先执行 `python -m pip install -e ".[dev]"`、`python -m pytest`，
再执行 `npm --prefix web test`。模型使用 mock。采用 [Apache-2.0](LICENSE) 许可证。
