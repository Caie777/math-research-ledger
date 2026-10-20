# Structured Math Research

本项目现在是 **Research Ledger + Retrieval/Context + Research Workflow + Verification/Authority system**。

```text
记录 → 有预算的上下文包 → Codex / Claude Code 等外部 Harness 研究
     → provisional Episode ingest → 审阅 / 检查 → 记录
```

不再运行自主 Agent、provider routing、compaction、自定义 sandbox、长期 orchestration 或 React/FastAPI 产品。

正常聊天入口是 Codex，经 MCP 查询和记录研究状态。当前机器已注册 `structured-math-research`；在项目中打开新的 Codex 会话，直接说“继续 PROBLEM-0001 的研究，先了解目前做到哪里”即可。工具参数由 Codex 选择，无需手工拼接。

一次性安装/注册见 [README](README.md#use-from-codex)；用 `codex mcp list` 和 `codex mcp get structured-math-research --json` 检查配置。CLI 与 IDE/desktop 共用配置，但旧会话需要重新启动；本次真实 host 调用仅在 Codex CLI 完成，desktop 尚未独立验证。详细证据见 [MCP 接入](docs/codex-mcp.md)。

以下 CLI 仅用于 debug 和可信 human authority fallback。入口 `smr`，`math-research` 为别名；未重装时用 `python -m math_research.cli`。

```sh
smr --workspace <项目目录> ledger list
smr --workspace <项目目录> ledger show PROBLEM-0001:claim:CLAIM-0001
smr --workspace <项目目录> search "研究问题" --problem PROBLEM-0001
smr --workspace <项目目录> context export PROBLEM-0001:claim:CLAIM-0001 --budget 8000
smr --workspace <项目目录> ingest episode PROBLEM-0001 output.md --provenance "外部 Harness/session"
smr --workspace <项目目录> review packet PROBLEM-0001:claim:CLAIM-0001
smr --workspace <项目目录> acceptance pending
smr --workspace <项目目录> stale report
```

示例 ID 必须替换为实际记录。所有入口调用共享 deterministic services。

- 保留领域 typed models；manifest 统一暴露 scoped ref、content hash、version、依赖、provenance、artifacts 和独立状态。
- 不迁移历史 ID。旧 YAML/JSONL/Markdown 直接读取；新 collections 位于 additive ledger/。
- canonical 不等于 verified；checked 不等于 accepted；working premise 不等于 trusted formal premise。
- Soft Review 永远 advisory；NO_GAP_FOUND 不会授予 authority。
- 真正接受走可信 human CLI；formal acceptance 要求 correspondence。MCP 只提供 `research_request_acceptance`。
- freshness 根据版本/依赖派生，历史 receipt 保留。
- context 预算覆盖 compact JSON；MUST/SHOULD/MAY、缺失及截断显式报告。连必需身份/authority 都放不下时明确报错。

MCP 使用九个顶层 `research_*` tools，各自附有 description 和 JSON schema，无 generic dispatcher。Episode 和单条 note 仅 stage provisional candidates，复用原 Proposal Store。输出（含 SDK text/structured 双份表示）限制在 64 KiB 内，错误结构化返回。没有 model-callable accept、shell、任意 filesystem 或 compiler。workspace 按 `--workspace` → `SMR_WORKSPACE` → cwd 向上发现的顺序解析，不自动 init。详情见 [架构和兼容性](docs/architecture.md)、[Episode 格式](docs/research-episode.md)、[Lean checker](docs/formalization-v0.md)。
