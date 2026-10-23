# Vertical-slice continuity 加固

> Historical engineering evidence; results refer to the recorded revision, not a new acceptance.
> Machine-specific locations are generalized. See [current limitations](../../known-limitations.md).

2026-10-22。所有代码、测试、文档、Git 与配置审计命令执行目录：
`<repo>`。本轮不做数学研究、不 ingest、不操作 DSH、notes、
verification/human acceptance，不 add/commit/push。
既有未提交修改与未跟踪文件保留。

## 证据范围

问题输入来自用户提供的 Run 1/Run 2 摘要：Run 1 checkpoint 与三个产物的 IDs，
Run 2 的 status 1 / get_object 12 / context 4 / search 2，以及两次 read 参数错误和一次预算错误。
仓库现有 run1 文档仍是较早的 PREFLIGHT BLOCKED 记录，不冒充最终真实研究报告。
没有取得最终 Run 1/Run 2 的完整逐调用 trace；一次 app chat 列表读取未及时返回，已停止等待。
不改写既有运行历史来填补这一空白。下文区分用户提供的观察、源码复现和本轮新实验。

本地忽略证据位于 `<local-evidence>`。
该目录可能包含本地路径、配置备份和私有只读核验 metadata，不进入公开仓库/分发包。

## 1. 插件为何未手动选择仍可用

直接观察：用户级 `~/.codex/config.toml` 中
`[plugins."math-research-ledger@math-research-ledger-local"] enabled=true`。
审计时研究目录及 D 盘父级均没有项目 `.codex/config.toml`，也未发现对应项目 marketplace。
研究目录已有 trusted 记录；用户级未发现旧 MathResearch Ledger 全局 MCP server 条目。
`codex plugin list --marketplace math-research-ledger-local --json` 确认插件已安装、enabled=true：

- plugin ID：`math-research-ledger@math-research-ledger-local`。
- marketplace ID：`math-research-ledger-local`，来源是工具仓库忽略的本地 marketplace。
- 审计前安装版本：`1.1.0+vslice.20261022`。

因此，**已持久化的 user-level enable 是当前自动工具可用的直接配置原因，足以解释 Run 2 现象**。
不需要每次手动在输入框再次选择插件。没有 Run 2 当时的配置快照，不能倒推配置的最初写入者。
是否由先前 UI 选择写入、UI 还有何 session persistence、旧连接怎样被 Host 恢复，均为 UNKNOWN；
本轮不据这些未知机制修改配置。已安装也不等于一定启用，marketplace discovery 与 enable 是两步。

后续本轮实际观察到另一个持久化来源：成功执行 `codex plugin add` 刷新本地版本，会把该插件
user enabled 重新设为 true。安装后的配置断言捕获了这个变化，已仅恢复该开关为 false，
并重新核对其他用户配置不变。该安装器副作用是本轮直接观察，不等于已经证明 Run 2 的历史写入者。

