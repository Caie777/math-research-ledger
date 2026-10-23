# P0-3：明确续研入口与固定 continuity 评测

> Historical engineering evidence; results refer to the recorded revision, not a new acceptance.
> Machine-specific locations are generalized. See [current limitations](../../known-limitations.md).

2026-10-22；本地工作树工程。所有命令执行目录：`<repo>`。
基线为 P0-2 的 269 passed；既有修改、未跟踪文件和构建证据保留。
本轮不处理 DSH、embedding、模型 reranker、UI、自动研究 loop 或数学研究。

## 最小 continuation contract

`research_status(problem_id=...)` 是有限导航，不是全文上下文。

| 字段 | 契约 |
|---|---|
| explicit_problem_id / selection_required | 显式选择生效；未选择时不采用 `.current` 猜测，continuation=null |
| primary_target | Problem 已指定的主目标 qualified ref、version、authority/check/freshness/integrity/premise flags；缺失则明确诊断，不选“最近 Claim”代替 |
| problem_status / object_count / counts | 当前 scoped 对象、open gaps、失败路线、counterexample/refutation、UNKNOWN/STALE/integrity failed 等数量 |
| open_gaps / failed_routes / counterexamples_refutations / risk_objects | 各最多四个状态导航卡，附 omission 数；不复制证明/失败正文 |
| premise_categories | trusted formal、conditional、historical-only、blocked positive 的计数和有限 refs；这些分类可能重叠 |
| latest_meaningful_checkpoint | 已发布对象/源声明的最近可信原文入口；ADVISORY，不授予数学权威 |
| latest_advisory_handoff | 最近可读取的 handoff/directions 入口；读取原文后重新检查引用对象 |
| continuation_snapshot / changes | 最多 16 个优先 refs 的状态指纹；可传回 since，最多比较 32 refs |
| recommended_next_calls | 仅 get exact main target / context packet 导航；没有数学研究方向建议 |

无显式 Problem 时仍提供原有分页 Problem/object 列表，让调用者选择。
九个工具不增加；research_status 仅新增可选 since map，其他分页工具不接收该字段。

状态指纹包括 version、semantic state、authority、verification、freshness、integrity 和 premise flags。
因此 reject 等不改变原始 Proposal 内容的状态变化也可检测。
没有 caller baseline 时返回 NO_BASELINE，不把“无法知道上次会话”说成“没有变化”。
比较只覆盖提供的 refs；缺失/alias 改变明确 ABSENT_OR_ALIASED，不等于已证明被删除。
不建立另一个快照数据库、不自动存储会话、不把 source-reported state_delta 当实际 canonical diff。

## 轻干预 memory policy

**Free research by default; memory intervention by exception.**

Default to free research. Query Ledger when memory is likely to materially affect the next decision.
Do not search the Ledger every reasoning turn.

| 事件 | 最小操作 |
|---|---|
| 新会话 | 显式 Problem 的 status；exact target / context restore 一次 |
| 连续局部推导 | 默认零 Ledger 调用，使用已恢复上下文 |
| 路线切换、重复风险、历史失败、昂贵分支前 | 针对当前决策的 scoped search；需要原文时再 exact get |
| 前提复用、冲突 | 对具体 qualified ref 检查当前版本、authority 与 premise flags |
| 有意义变化的 checkpoint | 完整 Episode preview；修正 ERROR、判断 WARNING；单次 ingest |

没有每 N 轮强制存储。4–6 个 substantive turns 后检查是否有值得保存的变化，只是 advisory fallback；
没有变化就不写 Episode。Agent 自己选择下一条研究路线，Ledger 只供记忆和安全边界。

`retrieval/memory_policy.py` 是无状态的事件指引，不发起调用、不计轮数、不调度 Agent。
相同指引写入 `core/research_agents.md` 的新 workspace 模板。没有改真实 workspace 的 AGENTS.md，
也没有更新用户已安装的插件缓存或强制修改旧 workspace 指令。

## Context complete 的兼容语义

