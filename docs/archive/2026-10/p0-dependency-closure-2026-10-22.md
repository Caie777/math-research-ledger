# P0-1：依赖身份、版本与工作前提判断闭环

> Historical engineering evidence; results refer to the recorded revision, not a new acceptance.
> Machine-specific locations are generalized. See [current limitations](../../known-limitations.md).

2026-10-22；本地工作树实现，未提交/发布。所有代码、测试、静态和 Git 命令执行目录均为
`<repo>`。真实 corpus 仅在最终回归通过后做只读诊断，结果见后文。
DSH、排序调优、embedding、UI、Episode P0-2 和真实数学研究不在本轮范围。

## 原缺陷与先红后绿证据

先新增 `tests/core_contracts/test_dependency_closure.py`，在修改实现前运行已知三类问题：
same-Episode Uses、legacy unpinned、refuted/rejected/invalidated upstream，共 5 个选中用例均失败，退出码 1。
JUnit、失败日志及退出码保存在忽略的 `<local-evidence>`。
这把上轮探针转为了真正的回归，而不是依赖报告结论直接改代码。

1. RESULT-2 Uses RESULT-1 经 candidate ID 转换后落到 unresolved，而 Manifest 对象使用 stable ID。
2. 无历史 pin 的旧 depends_on 在上游变化后仍被报告为无警告 CURRENT。
3. 新 ObjectView 没有完整传播语义上不可用的 upstream，新旧 usable 判断分歧。

## 共享身份契约

[identity.py](../../../src/math_research/ledger/identity.py) 的 ScopedIdentityResolver 只读取既有 records、
Proposal 与 latest ReviewDecision；不新建 alias 表或对象数据库。Manifest、KnowledgeState、
Episode local mapping、人工作业的 reference gate 和显式 link_dependency 复用该契约。

- qualified ObjectRef 优先且保持 kind；不得去掉 scope 后用 bare ID 猜测。
- bare ID 必须在给定 Problem/kind 中唯一；无 Problem 时必须全局唯一。
- local ID 需要 Problem + Episode；不能用“最近一次 RESULT-1”替代缺失来源上下文。
  在明确 Episode 中 local 名称优先于长得相同的 bare 名称；显式 qualified 名称始终优先。
- local -> CANDIDATE -> stable provisional -> reviewed canonical 使用记录中的映射。
  没有 object_id 的旧 proposal 使用已有 CANDIDATE 身份，只读投影不回填磁盘。
- reject/defer 保留可追溯 working identity，分别维持 REJECTED/HISTORICAL 或 PROVISIONAL，绝不升 canonical。
- accepted alias 可以解析到 canonical kind/ID；旧 pin 不因别名解析而被替换成 canonical 当前版本。
- 返回 MISSING_OBJECT、MISSING_LOCAL_OBJECT、EPISODE_CONTEXT_REQUIRED、SCOPE_AMBIGUITY、
  REVIEW_TARGET_MISSING、MALFORMED_REFERENCE 等原因。非法旧字符串保留为带诊断的 unresolved 边，
  不再仅发 warning 后把依赖从图里丢掉。

Ledger.explain 提供只读解释，Ledger.resolve/get 和对外 packet/get 接受历史 alias。
human review 仍要求依赖/target 已经通过原有 canonical gate，并保留 same-Problem 提交限制；
解析成功不意味着允许人工提交流程绕过审核。没有从自由数学正文推断等价或建立关系。

## Version pin：记录实际输入，不制造历史

[bindings.py](../../../src/math_research/ledger/bindings.py) 集中生成候选依赖，
Proposal 新增可选 dependency_pins，默认空；旧空字段不改变历史 record 的内容哈希算法。

| 输入情况 | 行为 |
|---|---|
| 新 same-Episode Uses/proof target/evidence target | 在 publication 中从本次精确作者快照，按依赖顺序计算并保存真实对象版本 |
| 跨 Episode/外部 Uses 有 input_versions | 保存调用者给出的原 pin，即使该版本已旧或目标当前缺失 |
| 外部 Uses 没有使用时版本 | 依赖可解析，但 expected_version=None，freshness=UNKNOWN，说明 Unbound |
| 显式 human link_dependency | 解析实际 scoped identity，并 pin 调用时读取到的 upstream.version |
| duplicate ingest / 旧 proposal 读取 | 不重算旧绑定、不回填 pin 或 ID |
| 人工 canonicalization | identity 跟随 canonical；保留原 expected_version，不自动 rebase |
| authored cycle / closure 超限 / 缺失对象 | 保守 UNKNOWN；已有 pin 丢失或不匹配时 STALE，不能自称 CURRENT |