官方支持 trusted project `.codex/config.toml` 覆盖 user defaults，CLI `-c` 的优先级更高。
见[配置优先级](https://learn.chatgpt.com/docs/config-file/config-basic)及
[插件 repo enable 配置](https://developers.openai.com/plugins/build/plugins)。
只对本地 marketplace 插件作这个判断，不推广到组织管理的所有插件类型。

### 本机无模型 Host 验证

全部使用新 Codex app-server、ephemeral thread、workspace-write，**没有调用研究工具或模型**。
没有通过 Full Access、管理员、ACL/MIC 变更获得结果。

| 阶段 / workspace | Ledger marker | 配置条件 | 实际 Ledger tools |
|---|---|---|---:|
| 修改前，隔离 ordinary | 无 | user enabled=true | 9 |
| 修改前，隔离 marker | 有（仅空标记目录） | user enabled=true | 9 |
| 修改前，隔离 project-off | 有 | project enabled=false | 0 |
| 修改后，隔离 ordinary | 无 | user enabled=false | 0 |
| 修改后，隔离 marker | 有 | user enabled=false | 0 |
| 修改后，真实研究项目 | 既有 | project enabled=true | 9 |

这个对照直接排除了“只因 `.math-research-ledger` 存在就激活插件”的解释。
Ledger 目录仅用于已启动服务的 workspace resolver，不是 Codex plugin discovery/activation marker。
研究项目的这项检查只发现工具，没有读取 Ledger 内容。

### 已实施的最小配置修改

按用户授权，先将用户配置完整备份到忽略目录 `codex-config.before.toml`，
再仅把该插件 user enabled 改为 false；新建 `<research-workspace>\.codex\config.toml`：

```toml
[plugins."math-research-ledger@math-research-ledger-local"]
enabled = true
```

解析前后 TOML 对比确认用户其他设置不变。没有卸载插件、改账号、改 trust_level 或 notes repo。
配置只控制新建/重新加载的有效连接；不宣称已经清除了所有旧会话的工具快照。
未来撤销应只调整该插件开关，不盲目用旧完整备份覆盖用户后续其他配置修改。

**Plugin availability does not imply per-turn memory access.**
**In research workspaces, Ledger may be available throughout the session while retrieval remains event-triggered.**
开局恢复一次，连续推导零调用；相关决策事件再查询，有实质增量才 preview + ingest。

## 2. Checkpoint → produced objects

新增共享 `ledger/publication.py`，仅派生读取已持久化的 Episode proposals/reviews，
复用 `ScopedIdentityResolver`，没有第二个身份库、正文重解析或 lexical search。
status 的 latest meaningful checkpoint 和 exact Episode read 复用同一导航合同：

- `produced_objects`：local_id、candidate_id、kind、publication_ref、当前 qualified_ref、version、
  authority、freshness、integrity、premise_eligibility 和 review_decision。
- `publication_ref` 保留原稳定工作身份；`qualified_ref` 可随已确认 canonical mapping 导航到当前身份。
- reject 保留原身份并明确 REJECTED/HISTORICAL、BLOCKED；defer 仍是 PROVISIONAL，不升权威。
- relation proposals 单独列出/count，不当作产生了数学对象。
- 没有持久 proposal mapping 的 legacy/raw-only Episode 返回
  `UNAVAILABLE_NO_PERSISTED_MAPPING`，不根据 RESULT-1 正文猜对象。
- 每类最多六条导航；exact Episode 的 `produced_offset` 与正文 `offset` 分开，返回 next offsets。
  status 只提供第一页与 total/omission，不塞正文或整个 Problem。

## 3. Exact ID navigation

`services/retrieval.py` 对整条 identifier-shaped query 或 qualified ObjectRef，先调用共享身份 resolver。
支持 Episode、candidate、canonical 和 stable IDs；candidate/旧稳定身份可跟随已确认 review alias。
唯一且在请求 scope 内解析成功时，返回 `retrieval_mode=EXACT_IDENTITY` 的一个 exact hit，
reason=EXACT_IDENTITY，不混入 lexical related history；失败/歧义才走原 BM25 + Recall。
没有为真实 P1 编号写规则，没有修改词法权重、embedding、gold 或模型路线。
匹配仅完成身份导航，不提升 verification/authority，也不绕过 source integrity 和 premise gates。

## 4. 状态表达修复

已复现源码缺陷：packet 将 `freshness != CURRENT` 一律标成 STALE，导致 UNKNOWN → STALE。
现在 UNKNOWN 原样作为显示 label；STALE 仅用于现有 freshness resolver 确认 drift 的情况。
`freshness`（版本可追溯性）、`research_state`（语义状态）、authority 和 premise eligibility 是独立轴。
REFUTED 可以仍 freshness=CURRENT、display=HISTORICAL、eligibility=BLOCKED；
UNKNOWN 也可以导致 BLOCKED，但不因此改成 STALE。

stale_report 的 object risks 改用与 status/get/search/context 相同的 authority-aware projection，
并明确 `object_scope=non_current_including_unknown_not_only_confirmed_drift`。
接口旧名保留；UNKNOWN 不是“确知漂移”，没有改 freshness 规则、历史 pins 或 research_state。
内部旧 `STALE_STATES` 是语义排除集合，不作为版本 freshness 输出；不把两者当同一指标。

## 5. 参数和分页

安全上限不变：read length 默认 4000、最大 8000 字符；offset 默认 0、非负。
context token_budget 默认/建议 8000，合法范围 256..16000，64 KiB envelope 不扩大。
schema 和 tool description 同时给出数字与分页方法，read 返回 next_offset、remaining、max_window。
正文已读完或 offset 超出末尾时 next_offset=null、remaining=0，不制造永远前进的空页。
publication 导航独立 produced_offset；工具不自动发起下一页请求。

## 6. Run 2 调用数与等价回放

真实汇总为 19 calls，但没有完整 trace，不能精确把所有成功调用归因到某个类别：

| 已知调用组 | 数量 | 可以支持的分类 |
|---|---:|---|
| status | 1 | necessary state restore |
| get 参数错误 | 2 | parameter-error waste（用户明确记录） |
| context 参数错误 | 1 | parameter-error waste（用户明确记录） |
| 其余成功 get | 10 | exact content / pagination / validation；逐项比例 UNKNOWN |
| 其余成功 context | 3 | restore / boundary validation；逐项比例 UNKNOWN |
| search | 2 | 摘要指出 local-ID navigation workaround 和 Episode-ID irrelevant history；无原 trace 不分配调用序号 |

19 是一次严格验收成本，不能规定为日常每个会话的最低恢复操作。
validation-only overhead 与必须分页均不应靠省略必需数学原文来消除。

### 代表性 synthetic equivalent replay

通用脚本 `scripts/replay_continuation_navigation.py` 创建同一结构的全新合成工作区，
可显式指定 `--runtime-source` 运行旧安装源码。旧缓存保留，不改 gold、不读真实数学。
目标均为恢复 checkpoint、三个产物、一个有未知依赖的上下文和验证 Episode ID 查询。
旧 driver 按旧 prose-only 指引复现两次 length=8001 与一次 budget=16001 的代表性非法请求；
新 driver 采用明确数字与返回导航。**它不是同一真实模型随机策略的无偏对照**，
也没有声称 Run 2 的实际错误参数就是这些值。

| 项目 | 实际旧安装源码 | 当前修复源码 |
|---|---:|---:|
| tool calls | 12 | 7 |
| 必需 restore | 3 | 3 |
| 三产物 exact reads | 3 | 3 |
| identifier validation-only call | 1 | 1 |
| 参数错误 | 3 | 0 |
| mapping lexical workaround | 1 | 0 |
| UNKNOWN/STALE 补查 | 1 | 0 |
| produced refs 找回 | 3 | 3 |
| exact Episode first correct | false | true |
| UNKNOWN rendered STALE | 1 | 0 |
| 连续局部推导 calls | 0 | 0 |

这证明这些绕行和错误在该路径可消除，不能推算所有真实会话一定减少五次调用。
原 schema 其实已有 max constraint；文案改善降低摩擦的模型效果仍需未来实际观察。
保留必要内容读取和 validation call，没有用巨大 status 正文人为压低 calls。

## 7. 测试与真实只读验收

本轮完整 pytest **320 collected / 320 passed / 0 failed / 0 skipped**，557.97 秒，退出 0。
比基线增加 **20 项**正式回归；19 项导航/状态合同先通过，随后合成 replay 也纳入全量。
全量在获准支持本地 IPC 的普通用户环境执行，未使用管理员或 DSH Full Access。
Ruff、format（130 文件，含 benchmarks）、`python -m mypy`（94 源文件）通过。
新回归覆盖 publication/review/legacy、exact ID/fallback/歧义、三种 freshness/semantic 状态一致性、
分页与上限指引、合成 replay 和零 per-turn 自动调用。没有改冻结 P0-3 tasks/gold。

代码与完整测试稳定后，仅针对用户指定 checkpoint `EPISODE-02B5B3613F9C03D8` 作真实只读核验：

| 持久 local ID | 当前 qualified ref | freshness / authority / eligibility |
|---|---|---|
| RESULT-1 | PROBLEM-0001:claim:CLAIM-P4256336B3D4ACF84 | CURRENT / PROVISIONAL / CONDITIONAL |
| PROOF-1 | PROBLEM-0001:proof:PROOF-P38BB8E0BF3A0024B | CURRENT / PROVISIONAL / CONDITIONAL |
| EVIDENCE-1 | PROBLEM-0001:evidence:EVIDENCE-PD9E04BAF18D4F198 | CURRENT / PROVISIONAL / CONDITIONAL |

三个映射均直接来自 proposals/reviews，没有先搜正文来找 qualified refs；
一个 PROVES relation proposal 单独显示，仍 UNREVIEWED，不自动生效。
原 Episode digest VERIFIED；Episode-ID search 返回 EXACT_IDENTITY、首项就是它。
三个产物的 exact view、navigation、8k packet freshness/eligibility 一致，display=PROVISIONAL，
没有 UNKNOWN 被误标 STALE。CURRENT 不等于数学正确或人工接受。

只读脚本调用当前源码的共享 services/projection/navigation，没有调用 MCP adapter 的
checkpoint_read，因而不创建临时锁。审计 hook 禁止研究目录任何写入/删除/重命名/权限操作，
也禁止读 notes 或普通研究文件；实际读取的 **74 个 Ledger 文件**前后 SHA-256 一致，写入尝试为零。
既有共享图投影会内部扫描 registry、其他 Problem 的记录作为状态基础；
本轮没有对其他 Problem 发查询或做研究，也未输出其正文，核验目标/导出始终只有上述 checkpoint。
这是读取范围的字节稳定观察，不是加锁的全局快照，不冒充真实模型/Host 再次续研验收。
证据为 `real-checkpoint.json`、`real-checkpoint.exitcode` 和私有 `real-read-hashes.private.json`；
公开报告仅保留用户已指定的定位 refs 和聚合结果，不复制数学正文。

## 8. 文件、部署与剩余边界

生产新增 `ledger/publication.py`；修改 `ledger/continuation.py`、`services/retrieval.py`、
`services/stale.py`、`retrieval/packet.py` 和 `mcp/adapter.py`。
新增 `tests/core_contracts/test_continuity_hardening.py` 与合成 replay 脚本；
更新双语 README、`docs/codex-mcp.md` 和本报告。
核心 identity/version/premise 规则、authority gate、Skills、Codex manifest 和 DSH 适配保持原样。

本轮另进行了必要的本地 Codex 安装刷新。公开仓库 manifests / Python 版本不改，
只有忽略的暂存包和安装缓存使用 `1.1.1+hardening.20261022`。
最初同 patch 的 `1.1.0+hardening.20261022` 安装报告旧版本仍 active；保留失败日志，
改用更高 patch 的本地暂存版本后，官方安装退出 0。
新版安装 95 个源码/模板文件与当前工作树逐字节一致，旧缓存仍可重现 before replay。
安装器重新启用 user 开关的副作用已纠正并复测；研究项目保持 enabled=true。
新 Host 的 schema 包含 produced_offset；这不意味着所有已打开的对话已热重载。
没有发布到社区、registry 或远端，也未重新构建冻结的 DSH Bundle。

最终安装后再核对：ordinary=0 tools、marker-alone=0、research=9，
仅 research 暴露新版 read produced_offset，server errors 为零。
配置变更后和安装完成后两轮 inventory 证据分别保留，安装器临时重新启用产生的中间 inventory
也保留，不能拿那个 9/9/9 的中间状态当最终项目范围配置。

### 本轮 Git 文件清单

新增：

- `src/math_research/ledger/publication.py`
- `scripts/replay_continuation_navigation.py`
- `tests/core_contracts/test_continuity_hardening.py`
- `docs/vertical-slice-continuity-hardening-2026-10-22.md`

修改既有文件：

- `src/math_research/ledger/continuation.py`
- `src/math_research/services/retrieval.py`
- `src/math_research/services/stale.py`
- `src/math_research/retrieval/packet.py`
- `src/math_research/mcp/adapter.py`
- `docs/codex-mcp.md`
- `README.md`
- `README.zh-CN.md`

阶段基线 SHA 审计确认既有文件无丢失，本轮没有范围外内容变化。
最终 `main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，**37 tracked modifications、
43 untracked files**（包括此前成果），index 无暂存；无 add/commit/push。
Ruff、format、mypy、diff 检查的实际退出码均为 0；私有配置备份、运行产物、
配置路径与只读 hash 明细均在 ignore 的 dist 下，没有进入公开包或 Git 待跟踪清单。
本轮新增/修改文本的凭据/私钥模式检查无命中；不将模式扫描当任意秘密检测保证。

下一步只需重新加载/新开研究项目的 Codex 会话，按事件触发 policy 检查新版导航体验；
真实模型是否因此少犯参数错误、真实 continuation 是否节省调用仍需实际观察。
不要求重新部署 DSH、全量重标 gold、迁移 corpus 或开始新研究。

UI persistence 的最初来源仍未知；没有真实模型后测，不能声称参数错误从此不会再发生。
legacy 无 mapping 时不能补救历史缺失；exact miss 仍可能有无关 lexical history。
本轮未安排新的数学研究或新 continuity conversation，也不把单次 slice 泛化成已验证长期可靠性。