schema_version=1 和 complete 保留；新增 required_set_complete（与 complete 始终一致）、
semantic_scope=computed_required_set_only、omitted_categories 与 continuation_coverage。
完整只代表当前算法计算出的 required 集合满足预算与原文要求，绝不表示完整数学研究状态已恢复。
全历史、未选择路线、未请求对象仍可能遗漏。额外 metadata 计入同一个 JSON token 预算。
截断正文仍撤销 positive/trusted flags；未放宽 P0-1/P0-2 的 currentness、authority 或 integrity gate。

## Latest checkpoint / handoff

在明确 Problem 内按 `(imported_at, episode_id)` 倒序选择。
排除固定 digest 失败、SOURCE_DIGEST advisory、已知重复 local IDs；
meaningful checkpoint 必须有已发布的非 relation 对象正文或 typed source assertion。
只有 raw 或规划的归档不替换最近研究增量；更新的纯 advisory handoff 可单独导航。
handoff 使用现有 reserved-heading reader / 已保存 next directions，不借 LLM 判断重要性。
导航不包含路线内容，也不把手写 handoff 当今日真值。

这不是对所有历史文档重新跑 P0-2 lint，亦非“最大数学价值”选择。
规则描述既有 publication 的操作意义；历史新规范诊断和来源损坏仍是不同概念。

## 冻结合成集与方法

[benchmark](../../../benchmarks/continuity/README.md) 固定 18 个双语任务、三种策略和 2k/8k/16k 预算。
任务输入与 gold 单独存放，固定 SHA-256 由回归测试检查；生产源码不导入任何 benchmark/gold。
没有将 fixture IDs、真实 IDs 或 gold 加进生产 ranker，未修改 BM25 权重。

内容覆盖 explicit target、错误 `.current`、多个 gap、latest checkpoint、CURRENT unverified、
UNKNOWN、STALE、refuted、rejected、conditional、历史 accepted 后漂移、损坏原文、
失败路线、中英查询、counterexample/refutation、相同词汇/局部 ID 的跨 scope 干扰、no-match、
无关历史来源、预算截断与 checkpoint。

每种预算创建一个合成 seed，A/B/C 分别复制相同 bytes，之后独立执行相同外部 definition drift。
真正调用 LedgerAdapter，统计 tool calls 和输出；没有 mock retrieval、模型回合或真实数学研究。

- A Heavy：每个非 checkpoint 阶段 search + context；前提决策另作 exact get。
- B Session-only：仅开局恢复，直到 checkpoint 不再读取。
- C Event-triggered：开局恢复；事件触发具体 search/exact get；连续推导不调用。

指标包括选题/主目标、四个 gold MUST identity recall、五个 key memory refs recall@10、
负面记忆覆盖、不安全 positive premise、缺少判断依据的决策、无关来源误召回与跨 scope 泄漏，
以及各任务真实调用数、bytes、packet estimated tokens、MUST/SHOULD/MAY、omission/truncation。
缺少依据不能伪装成已完成的安全检查；reference recall 不代表完整正文已读。

## 证据与结果

本轮完整 pytest **300 collected / 300 passed / 0 skipped / 0 failed，547.38 秒，退出 0**。
比 P0-2 增加 31 项：27 项 continuation/policy/候选只读合同，4 项冻结 benchmark 测试
（其中三项各执行一种预算下全部策略）。先有四项失败回归，再实现服务合同。
Ruff check、Ruff format（127 文件）、`python -m mypy`（93 源文件）及 `git diff --check` 均退出 0。
直接运行本机 mypy.exe 曾无输出退出 1；使用同一虚拟环境的 `python -m mypy` 实际完成检查。
完整 pytest 在获准支持本地 IPC 的普通用户执行环境运行，无提权、无真实 DSH Host。

固定 18 任务 × 3 策略 × 3 预算，共 162 个任务观察，9 次独立 replay。
所有策略、预算的 selected Problem / main target / latest checkpoint 正确，MUST identity 为 4/4，
跨 Problem 错误返回为零。以下 calls 包含开局 status/context 与结尾 preview/ingest：

