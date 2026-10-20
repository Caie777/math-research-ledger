# Structured Math Research

本项目现在是 **Research Ledger + Retrieval/Context + Research Workflow + Verification/Authority system**。

```text
记录 → 有预算的上下文包 → Codex / Claude Code 等外部 Harness 研究
     → provisional Episode ingest → 审阅 / 检查 → 记录
```

不再运行自主 Agent、provider routing、compaction、自定义 sandbox、长期 orchestration 或 React/FastAPI 产品。

安装：`python -m pip install -e ".[dev]"`。入口 `smr`，`math-research` 为别名；未重装时用 `python -m math_research.cli`。

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
- 真正接受走可信 human CLI；formal acceptance 要求 correspondence。MCP 只提供 request_acceptance。
- freshness 根据版本/依赖派生，历史 receipt 保留。
- context 预算覆盖 compact JSON；MUST/SHOULD/MAY、缺失及截断显式报告。连必需身份/authority 都放不下时明确报错。

MCP 已有可选 stdio skeleton 和有界 adapter；真实 SDK transport 需要在启用环境做 smoke test。详情见 [架构和兼容性](docs/architecture.md)、[Episode 格式](docs/research-episode.md)、[Lean checker](docs/formalization-v0.md)。