same-Episode pin 对应本次原文中的新对象，不是 ingest 以后查到的旧对象“当前版本”。
跨 Episode 即使服务能读到今天的对象，也无法由此知道作者当时使用版本，所以不自动补 pin。
相同语义的 canonicalization 也会改变记录版本；旧 pin 因而可以明确 STALE，但不能变成 missing alias，
更不能为消除 stale 而自动重签/重置历史。恢复 current 需要后续明确重评估与新记录。

## Role 与 freshness

[dependencies.py](../../../src/math_research/ledger/dependencies.py) 集中定义 VERSION_ROLES / PREMISE_ROLES。
当前证据不足以安全放宽出处/工件影响，本轮保持所有八种 role 的保守版本遍历：

| Role | 缺失 pin / 版本变化 | 是否作为正前提传播语义 eligibility |
|---|---|---|
| logical_premise | UNKNOWN / STALE | 是 |
| definition | UNKNOWN / STALE | 是 |
| proof_target | UNKNOWN / STALE | 否；待证明目标不是已用前提 |
| evidence_relation | UNKNOWN / STALE | 否；关联不是证明依赖 |
| source_reference | UNKNOWN / STALE | 否；出处不是逻辑前提 |
| artifact_provenance | UNKNOWN / STALE | 否；保留工件版本要求 |
| revision_supersession | UNKNOWN / STALE | 否；不据此猜测数学等价 |
| formal_correspondence | UNKNOWN / STALE | 否；保留原有人工 correspondence 条件 |

没有增加第二套 provenance freshness 字段，也没有将 citation drift 忽略。
原有传递版本比较、cycle/max_nodes fail-closed、missing artifact 与 receipt currentness 保留。
未 pin 不是已证实发生变动，所以不粗暴标 STALE；它表示无法证明历史版本一致。

## 共享 premise eligibility

[premises.py](../../../src/math_research/ledger/premises.py) 负责语义规则与 logical/definition 闭包；
ObjectView 和公开 KnowledgeState 使用同一 currentness/authority projection。
Manifest 内部只调用 intrinsic KnowledgeState pass，避免递归投影；它不是另一份对外安全结论。

| 核心状态 | 含义与字段 |
|---|---|
| ALLOWED | 当前研究工作前提许可；usable_working_premise=True，仍不表示数学已证 |
| CONDITIONAL | provisional / 未确立假设及其条件依赖；conditional_premise=True，正前提 boolean=False |
| BLOCKED | rejected/refuted/invalidated/historical、不可作前提的对象、失败验证、UNKNOWN/STALE 或不可用的逻辑上游 |

所有状态提供 premise_reasons。CURRENT 仅说明版本/依赖一致，语义无效且当前版本 pin 匹配的 upstream
仍会 BLOCKED。条件假设允许开展明确标注假设的研究，但不能以无警告 positive premise 输出。
canonical/current != proved，checked != accepted，STALE != refuted。

research_get_object、research_search hits、research_context_packet items 均返回相同的
premise_eligibility、conditional_premise、premise_reasons、usable_working_premise、trusted_formal_premise。
这只增加状态输出，不调排序、不增加工具、不改变九个输入 schema。
packet 若截断正文，还会独立取消正文的 usable/trusted boolean；核心 eligibility/reasons 不因 transport 预算伪造改变。

trusted formal premise 保留原有 passed/current、人工作业与 formal correspondence 必要条件，
并额外受语义 BLOCKED 限制。历史 HUMAN_ACCEPTED/verification receipts 原样保留，
失效只改变当前 projection。人工确实接受 current 硬验证后，可以解除旧 CONJECTURE 标签的 conditional
工作限制；exact evidence 仍不能冒充 formal correspondence。

## 验证结果

最终执行结果、测试收集数、静态检查、真实 corpus 前后哈希与分类见下节及本地证据目录。
所有测试只用合成 workspace；没有真实模型或数学验证。完整套件的既有打包合约测试仍正常执行，
但本轮没有重新部署/更新 DSH Bundle、启动真实 Host 或改变 Profile/认证。

| 本轮最终检查 | 实际结果 | 退出码 |
|---|---|---|
| 完整 pytest | 218 collected/executed，218 passed，0 skipped，0 failures/errors；117.79 秒 | 0 |
| 新增 dependency closure 回归 | 42 项全部通过，包含最初失败的 5 个案例 | 完整 pytest 为 0 |
| Ruff | All checks passed | 0 |
| 格式 | 114 files already formatted | 0 |
| mypy | 89 source files 无问题 | 0 |
| git diff --check | 通过 | 0 |