| 预算 | 策略 | calls | key refs@10 | 负面记忆 | unsafe positive | 安全证据覆盖 | 输出 bytes |
|---|---|---:|---:|---:|---:|---:|---:|
| 2k | A Heavy | 46 | 5/5 | 4/4 | 0 | 7/7 | 235052 |
| 2k | B Session-only | 4 | 0/5 | 0/4 | 1 | 1/7 | 16325 |
| 2k | C Event-triggered | 18 | 5/5 | 4/4 | 0 | 7/7 | 64146 |
| 8k | A | 46 | 5/5 | 4/4 | 0 | 7/7 | 536073 |
| 8k | B | 4 | 0/5 | 4/4 | 1 | 5/7 | 35491 |
| 8k | C | 18 | 5/5 | 4/4 | 0 | 7/7 | 83312 |
| 16k | A | 46 | 5/5 | 4/4 | 0 | 7/7 | 548932 |
| 16k | B | 4 | 0/5 | 4/4 | 1 | 6/7 | 40950 |
| 16k | C | 18 | 5/5 | 4/4 | 0 | 7/7 | 88771 |

key refs@10 计对应任务 search 的 top 10，B 没有执行这些查询，故为零；
负面记忆计当时 memory 中已有对应 identity，8k/16k 的 B 能靠开局 packet 恢复四个负面 refs。
这两个指标不等价；不能据此断言 B 完全没读过这些对象。
unsafe 是回放缓存仍许可无条件 positive-working 的次数，不是观察真实模型使用前提的次数。
B 三档均漏掉接受后上游 definition 漂移，保留一个旧 positive 标签。
A/C 各有一个预期的完整性错误（拒读损坏原文）；B 未读取它，不算安全验收成功。

| 预算 | 策略 | packet 数 / 对象数 | MUST/SHOULD/MAY 总数 | tokens 总计 / 单包最大 | required omissions / 截断项 |
|---|---|---|---|---|---|
| 2k | A | 18 / 72 | 72/0/0 | 34330 / 1945 | 0 / 0 |
| 2k | B、C | 1 / 4 | 4/0/0 | 1877 / 1877 | 0 / 0 |
| 8k | A | 18 / 346 | 72/148/126 | 130150 / 8000 | 0 / 1 |
| 8k | B、C | 1 / 21 | 4/12/5 | 7983 / 7983 | 0 / 0 |
| 16k | A | 18 / 358 | 72/154/132 | 134239 / 9708 | 0 / 0 |
| 16k | B、C | 1 / 27 | 4/15/8 | 9708 / 9708 | 0 / 0 |

packet 对象数含重复读取；required omissions 仅是 required_omitted_ids，不能代表全历史没有省略。
三个 local reasoning 任务中 A 总计 6 calls、B/C 为零。
C 对 A 少 28/46（60.9%）调用，输出 bytes 分别少 72.7% / 84.5% / 83.8%，
同时保留本合成集的主要安全与负面记忆收益。因此支持轻干预假设的**有限工程证据**成立，
没有证明真实研究中任何事件检测方式、预算或查询都得到同样收益。

重复失败路线风险是缺少四个指定负面 refs 的代理指标：B/2k 为 4，其他为零，
不代表已经观测到 Agent 真正重复实验。A/C 的 no-match 为 1/1，B 未执行，不能记为通过。
A/C 每种预算都误召回一个无关历史来源；保留原 gold 负标签，不为了变绿重标或泄漏给 ranker。
跨 scope 的错误返回与同 scope 的相关性误召回分开记分，后者仍是待改进的 relevance 问题。
没有为了本轮指标改 ranker；正文特别长的预算截断由独立回归另行覆盖。

本地忽略的工程证据：`<local-evidence>` 下的
`full.log`、`full.xml`、`full.exitcode`、`mypy.log`、三份 `full-temp/**/benchmark.json`。
JSON 包含各任务调用参数、结果、memory 快照和完整指标，均来自合成 workspace。
这些运行产物与 `.venv` 不提交，不重建或宣称刷新 DSH Bundle / 已安装插件缓存。

## 真实 P1 待标注候选

在合成评测和完整回归通过后，从选定 PROBLEM-0001 的 canonical metadata 准备 **6 条**候选。
只导出 refs、query、record status、已有 dependency IDs；不复制数学陈述/证明/标题/正文。
gold/relevance_labels 保持 null、annotation_status=PENDING_HUMAN，不自动作正确性或相关性判断。
输出位于忽略的 `<local-evidence>`。
公开仓库仅保留通用脚本和合成测试，不保留该私有候选 JSON。

