# P0-2：Episode 预检与原文完整性

2026-10-22；本地未提交实现。命令执行目录：`D:\Projects\math-research-ledger`。
DSH 冻结，不进行 Harness、retrieval 排序、embedding、UI 或真实数学研究。
本报告与 [P0-1](p0-dependency-closure-2026-10-22.md) 配套；历史审计数字保留在原审计文档中。

## 原缺陷与回归证据

改实现前固化三个失败回归：已归档 Episode 追加字节后，专用 reader 拒绝，
generic get_object 却成功；重复 local ID 与多个 target 没有结构化诊断。
三项均先失败，日志、JUnit 和退出码位于忽略的 `dist/_run/p0-episode-20261022/red.*`。
这些是合成 workspace 的直接观察；没有篡改真实研究原文。

## 一个 parser、一个 preview contract

`ledger/preview.py` 编排现有 decomposition、Proposal parser 与 metadata parser；
`services.ingest.preview_episode` 只是共享入口的重导出。ledger 不依赖 service/MCP。
numbered parser 保留字段出现次数与原文行范围，重复字段不再静默覆盖。

preview 返回 sha256、episode_id、detected_format/schema、候选/local IDs、bindings、
state_delta、input_versions、next directions、diagnostics 和 can_publish。
服务返回完整 Proposal/metadata 模型；MCP 只返回有 omission 计数的有界摘要。
bindings 分开保留作者 reference 与 resolved_ref；原作者 local ID 不被今日别名覆盖。

每项诊断具有 severity、code、message、start_line/end_line（无法定位时 null）、
related_refs、remediation。解析错误本身也转为可见诊断；非法 UTF-8/空上传/超限仍是输入错误。

| 等级 | 行为与主要代码 |
|---|---|
| ERROR | 阻止结构化 publication：DUPLICATE_LOCAL_ID、DUPLICATE_FIELD、AMBIGUOUS_TARGET、MISSING_TARGET、MISSING_CONTENT、SCOPE_AMBIGUITY、INVALID_STRUCTURE、CONFLICTING_INPUT_VERSIONS |
| WARNING | 可保留安全且明确的内容：未知 Uses 的 MISSING_OBJECT/MISSING_LOCAL_OBJECT、UNRESOLVED_USES、MISSING_INPUT_VERSION、STALE_INPUT_VERSION；不推断自由文本依赖 |
| INFO | ADVISORY_ONLY / RAW_ONLY：没有确立的数学增量，原文可以保存 |

proof/refutation/revision 及改变对象含义的关系声明需要唯一 target；中文旧对象字段受支持。
多个 target 仅在 P0-1 resolver 证明它们是同一身份时才规范化；不同对象不取首个。
缺失历史 pin 保留未知，不事后读取当前版本来伪造输入；新 same-Episode 输入沿用 P0-1 的作者快照绑定。
Revised/Refuted/Invalidated 始终是 source-reported assertion；不修改 canonical、关系 authority 或 receipts。
显式 front-matter assertion 可以独立存在；只有规划区的正文不生成 assertion。

默认 ingest 遇 ERROR 返回原因，不发布两个结构化索引。调用者可显式选择 archive_only，
精确保留原始 UTF-8 bytes，不提取候选或生成 delta；重复归档不会清除已经存在的结构化历史。
正常自然语言可以按 raw-only 内容保存，不因缺少标准标题强行制造 Claim。
已有 archived 记录仍可读取；lint 不是自动 schema 升级或历史重写。

## MCP 与轻干预 policy

九个工具保持不变。research_ingest_episode 新增两个向后兼容的可选布尔参数：

```json
{"problem_id":"PROBLEM-0001","markdown":"完整 Episode Markdown",
 "provenance":"harness checkpoint","dry_run":true}
```

dry_run 不创建锁、journal、原文、候选或索引。Agent 修正 ERROR、判断 WARNING 后，
以相同 Markdown 单次正常 ingest；必要时显式 archive_only=true 仅保存原文。
preview 不自动改写数学内容；64 KiB MCP 上限和省略计数继续生效。

Episode 是 checkpoint，不是每个 reasoning turn 的日志。默认只在有意义的状态变化、路线切换、
会话结束时产生；没有每 N 轮强制 ingest。轮数至多作 advisory fallback。
preview 保护持久状态的一致性，不限制自由探索或替 Agent 判断数学真伪。

## 固定 digest 的共享读取边界

`core/integrity.py` 读取一次 bytes、核对预期 SHA-256，再解码；不使用 mtime 缓存。
archive 校验、Episode reader/span、候选提取/review、generic Manifest/get_object、
live search docs、Recall exact download、context 来源读取复用这条边界。
精确读取返回已验证的同一份 bytes，避免先验证再重新读取未经验证的新文件。
旧 index/docs 缓存仅贡献成员与顺序；返回正文前重新从 live gather 读取，
不能用旧缓存或改过的缓存绕过今天的原文校验。未增加或调整 BM25/排序规则。

