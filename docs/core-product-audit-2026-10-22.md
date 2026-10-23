# MathResearch Ledger 核心产品审计与下一阶段路线图

2026-10-22；基于当前 `main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694` 加既有未提交工作树。
**结论：这是已有实际价值的研究记录与安全边界基础设施；尚不是经过真实长程研究验证的可靠续研系统。**
最需要投入的不是增加 Agent 或 Harness，而是让对象身份、版本依赖、读取校验和续研入口真正闭环。

后续 P0-1 已实现 scoped identity、输入 pin 和统一 premise projection，见
[P0-1 实现报告](p0-dependency-closure-2026-10-22.md)。本文保留原审计时的缺陷/数字作为历史基线；
当前实现与复测结果以专项报告为准。P0-2 的当前实现与证据见
[Episode 预检与原文完整性报告](p0-episode-integrity-2026-10-22.md)。P0-3 已在本地工作树完成
有限续研入口、轻干预 policy 与固定合成回放，见[续研评测报告](p0-continuity-evaluation-2026-10-22.md)。
P0-3 阶段回归为 300 passed；这是历史结果，不等于当前 release 的测试结果，
也不等于已经完成真实长期研究/模型续研验收。
下文未标为“后续状态”的“本轮”均指原始产品审计阶段；实现后的文件和测试结果以专项报告为准。

所有阅读、分析脚本与 Git 检查命令执行目录均为 `D:\Projects\math-research-ledger`。
DSH ACL/MIC/Host/Bundle 排障冻结，见[阶段交接](dsh-adaptation-handoff-2026-10-22.md)。
本轮没有改生产代码、测试或 README，没有构建 Bundle，没有运行数学研究、形式化检查或 human acceptance。
仅新增本文；已有未提交成果全部保留，没有 add、commit、push。

## 1. 证据范围与可信程度

审计直接阅读模型、存储、解析器、图投影、检索、packet、验证、authority、MCP 和相关测试，
不以 README 的承诺代替实现。下文源码链接对应当前工作树；行号在后续修改后可能变化。

真实 corpus 经本轮授权只读访问，未经过 MCP/CLI/`checkpoint_read`，避免创建临时锁。
使用底层只读 `Ledger.objects` / `projection.list_objects` 与元数据读取；审计 hook 禁止研究目录写入，
并禁止读取 Ledger 目录之外的研究文件。750 个 Ledger 文件读取前后 SHA-256 一致。
没有操作 notes repo、真实 Profile、ACL、所有者或完整性标签；没有 ingest/save/review/accept/迁移真实数据。
这是一份字节稳定的观察，不是锁定数据库快照或数学正确性验证，也没有证明未来并发读永远一致。

本轮另在忽略目录的全新合成 workspace 执行五项诊断探针；结果明确标为观察，不冒充新增回归测试。
聚合证据、私有引用清单和文件哈希保存在 `dist/_run/core-audit-20261022/`，不进入公开分发包。
本文仅记录聚合统计和少量定位 ID，不复制真实数学正文、证明、Episode 或 transcript。

## 2. 当前核心系统地图

