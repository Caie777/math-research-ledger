# MathResearch Ledger

为长期数学研究 Agent 提供持久研究状态、上下文、依赖追踪与验证层。

MathResearch Ledger 不是另一个研究 Agent runtime。Codex、DeepSeek Harness 或其他
Harness 负责推理、文献阅读和实验；Ledger 负责研究状态、Research Episode/checkpoint
历史、精筛召回、版本/来源/依赖、下游失效、验证证据和人工权威边界。

默认关闭，需要时通过 Harness 原生 plugin UI/config 开启。关闭后不参与普通工具选择；
开启后根据任务调用九个稳定 research_* 工具，不需要每轮点名插件。
Python import 保留 `math_research`，避免破坏既有集成。

```powershell
python -m pip install -e '.[mcp]'
math-research-ledger --workspace 'D:\Math Research' init
```

正式 CLI 为 `math-research-ledger`；`smr`、`math-research` 是 legacy compatibility alias。
详见 [Codex 接入](docs/codex-mcp.md)、[DeepSeek 一次性 patch](integrations/deepseek-harness/README.md)。

Harness 拥有 workspace，用户拥有普通文件，Ledger 只管理 `.math-research-ledger/`。
init 幂等创建空状态、workspace.yaml 和 AGENTS.md，不创建假研究对象、不覆盖用户指令、
不移动或整理普通文件。papers/notes 仅是可选习惯。MCP 不自动初始化缺失 workspace。

私有状态、workspace.yaml 和研究 AGENTS.md 默认 local-only。Ledger 不自动 git add、
commit、push，也不决定公开哪些成果。用户独立 notes repo 只发布用户主动选定的成熟研究。
[Workspace 与显式迁移](docs/research-workspaces.md)。

继续研究先调用 research_status，再为实质工作获取 research_context_packet。
搜索相关性不等于证据或可信前提；使用前检查对象、版本、来源、freshness、authority 和 verification。

研究 hot path 保持轻量，在有意义的 checkpoint 一次 ingest 完整 Research Episode：
Confirmed Research Increment 记录 source-reported typed state_delta；Next Research Directions
永远 advisory。research_save_note 仅用于少量值得立即保留的单个结果/缺口/失败/证据，
不要每轮自动记忆。[Episode 合同](docs/research-episode.md)。

尽量保留、召回时精筛：原始 Episode、完整证明、失败尝试、反例、拒绝/延后路线、来源、
修订历史都保留。优先优化 retrieval、context budget 和 derived views，不激进删除历史。

- checked != accepted；canonical != verified。
- 模型不能给自己 authority；人工 acceptance 由服务端 gate 强制。
- soft review 是 advisory；stale 是当前派生状态，历史 receipt 保留。
- Episode 是状态增量；报告 Revised/Refuted/Invalidated 不自动修改 canonical 对象。
- 同一个 workspace ledger 可跨 Harness 和会话使用，不维护第二套状态。

开发与构建步骤见 [English README](README.md)，[本轮验收报告](docs/finalization-report.md)
区分自动测试、真实 host smoke 和未完成事项。项目由 standalone research-agent runtime
演进为 agent-agnostic ledger/tool layer。
仓库：[Caie777/math-research-ledger](https://github.com/Caie777/math-research-ledger)。