执行 `scripts/prepare_continuity_candidates.py` 退出 0；审计 hook 将研究目录读取限于指定 Problem，
阻止研究目录写入，拒绝输出到研究 workspace 或覆盖旧输出。
选定 Problem 子树 33 文件读取前后 SHA-256 一致；这不是整个 Ledger 的重新扫描或全局事务快照。
未读取 notes、其他 Problems、`.current` 或全 corpus Episode，不运行 MCP status、锁、预检或补 pin。
未修改真实 corpus；没有要求用户本轮立即人工标注。

## 解释边界与 vertical slice

这是 deterministic evidence-exposure benchmark，不是先进模型真实续研效果证明。
事件标签由 fixture 给定；若真实 Agent 错过 premise reuse 或路线切换，C 也可能漏查。
会话中途外部修改只演示一种 drift，不覆盖所有长期研究方式。
双语任务使用一般研究语言和双语合成记录，不代表任意数学公式/语义改写召回。
token 是现有 UTF-8 估算，bytes 是 adapter JSON 输出，不是模型 token 计费或 SDK wire 流量。

真实 P1 只准备 refs/query/必要 metadata 的候选，gold/relevance 留空，需研究者未来人工标注。
候选集不能自动宣布主张正确、路线重复或哪段证明重要，也不要求用户本轮标注。
不重跑真实 Episode lint、不补 pins、不迁移、不读 notes，不进行 real model/DSH Host 验收。
可以据工程结果决定是否安排受控的第一轮 vertical slice；真正开展研究和写 checkpoint 仍需用户另行授权。

**当前判断：已具备安排受控 Codex vertical slice 的工程前提，尚未证明真实续研效果。**
下一轮先由用户授权研究/写 checkpoint，并明确刷新当前源码对应的插件运行环境；
恢复明确 Problem、主目标和一个真实 Gap，人工冻结少量 relevance/MUST labels，
核对前提再研究、preview 后单次 ingest、下一会话盲恢复。不要依赖本轮未更新的旧安装包。
DSH Windows 验收仍冻结，不是开始该受控 Codex 实验的前提。

## 本轮文件与保留边界

本轮修改七个既有文件：

- `src/math_research/services/research.py`
- `src/math_research/mcp/adapter.py`
- `src/math_research/retrieval/packet.py`
- `src/math_research/core/research_agents.md`
- `README.md`
- `README.zh-CN.md`
- `docs/core-product-audit-2026-10-22.md`（本轮开始时已是未跟踪文件）

本轮新增十四个文件：

- `src/math_research/ledger/continuation.py`
- `src/math_research/retrieval/memory_policy.py`
- `tests/core_contracts/test_continuation.py`
- `tests/core_contracts/test_continuity_benchmark.py`
- `scripts/evaluate_continuity.py`
- `scripts/prepare_continuity_candidates.py`
- `benchmarks/__init__.py`
- `benchmarks/continuity/__init__.py`
- `benchmarks/continuity/corpus.py`
- `benchmarks/continuity/evaluate.py`
- `benchmarks/continuity/tasks.json`
- `benchmarks/continuity/gold.json`
- `benchmarks/continuity/README.md`
- `docs/p0-continuity-evaluation-2026-10-22.md`

既有 P0-1/P0-2/DSH 修改和未跟踪文件保留，不改核心数据格式、审核门禁、Codex 插件清单/Skills。
本轮不 add、commit、push、不访问 remote、不打包真实数据。
最终 main HEAD 为 `60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，未暂存；
合并此前积累的工作树共 35 tracked modifications、38 untracked files。
baseline SHA 审计未发现既有文件丢失或本轮范围外的内容变化；
证据快照在最初四项 red tests 建立后采集，因此该新测试在快照比较中显示为 changed，不是历史既有测试。
本轮变更文本未发现匹配的凭据值、私钥或私人用户 home；该模式审计不是任意秘密识别保证。
真实候选 JSON 与所有工程产物确认被 dist ignore 规则排除，未复制到公开文件。
