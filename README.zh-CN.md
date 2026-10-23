# MathResearch Ledger

为长期数学研究 Agent 提供持久研究状态、上下文、依赖追踪与验证层。

MathResearch Ledger 不是另一个研究 Agent runtime。外部 Agent 负责研究；Ledger 保留可跨会话
恢复的研究状态。用 Codex 或其他 Harness 推理、阅读和实验，下次会话继续使用同一份研究记录。

[English](README.md) · [1.2.0 更新记录](CHANGELOG.md)

## 为什么需要研究 Ledger？

长期证明往往跨越很多会话。聊天摘要容易丢失前提、重复失败路线，或引用依赖已变化的结论。
Ledger 将 Problem、Claim、Gap、证明、反例、失败尝试及其来源、版本和 checkpoint 持久保存。

- **明确恢复研究：**找回指定 Problem 的 primary target、open gaps 和最新有意义的 checkpoint。
- **有选择地恢复上下文：**精确 ID、有限预算 packet 与原文分页，避免每次加载全部历史。
- **追踪依赖变化：**qualified identity 和版本 pin 区分 current、stale、unknown 前提。
- **保留真实进展：**先 preview Research Episode，再保存原文及 provisional 对象；下一步计划保持 advisory。
- **区分证据与权威：**review、verification、canonicalization 和人工 acceptance 各有独立职责。

## 五分钟开始

需要 **Python 3.11+**。从源码安装：

```powershell
git clone https://github.com/Caie777/math-research-ledger.git
cd math-research-ledger
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[mcp]'
math-research-ledger --workspace 'C:\Research\MyProject' init
math-research-ledger --workspace 'C:\Research\MyProject' ledger create-problem 'My question' 'State the question and assumptions here.'
math-research-ledger --workspace 'C:\Research\MyProject' status
```

macOS/Linux 用 `source .venv/bin/activate` 激活，并换成自己的研究目录。
workspace 必须在工具仓库之外，由用户显式初始化。init 创建空状态、workspace.yaml、研究 AGENTS.md，
保留已有指令和普通文件，不创建 demo 研究对象。上面的 create-problem 创建用户显式指定的问题。

也可从 [GitHub Releases](https://github.com/Caie777/math-research-ledger/releases) 下载 wheel，
用 `python -m pip install './math_research_ledger-1.2.0-py3-none-any.whl[mcp]'` 安装。
接着按 [Codex 安装指南](docs/codex-mcp.md) 安装插件，在研究项目启用并新开会话。
安装与启用是两步；普通项目可关闭。独立 MCP client 可用 stdio 启动
`math-research-ledger-mcp --workspace '<research-workspace>'`，MCP 不会初始化缺失的工作区。
兼容 CLI 别名 `smr`、`math-research`、`smr-mcp` 和 Python import `math_research` 保留。

## 最小续研流程

**Free research by default; memory intervention by exception.**
默认自由研究，只有记忆可能影响决策时才介入。

1. 显式调用 `research_status(problem_id="PROBLEM-0001")`；开发版 MCP 须预先在启动时绑定 workspace。
   检查 primary target、gaps、风险、checkpoint 和 advisory handoff。
2. 用 `research_get_object` 精确读目标，再调用
   `research_context_packet(ref="<qualified target>", purpose="CONTINUE_RESEARCH", token_budget=8000)`。
   检查 omission、truncation、freshness 与 premise eligibility。
3. 连续局部推导自由进行。切换主要路线、复用关键前提、怀疑重复失败路线或遇到历史冲突时，做最小 scoped retrieval。
4. 有值得保存的进展后，准备 [Research Episode](docs/research-episode.md)：
   Confirmed Research Increment 与 advisory Next Research Directions 分开。
   `research_ingest_episode(dry_run=true)` 预检，修正 ERROR、理解 WARNING，授权后单次 ingest。
   下一会话再从 Ledger 恢复。

示例 ID 必须替换成真实对象的 ID/ref。相关性不等于可信前提；使用前核对对象、版本、来源和验证证据。
保留完整证明与失败路线，不逐轮记录聊天，也不每步重建 context。

## 九个 MCP 工具

| 工具 | 职责 |
|---|---|
| `research_status` | Problem 状态、续研导航与计数 |
| `research_search` | 有界相关性检索或精确身份定位 |
| `research_get_object` | 精确对象、来源与原文分页 |
| `research_context_packet` | 为指定目标恢复预算内上下文 |
| `research_review_packet` | 版本固定的 advisory review 材料 |
| `research_stale_report` | 依赖与版本漂移 |
| `research_ingest_episode` | 预检或摄入 provisional checkpoint |
| `research_save_note` | 少量重要的独立 provisional 增量 |
| `research_request_acceptance` | 请求人工接受，不能执行接受 |

MCP Episode Markdown 每次最多 **128,000 字符**；底层文件摄入与响应上限见
[Episode 合同](docs/research-episode.md)。工具不暴露 shell、任意文件写入、编译器执行或人工接受操作。

## 信任模型与工作区所有权

`checked != accepted`；`canonical != verified`。soft review 是 advisory，freshness 是当前派生状态，
历史 receipt 保留。ingest 仍是 provisional；source-reported revision 不会自动改写 canonical 对象。

人工 acceptance 不在模型可调用的 MCP surface 中，由服务端执行**工作流边界**。
这不是针对任意本地代码或文件系统访问的认证或沙箱边界；human CLI 属于可信通道。
见[架构与 authority](docs/architecture.md)、[验证](docs/formalization-v0.md)。

Harness 拥有 workspace，用户拥有普通文件，Ledger 只拥有 `.math-research-ledger/`。
该目录、workspace.yaml、研究 AGENTS.md 保持 local-only。Ledger 不自动 git add、commit、push，
也不决定哪些研究可以公开。可选 notes repo 仅发布用户主动选定的成果。
见 [workspace、迁移及 Git 本地排除](docs/research-workspaces.md)。工具升级不重写历史 provenance。

## 集成与限制

- **Core Ledger、CLI、九个 MCP 工具、Codex：**有自动化测试与已记录的集成验证。
  [Codex 指南](docs/codex-mcp.md) 说明原生启停和项目范围；GitHub 发布不代表已上架公开插件目录。
- **DeepSeek Harness：experimental。**[原生 Bundle](integrations/deepseek-harness/README.md)
  复用同一 Python 服务和 Ledger。历史隔离 Host 测试已通过，但真实 Windows 既有工作区验收
  仍受报告中的 Low/Medium Integrity 边界阻塞；macOS/Linux DSH Host 未验收。
  插件不会修改 ACL、完整性标签、认证或切换 Full Access。

[已知限制与 1.2.1 待审事项](docs/known-limitations.md) 明确当前边界。本版不新增 Agent loop、
模型路由或第二套研究数据库。开发命令见 [English README](README.md)；
[历史工程报告](docs/archive/2026-10/README.md) 已与长期用户文档分开。