新增覆盖包括 same/cross-Episode、qualified 跨 Problem 同名与 kind 过滤、review 后 alias/pin、
reject/defer、缺失/非法 ref、缺少/提供历史 pin、八种 role 的 unbound/drift、传递 stale、
历史 receipts 保留、cycle、条件前提及三工具标签/原因一致性。
原有 cycle/cap、formal correspondence、权限锁/异步/stdin-stdout 传输回归也在全套内通过。
最终日志为 `verified.log/xml/exitcode`，此前红测和中间完整回归记录均保留，不混用数字。

复现（选择全新 basetemp；从上述仓库根目录执行）：

```powershell
$env:TEMP = (Resolve-Path <local-evidence>).Path
$env:TMP = $env:TEMP
.\.venv-win\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp <local-evidence>
.\.venv-win\Scripts\python.exe -m ruff check src tests scripts
.\.venv-win\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv-win\Scripts\python.exe -m mypy
git diff --check
```

Windows asyncio/stdio 回归使用已授权的普通用户本地 IPC 环境；没有管理员权限或研究目录权限变更。

## 真实 corpus 只读诊断

最终测试稳定后执行一次诊断。禁止写入研究目录的 audit hook、完整文件哈希前后比对、
底层只读 Ledger/projection/identity 访问取代 MCP/CLI，避免创建 checkpoint 锁。
原先 39 个 missing refs 使用上轮私有聚合清单逐项分类；只在 owner 显式 Uses/target 提供的 Episode
上下文中解释 local ID，不按同名对象猜来源。完整分类与 refs 保存在忽略的私有 JSON，不复制数学正文到本文。

实际执行退出码 0；**750 个文件前后哈希完全一致**，3 Problems / 270 objects 不变。

| 原先 39 个 distinct missing refs 分类 | 数量 | 新解释 |
|---|---:|---|
| legacy local ID | 26 | owner 显式 Uses/target 指定 Episode 后全部解析；无上下文仍拒绝猜测 |
| candidate alias | 13 | 经 scoped working/canonical 映射全部解析 |
| 真缺失对象 | 0 | 原清单未发现 |
| scope ambiguity | 0 | 在实际 owner 上下文未发现；不宣称所有无上下文 local ID 唯一 |
| 其他 | 0 | 原清单未发现 |

当前投影 missing refs=0、unresolved edges=0、边数仍 133。
这是**读取解释改进**，没有修复磁盘 alias、重写 dependency、迁移或重新 ingest。
projected pinned edges=0、持久 candidate pins=0；零历史版本信息没有被伪造补齐。
CURRENT=173、UNKNOWN=97（旧审计为 205/65）；Unknown 增加来自未绑定历史版本的显式 fail-closed，
不能把 missing 清零解读为历史依赖已经验证 current。
eligibility 为 CONDITIONAL 101、BLOCKED 169；authority 仍 PROVISIONAL 217/CANONICAL 53，
270 个对象仍 NOT_CHECKED。没有新增 canonical/human acceptance/verification。

证据位于 `<local-private-evidence>`、
`corpus-hashes.private.json`、`corpus.log` 和 `corpus.exitcode`，均被 dist 忽略规则保护。

## 修改范围与保留问题

新增：ledger/identity.py、ledger/bindings.py、ledger/premises.py；
tests/core_contracts/test_dependency_closure.py；本文。

修改：ledger/dependencies.py、episodes.py、manifest.py、projection.py、provisional.py、state.py、target.py；
verification/freshness.py；services/research.py、services/retrieval.py；mcp/adapter.py；retrieval/packet.py。
core-product-audit 增加本报告链接，保留旧审计数字和原缺陷历史。

- 无历史 pin 的旧边仍 UNKNOWN；这是已知信息缺失，不是待自动修复的数据。
- canonicalization 改变版本后旧 pin 明确 STALE；不会自动把旧研究“刷新”为新研究。
- 需要 Episode scope 的 local ID 仍必须有来源；真正缺失/歧义不能靠猜测消除。
- 原文读取 digest 一致性、Episode lint/多 target 等 P0-2 问题未修；retrieval/continuity P0-3 未扩展。
- DSH 构建产物仍按原阶段冻结；不能拿旧已安装 wheel 声称包含本轮源码。
- 没有改 authority 决策、自动 accept/verify 或真实研究内容；没有 Git add、commit、push。

本轮完成后可进入 P0-2，需用户另行安排；本文不启动下一阶段。

最终 Git 状态：`main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，
21 个 tracked modifications、20 个未跟踪文件（逐文件计数，包含全部既有未提交成果），index 无暂存变更。
详细文件列表、JUnit 解析与检查退出码见忽略的 `<local-evidence>`。
既有 atomicio.py 与 MCP server.py 的字节哈希仍与进入本轮前一致；Codex manifest/Skills 未改。