| 层/源码 | 实际职责 | 权威来源与边界 |
|---|---|---|
| [paths](../src/math_research/core/paths.py#L22)、[config](../src/math_research/core/config.py#L57)、[workspace](../src/math_research/core/workspace.py#L16) | 发现 v1/v2 state，校验 workspace.yaml，拒绝冲突/未完成迁移，显式初始化 | 普通用户文件由用户拥有；MCP 不自动 init；读取不迁移 |
| [MCP resolver](../src/math_research/mcp/server.py#L47) | 部署参数 > MRL_WORKSPACE > SMR_WORKSPACE > cwd；handler 另先处理 MCP roots，再处理 tool workspace | roots/部署 pin 可以优先于 per-call；CLI ancestor 防误绑定规则与 MCP cwd 规则不完全相同，不能宣称完全同一个 resolver |
| [Problem/typed records](../src/math_research/ledger/records/models.py#L186)、records/store、claims、validation | Problem、Definition、Assumption、KnownResult、Claim、Proof、Gap、Evidence、Counterexample、FailedAttempt 等持久记录 | YAML/JSONL/正文文件是当前 canonical 内容；type、status 和 formalization_status 含义不同 |
| [ObjectRef/VersionPin](../src/math_research/core/refs.py#L6) | problem:kind:id 身份与 64 位哈希版本分离，拒绝不明 scope 的碰撞 | ID 不携带版本，bare ID 必须唯一；kind 是开放字符串，不是数学本体推断 |
| [ManifestEntry/Ledger](../src/math_research/ledger/manifest.py#L25) | 汇集 typed records、proposals、Episode、sources、旧 checker、assets、新 receipts，生成统一对象与边 | 派生读视图，不是另一个数据库；accepted aliases 折叠到 canonical，raw/rejected 仍可保留 |
| [KnowledgeState](../src/math_research/ledger/state.py#L125) | review/alias、已确认关系、proof/claim 状态、failed route 和上游警告的旧研究状态投影 | 不修改原记录；已有数学关系必须来自受控确认，不从自由正文猜测 |
| [ObjectView](../src/math_research/ledger/projection.py#L12)、[freshness](../src/math_research/verification/freshness.py#L23)、[authority](../src/math_research/verification/authority.py#L10) | 在 Manifest 上叠加 CURRENT/STALE/UNKNOWN、receipt currentness、HUMAN_ACCEPTED 和 premise 标志 | 新旧状态层并存；本轮发现 eligibility 不一致，不能把它们视为已完全统一 |
| [archive](../src/math_research/ledger/archive.py#L63)、[episodes](../src/math_research/ledger/episodes.py#L131)、[parser](../src/math_research/ledger/decomposition.py#L160)、[ingest](../src/math_research/services/ingest.py#L45) | 原文内容去重、scope membership、格式拆解、provisional candidates、来源 span、typed delta、advisory directions | 原文/metadata/proposal/review 是持久输入；state_delta 是 source-reported，不是 canonical 修改指令 |
| [dependencies](../src/math_research/ledger/dependencies.py)、[link_dependency](../src/math_research/services/research.py#L109) | 显式 pin 与既有字段推导的 typed edges；记录 role 和 provenance | 显式 edge 存 ledger/dependencies.jsonl；旧 depends_on/uses 等字段产生的边常无 pin |
| [checkpoint](../src/math_research/ledger/checkpoint.py#L46)、[atomic IO](../src/math_research/core/atomicio.py#L41)、[history](../src/math_research/ledger/history.py#L26) | 两索引 publication journal/rollback、独占文件锁、原子替换、部分对象版本快照 | 不是所有业务写入统一事务；不是全量 event sourcing 或全对象自动版本档案 |
| [index/BM25](../src/math_research/retrieval/index.py#L400)、[policy](../src/math_research/retrieval/policy.py#L191)、recall/selection | 实时文档、词法排序、双语意图规则、最多两跳图扩展、对象/失败路线导航 | index/docs/vectors/status 是可重建缓存；相关性不赋予权威 |
| [context](../src/math_research/retrieval/context.py#L159)、[packet](../src/math_research/retrieval/packet.py#L74) | 内部丰富选择器与外部预算 JSON；MUST/SHOULD/MAY、缺失/截断、版本前后校验 | 外部 packet 并未完整暴露内部 explore/handoff；complete 仅针对已计算 required 集合 |
| [review](../src/math_research/services/review.py#L18) | 固定 Claim/Gap 的完整审查输入、外部 advisory report 的版本匹配 | 没有内建 LLM reviewer；NO_GAP_FOUND 不验证、不接受 |
| [verification](../src/math_research/services/verification.py#L93)、verification/formal | 本地注册 exact checker；Lean frozen statement/config、固定 build/type/axiom probe、日志与 receipts | Lean 路径有实现；通用 exact/validated computation 没有随包附带数学 checker |
| [acceptance](../src/math_research/services/acceptance.py#L32)、[write boundary](../src/math_research/ledger/records/write_boundary.py) | 通过且 current 的硬验证才能 request；受信任人工通道创建 acceptance receipt | MCP 无 accept；ContextVar/环境标志是调用边界，不是对任意本地进程的认证或加密签名 |
| [MCP adapter](../src/math_research/mcp/adapter.py#L169)、server、CLI | schema/参数、workspace、分页、64 KiB SDK envelope、错误与共享服务调用 | 九个工具不含编译器/shell/任意文件写入；同步服务进入 worker thread；业务决策留在服务/ledger |

### Source of truth 与派生状态

- **持久事实来源：**Problem typed records 与正文、raw Episode/Paper 与固定 digest、archive membership、
  proposal/review/confirmed-relation 日志、显式 dependency pins、verification/acceptance receipts 与其 artifact bytes。
  这是多个有职责边界的文件集合，不是单一 append-only event store；部分 canonical YAML/JSONL 可以更新。
- **派生 projection：**ManifestEntry、KnowledgeState、ObjectView、freshness、usable/trusted flags、
  research map、current handoff、stale report、search ranking、context packet。
- **缓存/导出：**BM25 docs、vectors、生成报告、context markdown；删除/重建它们不应修改研究权威。
- `content_hash` 覆盖语义记录、正文和实际 artifacts；时间戳部分排除。
  `ManifestEntry.version` 再包含依赖 target/role/expected_version。**它不是递归 Merkle 图：无 pin 上游变化不会自动改变下游 version。**
  `source_version` 是整次导出的一致性指纹，连同相关闭包及部分全局 ledger history；不是内容真伪证书。

## 3. 两条实际调用链

### Episode 到后续上下文

```text
research_ingest_episode / CLI ingest
  -> services.ingest.ingest_episode
  -> checkpoint_transaction（锁 + archive index/candidate index journal）
  -> preview_episode（UTF-8/大小、格式、input_versions/schema）
  -> parse_candidate_proposals
       numbered H2 -> _numbered_candidates -> explicit fields / relation proposals
       或 legacy ## Claim:/Proof:/Gap: -> 严格字段拆解
  -> checkpoint_metadata（typed source assertion + advisory directions）
  -> archive_source（原文/digest/content dedup + metadata）
  -> extract_candidates -> stage_candidates（stable provisional object_id）
  -> Ledger.objects + KnowledgeStateResolver
  -> derived dependency edges + FreshnessResolver/ObjectView
  -> search / context
```

ingest **不会**直接 revise/refute/invalidate canonical 对象，不运行 checker，不请求/完成 human acceptance。
只有另行的受信任 `review_candidate` 才能把选定 proposal 映射到 canonical record；
关系确认、数学验证、新 acceptance receipt 仍是不同动作。
REVISION candidate 的人工提交主要生成 Approach/FailedAttempt，并不是通用旧对象替换器
（[commit](../src/math_research/ledger/episodes.py#L1019)）。

### 搜索到续研

```text
research_status(problem_id, offset, limit)
  -> status -> list_objects -> 小型分页摘要（没有完整证明或明确 primary_claim_id）
research_search(query, problem_id)
  -> services.retrieval.search_research
  -> unified full-content BM25 + ResearchRecall.find_files(intent/rules/relations)
  -> RRF 融合 + ObjectView trust/freshness 标签 + source_version 前后校验
research_get_object(qualified ref, offset, length)
  -> exact projected object -> 文本窗口、版本、来源、状态
research_context_packet(ref, query, purpose, budget)
  -> Claim/Gap 时先用 ResearchContextBuilder；再按 Manifest 依赖闭包组装外部 JSON
  -> 原文补读、核对依赖/权威/失效/预算 -> 外部 Agent 研究
  -> 单次完整 Episode checkpoint（回到上链）
```

“research continuation” 的推理者是外部 Agent；Ledger 没有研究循环。
当前 MCP status 不输出 primary target，get_object 的 Problem 正文也不输出完整 problem.yaml 元数据；
内部 [research_map](../src/math_research/retrieval/research_map.py#L92) 知道 primary_claim_id，但不在九个工具的结果中完整呈现。
这会使纯 MCP 新会话难以明确知道“当前主目标”，不能靠 `.current` 或最早的 Claim ID 猜测。
静态链路还显示一个兼容断点：Manifest 为缺少 object_id 的旧 proposal 返回 CANDIDATE 身份，
而 ResearchTarget 校验只匹配 candidate.object_id 或 canonical Claim；旧候选可被搜索/读取不代表可以直接构造 context。
人工接受后的旧 working ID 也不在 Ledger.resolve 的通用 alias 查询范围内，需要明确覆盖生命周期测试。
本轮没有逐个调用真实候选的 context；这些判断来自两端代码条件，不冒充真实调用结果。

## 4. 成熟度：按能力边界分类

“A”只表示该窄能力有可用实现和测试；不证明数学推理、真实 retrieval 质量或完整续研流程成熟。

| 分类 | 能力 | 判据与限制 |
|---|---|---|
| A | 显式 workspace init、v1/v2 发现/冲突拒绝/迁移 journal | workspace/migration tests；真实使用需显式选 root，不自动处理真实数据 |
| A | qualified identity、typed 存储、原文归档、精确内容去重、保留 rejected/failure | ledger/checkpoint tests；精确重复字节幂等，不是数学语义去重 |
| A | 自动化 provisional-only 与 MCP capability 边界 | authority/interfaces/transport tests；可信 CLI/文件系统仍是外部信任前提 |
| A | 已显式 pin 的传递 drift、cycle/limit fail-closed、历史 receipt 不覆盖 | dependencies/authority/harness tests；不涵盖未 pin 或错误 alias 图的完整性 |
| A | 有界 JSON transport、分页、明确 missing/truncated，Windows 锁错误有限返回 | packet/stdio/23 个锁/2 个异步用例；status 逻辑只读仍创建锁，非任意只读目录可用 |
| B | Episode 数学对象拆解与已有对象更新 | 格式解析可用；目标歧义、重复局部 ID、语义等价、revision 目标不完整，见下文 |
| B | 端到端 dependency/currentness/premise eligibility | 引擎存在；实际 corpus 零 pins、身份映射和新旧状态层不一致，必须优先补齐 |
| B | 搜索/排序/上下文选择 | BM25 + 固定规则 + 结构邻接已实现；无真实科研 gold/长期 continuity 验证 |
| B | source/provenance/artifact integrity | 固定源及专用读取有校验；通用 Episode read 与专用 read 不一致；出处字符串不是来源真实性证明 |
| B | ReviewPacket、Lean verifier | 完整 packet/严格 Lean probe 有生产路径和合成 tests；大 packet 会拒绝，真实工具链/科研效用本轮未验证 |
| B | human acceptance receipts | 请求/人工接受/currentness 有实现与测试；真实 corpus 未使用，旧 canonical review 与新 HUMAN_ACCEPTED 容易混淆 |
| B | 版本历史、checkpoint 事务 | 明确子路径可靠；不是所有写路径统一 snapshot/transaction，不能称完整审计数据库 |
| C | 通用 exact/validated-computation 数学验证能力 | certificate/registry/receipt 框架存在，tests 用 SyntheticChecker；没有产品内置精确算法或 interval checker |
| C | 向量语义 backend | Embedder Protocol 和 hybrid/RRF 有代码；没有附带 provider/model，九工具检索不走此 backend |
| C | 自动理解数学、自动生成可靠 dependency/revision 关系 | 没有这种能力；source fields/confidence 或外部 relation workflow 不是数学理解引擎 |
| D | 重建 Agent loop、planner/scout/model router、重复研究记忆数据库 | 与当前定位冲突；已有旧 campaign 字样/兼容类型不应成为恢复运行时的理由 |
| D（冻结） | DSH 真实 Windows 兼容、更多平台/渠道分发扩张 | 本轮不投入；不删除既有兼容记录或用户资料 |

## 5. 四个核心问题的审计

### 5.1 Episode 拆解：可靠的是语法，不是数学含义

[decomposition.py](../src/math_research/ledger/decomposition.py#L8) 识别严格 H2 `RESULT/PROOF/GAP/EVIDENCE/
COUNTEREXAMPLE/REFUTATION/REVISION/FAILED-ATTEMPT/BRANCH-n`，以及中英白名单的独立加粗字段。
字段前空行、heading 层级、命名都有实际约束；普通 prose 留在 raw archive，不会自动抽取结论。
legacy `## Claim: ...` 等是另一条有限语法；numbered 与 legacy 不能假定可随意混排。

- Confirmed Research Increment 是显式块边界；未加该块的旧数学段落仍可能被识别，以保持兼容。
- Next Research Directions / CURRENT RESEARCH HANDOFF 被 masking，不生成数学对象/依赖；保留原行号。
- `state_delta` 可显式声明五种 action，否则按 proposal 类型/关系推导；每条有 source SHA/span。
  Added/Revised/Invalidated/Refuted/Still Open 是**原作者断言**，不是系统已经完成的状态变更。
- RESULT 不等于已证明 theorem；PROOF 是完整作者正文而非已通过审查的证明；Evidence/Counterexample
  的构造、范围、验证文字是作者输入，不能替代 machine certificate。
- 目标主要从 target/uses 等 ID 字段定位。numbered 解析对多个可能 target 选择首个匹配，并非拒绝所有歧义；
  REVISION 的“旧对象”字段与 target 的读取并不等价。局部 ID 重复也没有集中 lint 后拒绝的契约。
- stable candidate ID 与 Episode digest/local ID 关联，完全相同内容幂等；换排版/改写后的相同数学命题会新建候选。
  legacy Claim SAME_AS 仅在正文与已有 Claim.statement 完全相等时匹配，numbered 不做通用语义去重。
- 人工 review 解析 local references 时要求已接受映射；不会把自由文字猜成 revision/refutation。
  这保护 canonical，但也使部分格式错误只能到 review/context 阶段才显现。

因此当前能可靠保留/拆分“作者按格式明确报告了什么”，不能可靠理解“实际证明了什么、与旧命题是否等价”。

### 5.2 Dependency/freshness：引擎已实现，输入图不完整

边有八种 role：logical_premise、definition、source_reference、proof_target、evidence_relation、
artifact_provenance、revision_supersession、formal_correspondence。角色词表不代表所有角色均有成熟自动生产者。
Manifest 根据 depends_on、candidate uses/target、source_artifacts、claim_links、assets 等产生既有字段边；
Episode 显式 input_versions 只对已声明 Uses 或 proof target 生效；显式 ledger edge 最后覆盖相同 key。

显式 link_dependency 在创建时保存 upstream.version；FreshnessResolver 递归比较 pins，
缺失/循环/遍历上限返回 UNKNOWN，哈希或 pinned version drift 返回 STALE。
所有角色当前都会参与该遍历，尚没有按“逻辑依赖”和“导航出处”区分影响强度的 currentness 策略。
因此图缺边/错边可漏标，纯出处变化或 proof-target 环可造成保守过标/UNKNOWN。

**本轮合成探针直接复现：**

1. 未 pin 的 depends_on 上游正文改变：dependent.version 不变，freshness 仍 CURRENT。
   这是当前实现对无 pin 的语义，不是传递 pinned drift 测试已覆盖的情况。
2. 新 Episode 的 RESULT-2 Uses RESULT-1：KnowledgeState 将 local ID 变成 CANDIDATE ID；
   Manifest 对象却可能使用 stable CLAIM-P ID，边落到 `kind=unresolved`，freshness UNKNOWN。
   corpus 中既有遗留 RESULT-n/GAP-n 和 CANDIDATE 引用也存在，不能把全部问题归因于历史数据。
3. 上游已 refuted，依赖 pin 指向其当前字节版本：旧 KnowledgeState.usable_premise=False，
   新 ObjectView.usable_working_premise=True，freshness=CURRENT。
   新投影未完整携带旧警告/语义失效判断；这**不是获得 HUMAN_ACCEPTED 的绕过**，但会误导工作前提选择。

历史 verification/acceptance receipts 不被修改。上游 pinned 内容变化时仍保留历史 HUMAN_ACCEPTED，
但 freshness 变 stale、trusted_formal_premise 不再允许；这正是设计所需。
不能反向推断 CURRENT = proved 或 accepted = current。

**测试缺口：**现有 dependencies 三项覆盖 pinned 跨 scope、缺失、cycle/cap；harness 一项覆盖显式
input_versions 经 canonicalization 后保持 stale；尚缺本轮上述新输入 identity/无 pin/语义 eligibility
跨投影一致性、pin 被遗漏时的警告，以及更深 alias/review 拓扑、role 影响策略的系统性回归。

### 5.3 Retrieval/Context：工程可检索，科研质量尚无证据

BM25 使用 NFKC/casefold、Latin/数字 token、中文 bigram，k1=1.5、b=0.75；
不理解数学等价、希腊符号、公式结构或跨语言数学同义词。
MCP search 对统一视图 full_content 做实时 BM25，再与 scoped Recall 的排名用 `1/(60+rank)` 融合。
Recall 有英文/中文 current/open/failed/history 等意图、固定权重、显式 target boost、最多两跳关系扩展；
并非训练或真实 gold 校准的 ranker。

- MCP SearchArgs 仅 query/problem_id/limit，没有显式 kind/state/freshness filters；意图偏好不等于过滤。
- 统一 BM25 的输入含包括 Episode 在内的大正文；Recall gather 的 source/proof 文本部分有 100k 字符界限。
  这两套文档路径与 tokenization 成本都不是持久索引即可解决；MCP 主路径不依赖陈旧的 docs.jsonl cache。
- canonical/current/authority 一部分通过旧规则加分，完整新 freshness 主要作为返回标签；
  融合后的词法通道仍可把 stale/unknown/unverified 排在前面。保留历史检索合理，但不能当作安全 premise 排序。
- failed attempts、counterexamples、已确认攻击/替代关系有专用导航和 caution；不是简单遗忘失败。
  其效果取决于 target/artifacts/uses 是否正确记录；缺边的失败只能靠关键词。
- external packet 先放 required 身份/omission metadata，再填正文，完整 JSON 按 `ceil(UTF-8 bytes/3)` 估算；
  不是模型 tokenizer 的硬 token 上界。MCP 另外限制 64 KiB，预算在模型内还要留系统提示/输出空间。
- Claim/Gap 用内部 selector 的 proof/依赖优先级；Problem target 跳过该 selector，只有显式依赖闭包和词法补充。
  默认不遍历“全 Problem 当前主目标/全部 gaps/最新 handoff”来定义 required 集合。
- raw Episode/source 取 head/match/tail 字面 excerpt；proof 优先完整正文，超预算明确截断并取消 premise flags。
  这不是自动数学摘要；provenance/labels 的开销可使 tiny budget 拒绝。
- 内部 context 的 `explore=True` 会生成 HOT current handoff / WARM failures / COLD sources；
  MCP export 没传 explore，外层又从 Manifest 原文重建内容，不能声称完整复用了该续研体验。

本轮合成 Problem packet 的 required 只有 Problem 本身，即使相关 claim 为 UNKNOWN 也可 complete=True。
这符合当前字段定义，却不能解释成“恢复研究所需的信息已经齐全”。
缺少冻结查询集、researcher relevance 标注、premise 安全指标、预算曲线与隔周盲恢复实验；
因此目前只能评为工程检索可用，不能评为真实长期数学研究 retrieval 已成熟。

### 5.4 Continuity：目前最容易误解的地方

| 几周后 Agent 的问题 | 当前应做的事 | 当前断点 |
|---|---|---|
| 我在哪个 Problem？ | 显式 workspace + problem_id 调 status，并分页 | `.current` 可能是别的问题；status 不给 primary target |
| 证明了什么？ | get_object 原文、完整 proof、verification/authority/freshness 分开看 | THEOREM 类型、CANONICAL、CURRENT 均不能证明“已证明” |
| 哪些路线失败？ | scoped failed-route search，沿 target/artifact 补读负面材料 | 孤立 failure 与未确认关系可能检索不到或召回过多 |
| 哪些结论失效？ | stale_report + research_state/UNKNOWN + 版本检查 | 未 pin 会漏 drift；新旧 usable flag 分歧不能忽略 |
| 当前 gap 是什么？ | 定位 exact Gap，核对它与当前目标的显式关系 | 仅搜索 open gap 不等于知道唯一关键障碍，provisional/legacy alias 可断图 |
| 该拿多少上下文？ | exact Claim/Gap packet，检查 MUST/omitted/truncated，按窗口补原文 | complete 不等于语义完整，MCP 未暴露最新操作 handoff |

首要误用风险是把“找到了大量带 ID 的内容”当作“恢复了研究状态”，或把简洁且 CURRENT 的结果当作可信前提。

## 6. Verification、canonical、checked、acceptance 的实际关系

1. **canonical**：typed/human-reviewed 研究记录身份；默认 CANONICAL/ACCEPTED 也用于部分 metadata，
   不等于硬验证或新的 acceptance receipt。proposal 的 reject/defer/accept 是第一套 review 流程。
2. **checked/PASSED**：旧 Record status/旧 verifier flags 与新版 VerificationReceipt 是不同来源。
   新 receipt 的 authority 固定 NONE，只有指定 checker 的 outcome，不能从“作者说 verified”获得。
3. **soft review**：外部 reviewer + pinned packet + GAP_FOUND 等结论；NO_GAP_FOUND 仍 ADVISORY。
4. **human acceptance**：第二套流程，必须存在对应 current PASSED 硬验证；MCP 可 request，不可 accept。
   formal acceptance 还要求显式 informal/formal correspondence。
5. **freshness/stale**：当前依赖/源工件与记录版本是否一致的派生值；保留旧 receipts，取消当前可信使用，
   不删除历史、也不自动重新验证。UNKNOWN 不是 CURRENT，STALE 也不是数学命题被 refuted。
6. **工作假设 vs formal premise**：provisional 可用于注明条件的研究工作；trusted_formal_premise
   需要 current 的 formal/human acceptance 闭环。新旧工作 eligibility 分歧需先修复，不能靠提示词兜底。

LeanChecker 有实际固定命令、超时、frozen hash、确切 declaration/type 与 axiom policy。
测试大多 mock checker/subprocess，不是通用数学证明正确性或每个安装环境认证。
冻结 toolchain/lockfile 不等于 attestation 每个编译器/Mathlib 安装字节。
Exact/ValidatedComputation 依赖本地应用注册 checker；证书的 method/scope 字符串不是算法实现。

## 7. Source/provenance/integrity 的另一处实测边界

raw Episode 的原始 SHA、source span、Paper pin、counterexample body hash、retained run assets、
checker log hash 都有实际实现和测试，详见 sources/readers/assets/history 与 verification services。
然而不是所有读取都经同一校验入口。

合成探针将已归档 Episode 正文追加一行：专用 `episode_source` 拒绝 SHA mismatch；
通用 `projection.get_object` 却返回修改后的 bytes，freshness=CURRENT、warnings 为空。
原因是 Manifest 在该路径重新散列实际文件，但未把它与 Episode 的原始 content_sha256 对比后拒绝/降级。
这是生产读取链缺口的复现，**没有**对真实 Episode 做篡改实验。

另一个独立风险是 `core.jsonl.iter_jsonl` 对多数 schema 损坏行 warning 后跳过；archive metadata 用更严格的读取。
不能把“列表看起来正常”当作“所有持久记录都通过完整性检查”。快照也只在部分 update/check 路径创建，
不是任何变动都有可恢复的旧正文。出处 span 定位文本，不认证作者，也不证明数学推理。

## 8. 真实 corpus：只读实测画像

统计为当前统一 Manifest 视图，既包括研究对象，也包括 Episode/Problem/source 等导航记录；
不等于 canonical 命题数量，也不是所有旧磁盘文件行数。raw duplicate 检查只比较同 scope/kind 完整正文，
不检测数学等价；未自动修复任何异常。

| Problem | objects | Episodes | candidates（含 relation） | projected edges | 孤立对象 | CURRENT / UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|
| PROBLEM-0001 | 157 | 10 | 190 | 103 | 75 | 116 / 41 |
| PROBLEM-0002 | 51 | 5 | 53 | 15 | 38 | 40 / 11 |
| PROBLEM-0003 | 62 | 3 | 65 | 15 | 47 | 49 / 13 |
| 总计 | **270** | **18 unique** | **308** | **133** | **160** | **205 / 65** |

kind 分布：claim 72、proof 51、refutation 3、gap 28、evidence 29、counterexample 9、
failed_attempt 23、revision 26、branch 6、episode 18、problem 3、related_paper 1、source 1。

- authority：PROVISIONAL 217、CANONICAL 53、HUMAN_ACCEPTED 0。53 含导航/metadata，不能称 53 个接受定理。
- verification：270 个均 NOT_CHECKED；STALE 0、UNKNOWN 65。零 STALE 不等于全部验证新鲜。
- research_state：CURRENT 219、OPEN 28、HISTORICAL 23；没有派生 RESOLVED/REFUTED/INVALIDATED。
- edges：logical_premise 36、proof_target 51、evidence_relation 25、source_reference 21。
  pinned 0；已确认 active relations 0；308 proposals 中 relation 90，不能算成 90 条已成立逻辑关系。
- 133/270 = 0.493 条 outgoing edge/对象；160/270 = 59.3% 在这张 typed dependency 图上无入边/出边。
  孤立 Episode/Problem 本身未必异常；研究对象漏链接才影响用途，不能为降孤立率自动编造边。
- 39 个不同的缺失 target refs，包括旧 RESULT/GAP/PROOF local ID 和 CANDIDATE alias。
- 新式 ledger verification/acceptance collections 当前无记录。只有一次 Proposal accept，不能等价为新 human acceptance。
- 18 Episodes 的**持久 typed metadata**中 input_versions、state_delta 和 next_directions 均为零/空；
  不能由此断言 raw Markdown 没有研究内容或方向，也不能静默重解析/回填旧历史。
- 同 scope/kind 的完整正文精确重复组为零；没有做语义重复/证明有效性检查。

**PROBLEM-0001 当前定位（来自文件，不是聊天记忆）：**status=open、formalization_status=informal、
primary_claim_id=CLAIM-0002。当前全局 `.current` 却是 PROBLEM-0003；续研必须显式选 P1。
P1 canonical claims 共 20：CONJECTURE 3、CLAIM 2、THEOREM 12、OPEN_GAP 1、OBSERVATION 2，
全部 unverified；canonical gap 是 CLAIM-0017，依赖 CLAIM-0016（CONJECTURE）。
投影包含 12 个 OPEN gaps，其中 11 个是 provisional。CLAIM-0003 虽类型 THEOREM，仍未被硬验证。
本轮没有判断这些命题真伪，也没有替研究者决定哪个 Gap 最值得研究。

## 9. 下一阶段优先级

### P0-1：依赖身份、版本与工作前提判断闭环（立即开始）

**当前问题/重要性：**新输入都可产生 unresolved local alias；已有图零 pins；新旧 eligibility 不一致。
这是 Ledger 最独特能力失效的位置，先于扩大检索或写更多数学记录。

**模块：**episodes/provisional、state、manifest、dependencies、freshness、projection、对应 services。

**建议实现：**先把本轮三个依赖探针变成失败回归，再用一个共享的 scoped identity resolver 处理
Episode-local -> candidate -> stable provisional -> reviewed canonical 映射。
新增输入保留使用时的明确 version pins；未记录历史版本不得用“今天的版本”假装补齐。
对 legacy 无 pin 明确返回未绑定/不可证明新鲜的诊断，不大批迁移或误报全是 stale。
统一 semantic eligibility：上游 rejected/refuted/invalidated/unknown 不能给出无警告的 positive-working 许可，
同时允许明确标注条件的 provisional research；保留 historical authority。
先修身份，再 pin/eligibility，分小变更验证，不更改数学内容或自动确认关系。

**测试策略：**本地/跨 Episode、canonicalization、reject/defer、跨 scope 同 ID、传递 revision、
上游 refuted 与 pinned-current 字节、cycle/cap、缺失 refs、旧无 pin 读取、旧 receipts 不改。
MCP get_object/search/packet 应对同一对象给出一致标签/原因。

**完成判据：**合成合法 Uses 无 unresolved；使用旧 pin 时 upstream change 必为 STALE；
未知旧版本明确 UNKNOWN/未绑定；所有失效前提路径一致 fail-closed；原有 authority/receipt 回归不变。
**真实 corpus：**需要后续只读诊断确认 39 个缺失 target 的来源与显示改善，不要求也不允许自动回填历史 pins。

### P0-2：可预检的 Episode 输入与一致的原文读取校验

**2026-10-22 后续状态：**已在本地工作树实现共享 preview/lint、九工具内的 dry-run/raw-only、
统一固定 digest 校验与损坏正文隔离、严格 authoritative JSONL 读取。
当前回归和真实只读统计以[专项报告](p0-episode-integrity-2026-10-22.md)为准。
最终工程回归 269 passed；18 份原文 digest 通过、750 文件字节不变。
唯一一次真实 dry-run 暴露的空 Uses warning 误报已用合成回归修补；未再次扫描真实语料，
因此最终有效 warning 总数仍待下次授权复核，不能把原始统计当作定版质量基线。
以下问题描述/建议是原审计基线；不是当前代码仍未修复的结论。

**当前问题/重要性：**格式与多 target 歧义缺少统一反馈；通用读取绕过 archive digest 对比。
会把“存下了”误当“正确拆好了”，或让改过的原文以 CURRENT 返回。

**模块：**decomposition、episodes、ingest.preview_episode、archive/readers、manifest、MCP adapter。

**建议实现：**复用现有 preview，返回结构化 lint：重复 local ID、多 target、未知 Uses、missing fields、
无法定位的 revision、未固定 input_versions、仅 advisory 内容；给出 source span，区分 error/warning。
保留 raw bytes，明确 delta 是 assertion；不自动数学去重、canonical revise 或 relation accept。
把 archived Episode 的 digest 校验复用到所有 generic get/search/context 读取；
必要时提供无正文的损坏导航项与明确错误，不能一律“重新散列后视为正常”。
若公开 preview，不建第二 parser；评估向后兼容后再选择现有工具参数/CLI 报告入口。

**测试策略：**规范中英格式、空行/H1/H2、混排/重复 ID、多 target、advisory reference、原文篡改、
失败 publication/rollback、重复 ingest、声明 Revised/Invalidated 不修改 canonical；所有读取通道一致拒绝/降级。

**完成判据：**每个歧义输入有可定位诊断；未授权 canonical/authority 变化为零；
专用与通用 reader 对 digest mismatch 结果一致；有效 legacy 读取兼容且原文不改。
**真实 corpus：**经单独允许后只读 dry-run lint，报告历史格式支持范围；本轮不重解析或迁移现有 archive。

### P0-3：可核对的续研入口与固定 retrieval/continuity 评测

**2026-10-22 后续实际状态：**已实现显式 Problem 优先、primary target、有限 gaps/失败/风险导航、
ADVISORY latest checkpoint/handoff、caller baseline 状态指纹比较；未选 Problem 不采用 `.current`。
packet 保留 complete，新增 required_set_complete 与有限语义覆盖说明；九工具不增加。
free research / event-triggered policy 已进入新 workspace Agent 模板，无每 N 轮自动调用/保存。

冻结 18 个双语任务、三种策略、2k/8k/16k，共 9 次 replay/162 任务观察。
全部选题/主目标/最近 checkpoint 正确、MUST identity 4/4；A/C 的 key refs@10 为 5/5、
negative refs 4/4、unsafe cached positive 为零。C 每档 18 calls，对 A 的 46 calls 少 60.9%；
B 每档 4 calls，但漏掉会话中途依赖漂移，unsafe cached positive 为 1。
A/C 均保留一个无关历史来源误召回，没有改 gold/排序权重来隐藏它。
这是实际工具回放的 evidence exposure，未进行真实模型推理效果评测，事件识别能力亦未验证。

合成与全量通过后仅只读 P1 metadata，生成 6 条私有待人工标注候选；33 个选定 Problem 文件哈希不变。
尚无人工真实 gold / relevance / nDCG，不宣称真实 recall@10 已达到原审计的 90% 目标。
完整 pytest 300 passed；Ruff、format、mypy、diff 检查通过，详情和分母以专项报告为准。
原有方案描述保留于下方作为审计历史；其中“当前问题”不是对新代码仍有这些缺陷的断言。

**当前问题/重要性：**MCP 无明确主目标/最新 handoff 入口；Problem packet complete 语义太窄；
没有质量 baseline，无法证明排序和预算策略真正降低重复研究。

**模块：**research.status、research_map、handoff、context/packet、search/recall/policy、MCP schemas/tests。

**建议实现：**status 以有限字段暴露 primary target、明确选择来源、当前 open gaps/失败/未知数与分页导航。
复用现有 current_research_state 做独立标注的 advisory 操作状态；禁止把 handoff 当数学 premise。
让外部 Claim/Problem packet 的 required 集合解释覆盖什么、未覆盖什么；复用选择结果，避免只借 priority 又丢内容。
先冻结小型查询/target gold，再调排序；不要先上 embedding 或扩大读取。
第一版可用 12 个合成任务（中英 current/gap/failure/history/ambiguous/no-match 各两类），
再由研究者标注少量真实 P1 查询；标注与 gold 不硬编码进 ranker，也不公开真实数学正文。

**测试策略：**显式 P1 对抗 `.current=P3`、main target 缺失/变更、false complete、未知/历史 premise、
完整 proof 与摘要、负面知识、预算 2k/8k/16k、无关 Problem 干扰、源中途变化、下一会话盲恢复。

**完成判据：**固定合成集 required identity recall=100%、unsafe positive-premise=0、预算/截断报告正确=100%；
真实 gold 的关键来源 recall@10 至少 90%（不足十项时报告分子/分母），手工比对 nDCG/失败路线 recall，
不为达分泄漏标注或塞特定 ID；若 baseline 不达标，明确失败并据失败类型调策略。
**真实 corpus：**需要研究者 relevance/continuity 标注；统计数不能替代判断数学相关性。

### P1：真实研究实验后再决定（五项）

1. 是否增加显式 type/state/freshness filters、公式/同义词检索：看冻结评测中的误召回/漏召回。
2. 是否接可选 embedding/reranker：只有词法基线的失败确有语义原因时再加，保留可离线降级。
3. 是否扩展版本快照、严格控制 ledger reader 与更广事务范围：看实际损坏恢复/大 corpus 成本需求。
4. 是否开发一个具体 exact/validated checker、扩大 formalization 适配：先有真实研究任务和可验证证书算法。
5. 是否改善人工 proposal/relation review 的批量体验：根据 provisional backlog 和真实用户负担决定，不自动提升权威。

### 暂不做

Standalone Agent loop、自动研究 planner/实验执行器、模型路由/新账号管理、全量语义知识图谱、
自动 theorem truth/accept、每轮聊天自动记忆、第二研究数据库、无评测依据的向量库/分布式缓存、
通用 UI/社区发布扩张，以及被冻结的 DSH 权限排障。保持既有兼容读取，不借机删除历史模块/数据。

## 10. 第一个真实 vertical slice：P1 的一条已有 Gap 续研

**仅设计，本轮未执行研究或真实 MCP 调用。**在完成 P0-1/2 的安全底座并具备 P0-3 baseline 后，
优先在现有可用 Codex 接入安排，不依赖恢复 DSH。用户需另行授权真实研究与 checkpoint 写入；不包含 human acceptance。

### 预检与恢复

1. 显式选择真实 workspace、`problem_id=PROBLEM-0001`，调用 research_status；
   先读有限 continuation 导航，需要时再分页。历史基线 157 个对象不是永久计数。
2. main target 应从受支持的 metadata 入口核对为当前 `PROBLEM-0001:claim:CLAIM-0002`；
   当前 status 已有该入口；真实安装环境必须使用已更新的实现再验收，不借本地测试冒充已部署。
3. read main claim 的完整窗口，恢复所需 gaps/风险/失败背景；
   在路线切换、前提复用、重复风险等事件再针对性检索，不在每轮推导重复 search。
   可从现存 `PROBLEM-0001:gap:CLAIM-0017` 及它的 `CLAIM-0016` 依赖检查起；
   先确认该 Gap 与主目标的真实关系。若不是本轮适合的子问题，用户/Agent依据来源另选现存 Gap，
   不新建 demo、不因编号/排名自动认定关键性。
4. 对最终 exact Claim/Gap 请求 purpose=CONTINUE_RESEARCH、token_budget=8000 的 context packet；
   如需失败背景再用 FIND_FAILURES，正文不足用 get_object 分页，不进行全库倾倒。

### 应获得的 packet 与研究动作

MUST：目标完整陈述、明确条件/definitions、已记录依赖闭包、当前版本/来源/authority、
缺失和 UNKNOWN 原因、与此目标直接相关的现存 proof。SHOULD：相关 Gap、failed route、counterexample；
MAY：历史 Episode/source 的受限导航。操作 handoff 独立 ADVISORY，不能污染可信数学依赖。
CURRENT 且 unverified 的 CLAIM-0016 只能作显式条件假设；当前 corpus 没有 hard-verified premise 可凭标签直接宣称成立。

外部 Agent 只做一项有时间边界的真实数学推进，例如检验一个明确子情形或给出缺口定位；
不要求成功证明新定理。全过程记录实际使用的 ref/version、来源和失败条件，不运行形式化/human acceptance，
除非后续用户再明确授权。

### 标准 Episode 与 ingest 后应发生什么

完成时提交一份完整 UTF-8 Research Episode：Confirmed Research Increment 中使用标准编号对象/字段；
明确 Added/Revised/Invalidated/Refuted/Still Open 的 source assertion；
实际用到的 input_versions + Uses、target、完整证明/证据/失败正文与 scope；
Next Research Directions 单独 advisory。没有成果也可诚实记录 failed attempt / still-open，而不是制造 Claim。
先 preview/lint，再单次 research_ingest_episode，记录新 Episode/candidate/stable IDs 与 counts。

确定性验收：原文 digest/来源 span 可还原；新增候选数与 preview 一致；重复相同内容不增对象；
canonical records、人工 review/acceptance、原有 verification receipts 不变；
新增 dependency 解析到已有/同 Episode 对象并保存真实使用版本；
若使用期间上游版本已变，新候选为 STALE/UNKNOWN 而非伪 CURRENT；
relation proposal 和 delta 不自动使旧 canonical 被 refuted/revised。
不能把“新 Episode 说修订了”写成“系统已完成旧命题修订”。

### 下一会话的可量化成功标准

- 不读上次聊天，明确恢复 P1/main target 和选定 Gap，scope/版本/authority 识别 100% 正确。
- 从事先冻结的 researcher gold 中找回全部 MUST ref，关键来源 recall@10 达到前述阈值；报告分子/分母。
- stale/unknown/refuted/截断材料被当成无条件正前提的次数为 0；未验证 THEOREM 被称已证的次数为 0。
- 正确说出选定 Gap 的尚缺步骤，并召回至少一条确实相关的失败路线；若数据没有关联 failure，明确“未记录”，
  不编造“不重复失败”的成功。用户判定所选路线是否实际重复。
- 8k 预算内完整必需项或明确列出全部 omissions；不把 complete 当数学理解认证。
- 新 checkpoint 的可检索 refs、typed delta/provisional 状态与 dependency pins 全部匹配；
  没有自动 canonical/human authority 提升，旧研究文件保持不变。

这验证的是“有证据地恢复、推进和保存一轮研究”，不是以生成长报告或证明数量作为成功指标。

## 11. 原始审计阶段的工程验证与交付状态（历史记录）

本轮只有文档新增；忽略的 dist 内有只读聚合/合成诊断脚本和证据，没有改生产实现或回归 tests。
五项合成探针实际运行退出 0，输出的是已发现缺口，不把缺口当功能验收通过。
只读 corpus 观察退出 0，750 文件前后哈希一致；后续仅补读 Problem 元数据定位 primary targets。
最终执行 `git diff --check` 与本文本地链接检查；具体退出码记录在同目录工程证据中。
未重跑 pytest/Ruff/mypy，也未重建 Bundle；上一阶段 176 passed 的记录仅是历史基线，**不是本轮执行结果**。
这些新发现也说明此前全绿回归没有覆盖全部产品风险。

最终已核对 Git 状态：main HEAD 不变；既有 9 个 tracked modifications、14 个 untracked 文件保留，
加本文共 15 个 untracked 文件，index 仍无暂存。真实研究状态未修改，notes/Profile/DSH 完全未操作。
下一步建议直接从 **P0-1：先把本轮 dependency identity/eligibility 探针固化为回归，再修共享投影** 开始；
本轮到此停止，真实研究实验与后续实现等待用户安排。