| 路径 | 损坏/不可读来源的行为 |
|---|---|
| raw archive / specialized reader / span / generic exact get / extraction / review | IntegrityError；MCP code=INTEGRITY_ERROR |
| list/status/search/navigation | integrity=FAILED、STALE、正文清空或仅诊断；不得成为 positive premise |
| 来源于该 Episode 的 Proposal 或 reviewed canonical 对象 | 原始记录保留；当前正文被隔离、freshness/premise fail closed |
| context packet / 内部 context | 损坏正文不进入 MUST/SHOULD；excluded/required_omitted 显示来源失败 |
| pinned Markdown Paper | 原件固定 digest 检查；未有独立 digest 的 extracted text 缓存不作为 exact source 正文 |

不会更新 stored digest、删除原文/对象/receipt、修复文件或改变 ACL。
哈希确认的是与既有固定 bytes 相符，不是作者身份认证或数学正确性证明。
没有声称所有可变 canonical 文件、历史 JSON snapshot 或 PDF 派生缓存都具有独立签名。

## JSONL 盘点

共享 read_jsonl/iter_jsonl 的调用者是 source-of-truth：typed Claim/Proof/Evidence/FailedAttempt/
Approach/RelatedPaper、Proposal/Review、relations/graph、verification/acceptance/dependency 等 ledgers。
这些读取现在遇非法 JSON、schema 不合法、UTF-8/访问错误时明确 INTEGRITY_ERROR，
JSON/schema 错误含文件名与行号，不再警告后跳过再返回“正常列表”。
不存在的可选日志仍表示空；读取不初始化。update_jsonl 读失败时不执行 mutation/rewrite。
archive index 原本已有严格 reader，继续 fail closed；checkpoint journal 原恢复边界保留。
index/docs/vectors/status 是可重建缓存，使用自己的 reader，不通过本次共享 authoritative reader；
没有把缓存变成新事实库，也没有进行数据库事务重构。

## 验证结果与只读 corpus

本轮最终回归、静态检查及一次只读 corpus 的实际结果见下方收尾记录。
证据全部保留在忽略的 dist 中，不提交真实正文或私有文件清单。

完整回归曾暴露既有四进程锁测试的 Windows CRT EACCES：os.open 不总保留 winerror。
新增注入测试先失败，再把 errno=EACCES 且 winerror 缺失这一情形纳入既有三次短重试。
永久拒绝最多四次尝试、三次休眠，仍受更短 deadline 限制；未知 winerror 与非 Windows 行为不放宽。
没有因此假定锁被占用、执行无锁写入、变更权限或调用 DSH。
25 项锁测试通过（含旧的竞争/超时/权限/清理/多进程回归）。

## 本轮文件范围

- 新增：`core/integrity.py`、`ledger/preview.py`、
  `tests/core_contracts/test_episode_integrity.py`、本报告。
- 调整 core：`errors.py`、`jsonl.py`、`atomicio.py`。
- 调整 ledger：`archive.py`、`decomposition.py`、`episodes.py`、`manifest.py`、
  `projection.py`、`readers.py`、`sources.py`。
- 调整 MCP：`adapter.py`、`server.py`；services：`ingest.py`、`research.py`、`retrieval.py`。
- 调整 retrieval：`context.py`、`index.py`、`packet.py`、`recall.py`、`selection.py`；
  verification：`freshness.py`。仅完整性过滤，不做 P0-3 召回/预算调优。
- 测试补充：`test_mcp_transport.py`、`test_file_lock.py`；`test_ledger.py` 原“任意自然语言必须拒绝”
  断言改为“空上传必须拒绝”，另有明确的自由文本可保存测试，未删除该测试。
- 文档：`README.md`、`README.zh-CN.md`、`docs/core-product-audit-2026-10-22.md`。

既有 P0-1、DSH、本地构建证据与未提交文件保留。本轮不重建或安装正式 DSH Bundle；
已有分发包不是本轮 P0-2 源码的新发行包，不应将本地源码修复等同于已安装插件升级。

## 唯一一次真实 corpus dry-run

执行目录仍为 `D:\Projects\math-research-ledger`；脚本直接调用只读 preview/archive reader，
不经过 checkpoint 写锁、MCP 或 ingest。Python audit hook 拒绝研究目录写入及 Ledger 目录之外的
研究文件读取；前后分别对全部文件作 SHA-256。一次诊断退出码 0，750 → 750，全部 bytes 相同。
未访问 notes repo、未回填 pins/delta/metadata、未升级 schema 或修 digest。

| 观察 | 实测结果 |
|---|---|
| Episode 总数 / 固定 source digest 通过 | 18 / 18 |
| 可识别格式 | numbered 17、legacy 1；全部未显式声明 schema |
| 无 ERROR、可按新合同结构化发布 | 3；另外 15 有结构诊断，并非 15 份原文损坏 |
| 没有 WARNING/ERROR 的 Episode | 0 |
| ERROR | 94 |
| 原始 WARNING | 579，**包含下面说明的空 Uses 误报，不能当作最终有效 warning 数** |
| advisory-only | 0 |
| 缺少历史输入版本的 Episode / 持久 input_versions | 18 / 0；没有补写 |

原始诊断事件分类（一次 source assertion 可能产生多个事件，不能等同于不同问题/文件数）：

| Code | 原始事件数 |
|---|---:|
| MISSING_INPUT_VERSION | 271 |
| UNRESOLVED_USES | 276 |
| MISSING_TARGET | 29 |
| UNRESOLVED_TARGET | 58 |
| AMBIGUOUS_TARGET | 16 |
| MISSING_CONTENT | 22 |
| MISSING_LOCAL_OBJECT | 1 |

诊断后发现并修复一个 preview 缺陷：两个未填写 Uses 字段拼接为换行，错误地被当作非空字段。
新增 numbered/legacy 两个回归，缺省 Uses 不再产生 UNRESOLVED_USES。
**遵守本轮仅一次真实 dry-run 的限制，没有在修补后再次扫描真实 corpus。**
因此上述 ERROR、原文 hash、格式、历史 pin 观察仍有效，但 276 条 UNRESOLVED_USES 中
哪些为真实未知引用、哪些为空字段误报，尚未在最终代码上逐条复核；当前有效 WARNING 总数未实测。
不擅自从统计里删掉整个类别，也不把未运行的最终 corpus lint 宣称为通过。
原始明细与前后 hash 仅在忽略的 `dist/_run/p0-episode-20261022/corpus*.private.json` 中保留。

合法 legacy 格式继续支持；旧文档缺少新发布所需 target/pin 是结构风险或历史未知，
不等于 digest corruption。现有历史仍可读取，本轮没有重新提取或迁移其中任何对象。

## 后续边界

- 已覆盖主要 Episode 固定原文读取入口和 cached/live search；目前未发现这些入口返回未验证
  archive bytes 的已知绕过。调用者自行传入的任意 Python 字符串、可变 canonical 正文和 JSON
  历史快照不是签名档案；本轮没有给所有研究文件补 digest，也不能检测攻击者同时改原文和其
  authoritative digest 的情况。
- 权威 JSONL 的语法/schema 损坏会显式失败；对于仍合法但被人改写过的行，没有新的签名或
  全量事件溯源保证。不会据此自动恢复或删除历史。
- 源码和合成测试可作为 P0-3 工程准备的基础；真实语料的最终 warning 基线仍需用户下次
  授权一次只读复核，不能据当前原始 warning 总数建立质量或 retrieval 改善结论。
- DSH 真实 Windows 验收、打包发行和真实数学研究继续暂停；需要后续独立安排。

## 最终工程收尾

本轮相对 P0-1 的 218 项基线新增 **51 项**：Episode/integrity 48、真实 stdio 合同 1、
Windows CRT/未知 native code 边界 2。全部为合成 fixtures，不调用模型或真实研究 checker。

最终命令执行目录均为 `D:\Projects\math-research-ledger`，Python 为仓库 `.venv-win`：

| 检查 | 最终结果 |
|---|---|
| 完整 pytest | collected 269；269 passed；0 failed、0 errors、0 skipped；140.21s；退出 0 |
| Ruff check src tests scripts | 退出 0 |
| Ruff format --check src tests scripts | 117 files already formatted；退出 0 |
| mypy | 91 source files；退出 0 |
| git diff --check | 退出 0 |

pytest 使用新建 dist 临时目录、`-p no:cacheprovider`、`--basetemp`、JUnit、
`-X faulthandler -o faulthandler_timeout=45`；完整套件在已授权的普通用户 IPC 环境运行，
没有管理员权限或 DSH Host。最终证据为 `dist/_run/p0-episode-20261022/closure.*`，
48 项 Episode 专项为 `post-corpus.*`；静态检查日志与机器可读汇总也在同目录。
原始 red、CRT red、两次失败全量结果以及后续绿色结果全部保留，不以绿色结果覆盖失败证据。

原有 rollback、canonical/verification/human authority、同 Episode pin、并发/原子写入、
MCP schema/纯净 stdout/输出上限、Codex 便携安装合同均通过完整回归。
没有操作真实 Codex/DSH 会话，也没有升级用户已安装插件。

Git：`main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，34 个 tracked modifications、
24 个 untracked 文件（包括既有成果）；staged diff 为空。没有 add、commit、push。
本轮涉及 31 个文件，完整范围已在上文列出；四个新增文件不包括既有 P0-1/DSH 未跟踪成果。
dist、日志、合成 workspace 与私有 hash 明细均被 Git ignore；新文件凭据模式检查未发现匹配。
没有读取/复制认证令牌，没有新增个人研究正文或修改公开插件配置中的 workspace 路径。
