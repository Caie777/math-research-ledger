# Context precision after vertical slice

任务编号：2026-10-22。所有代码、测试、文档、Git 命令执行目录：
`D:\Projects\math-research-ledger`。本轮只做工程加固，没有数学研究、真实 ingest、canonicalize、
verify/accept、DSH 排障或 Git add/commit/push。原有未提交成果保留。

## 冻结的真实观察与调用分类

用户报告的自然 continuation：session-start 为 status ×1、context ×2、get_object ×9，
共 12 calls；checkpoint 后总数 14。produced/exact-ID navigation 正常，无 lexical workaround、
参数错误或 UNKNOWN/STALE 歧义，连续局部推导零 Ledger calls。
主要问题是局部 packet 带入不同路线的历史；具体私有研究主题不在公开报告中复述。
这些是用户提供的观察，本轮不依赖或重建完整旧聊天 trace，不把 12 当优化目标。

可靠恢复至少应知道：主目标、选定 Gap 及其使用的依赖；最新直接相关 checkpoint 的增量与
仍 open / invalidated 等来源声明；产物 refs/版本/authority/freshness；直接失败路线与反例；
需要数学使用时才读取完整 proof。source assertions 和 handoff 仍不是 canonical 修改或数学前提。

| 调用类别 | 可以支持的判断 |
|---|---|
| status navigation | 真实观察为一次；提供有限入口，不含数学正文 |
| required mathematical content | 主目标、Gap 和前提确实需要；packet 已完整返回同一版本时不必再 exact |
| truncation pagination | 正文未恢复完整且本轮需要时必须读取，不能为降 calls 丢弃 |
| dependency/premise inspection | 复用前提前要核对；不能仅凭 CURRENT 或类型 THEOREM 当已证 |
| checkpoint-produced recovery | 持久 mapping 已解决身份；packet 可进一步供局部导航/summary |
| validation-only | 严格检查可以额外调用，不把它当每个日常会话的必需步骤 |
| duplicate exact reads | 仅当 packet 已完整覆盖同一版本/窗口才可判多余；九次 get 的逐项比例 UNKNOWN |

因此，本轮用固定语义需求的 equivalent replay 衡量成本，不编造那九次 exact reads 的目的分配。

## 根因：当前代码直接证据与合成复现

旧 `export_context_packet` 在明确 Problem 内仍合并旧 selector priorities 和全部 BM25 hits；
没有要求每个可选身份与选定 Gap 或其 checkpoint 直接相连。
之后只要预算还有余量就继续加入 candidates。Problem scope 防止跨 Problem 混入，
但不能排除同一 Problem 内已换路线的历史。

合成强重合对象无需图连接，仅有共享研究词汇就在旧 8k/16k packet 入选；
另一个 old advisory Episode 也入选。来源是 selector/lexical candidates 与预算装填共同造成的
局部边界不足，不能据此倒推真实每一个历史对象究竟来自哪一条旧 selector 分支。
不是因为这些材料被数学验证或确认是当前路线的一部分。

保留旧安装源码的选材探针进一步确认：两个合成干扰对象 BM25 均为正分
（60.72 和 9.83），旧 selector 也把两者选为非 mandatory 项；它们没有直接目标关系。
因此这次合成误召回有确切的 lexical/optional selection 路径，不依赖推测“可能是高权威奖励”。
探针结果保留在 `before-selection-trace.json`，不把这两个合成分数冒充真实历史对象的分数。

旧 8k 还返回 7766 bytes 的不完整 proof，随后仍需 exact 读取整份正文，产生重复暴露。
旧 16k 则能直接塞入整份 17599-byte proof，calls 很少，但这不意味着合适的默认续研上下文。

## Selection policy

只收紧现有 `purpose=CONTINUE_RESEARCH`，不新增 mode 参数或 Agent/ranking runtime。
RECOVER_PROOF / TRACE_HISTORY / FIND_FAILURES 的一般选材，以及普通 research_search 实现不改。

- **MUST**：显式目标、选定 Gap 对应的指定 primary，以及这些根的确定性依赖闭包。
  不从 BM25 或“最新/权威”奖励创造 MUST。完整性失败、遍历 cap、missing 和预算 omissions 仍明确报告。
- **SHOULD**：直接针对目标的 proof/failed attempt/counterexample/refutation；
  最新完整、非纯 advisory、直接关联目标的持久 checkpoint；其已发表产物、产物的直接依赖，
  和 typed state_delta 明确引用的对象。沿用已有 candidate/review 身份 resolver。
- **MAY**：本轮 continuation 不自动填入无图/持久关联的历史；预算可以留空。
  想追查其他路线时再显式 search / TRACE_HISTORY，不因同 Problem 或词汇重合自动扩展。

checkpoint 按 `(imported_at, episode_id)` 倒序，跳过失败 digest、source-digest advisory、
无实际对象/状态增量、重复 local IDs 和不关联目标的 publication；不会让更晚的无关新材料替换本地 checkpoint。
共同依赖或 Problem membership 本身不是 incoming route 的直接关联证明。
不创建身份数据库、embedding、reranker、模型规划器或 query-rewrite Agent。

## 内容和导航边界

必需对象保留已有正文/预算语义；可选材料提供 `selection_reason` 和 bounded navigation：
source_characters、已存 source span、exact_read_reason，以及存储 summary 或短 excerpt。
proof 默认不复制正文；checkpoint 只给 bounded typed source assertions，方向始终 advisory，
有 assertion count/truncation 提示，不把整个原文 proof 再嵌套进 packet。
完整证明需要时仍通过 1..8000 字符窗口的 exact get 读取。

非全文项 full_text=false/truncated=true，撤销 usable/trusted positive flags；
authority、verification、freshness、conditional/blocked 标签由现有共享投影提供，未放宽门禁。
`complete/required_set_complete` 仍只针对 required 集合，不代表 SHOULD 全部放入，更不是已理解完整研究状态。
新增可选字段用现有 Pydantic 下限支持的 wrap serializer；无值时不改变一般 packet 字段。
MCP status 没有增加正文，64 KiB envelope 和预算上限不变。

## Precision benchmark

[固定合成结构与执行方法](../benchmarks/precision/README.md)：主目标、Gap、输入三项 MUST，
checkpoint/三个产物/直接 failed route/反例六项 SHOULD，同 Problem 强重合但无关历史、旧 handoff，
以及需要 exact read 的大 proof。实际调用 LedgerAdapter，输出成本来自真实返回值。
before 使用保留的 `1.1.1+hardening.20261022` 安装源码，after 使用当前源码，
相同 replay 与需求，不修改已有 P0-3 tasks/gold，不将真实 IDs 加入生产选择器。

| 预算 | required identity | SHOULD before→after | irrelevant objects | irrelevant bytes / estimated tokens | restore calls | exact reads |
|---|---|---|---|---|---|---|
| 2k | 3/3 → 3/3 | 1/6 → 1/6 | 0 → 0 | 0/0 → 0/0 | 9 → 9 | 7 → 7 |
| 8k | 3/3 → 3/3 | 6/6 → 6/6 | 2 → 0 | 2732/911 → 0/0 | 5 → 5 | 3 → 3 |
| 16k | 3/3 → 3/3 | 6/6 → 6/6 | 2 → 0 | 2732/911 → 0/0 | 2 → 5 | 0 → 3 |

新 8k/16k packet 约 4.4k estimated tokens，不填满预算。
三档 required omissions、unsafe premise flags、packet 内重复 identity、local-reasoning calls 均为零。
2k 只恢复 1/6 SHOULD，不能宣称完整恢复所有 checkpoint/负面导航；需要这些材料时选约 8k 或 exact get。
8k/16k 的三个 exact calls 均为同一大 proof 的必要分页，不是重复导航。
16k calls 上升是主动将默认上下文与完整证明读取分开；没有把“越少越好”硬编码成通过条件。
proof 内容重复暴露由旧 8k 的 7766 bytes 降为零。
这些是 fixture 指定的证据需求，不能证明真实模型会自主省掉哪一次 exact read。

## 自动化和真实只读证据

新增 **14 项**正式回归，最终源码完整 pytest **334 collected / 334 passed / 0 failed /
0 skipped**，258.15 秒，退出 0。Ruff、format（136 文件，含 benchmarks）、
`python -m mypy`（95 源文件）、`git diff --check` 均实际退出 0。
首轮全量为 334 passed / 351.82 秒；随后将可选字段改为使用既有 Pydantic wrap API 的同值序列化，
才对最终源码再次完整回归。前后日志均保留，以 `full-final.*` 为最终证据。
未单独运行旧 Pydantic 版本矩阵，不将使用已有 API 说成所有依赖组合均实测通过。
受限环境和普通用户环境的相关合同回归均实际为 61 passed，分别为 117.06 / 61.80 秒；
前者输出曾延迟显示，但已完成，没有终止任何测试进程，也没有把未执行项目算作通过。

### 两个指定 checkpoint

合成首轮全量通过后，用当前源码共享 services/projection 对两个指定 Episode 作只读核验；
没有调用真实模型或 Codex Host，也没有走会创建临时锁的 MCP adapter。

| 核验入口 | 选中的局部 checkpoint | 8k packet tokens | required omissions | 选中 checkpoint 产物缺失 | 已记录直接负面对象缺失 |
|---|---|---:|---:|---:|---:|
| 共同 current Gap CLAIM-0017 | EPISODE-E6583D7957789B06 | 5558 | 0 | 0（3/3） | 0 |
| EPISODE-02B5B3613F9C03D8 的 claim 产物 | EPISODE-02B5B3613F9C03D8 | 3666 | 0 | 0（3/3） | 0 |
| EPISODE-E6583D7957789B06 的 claim 产物 | EPISODE-E6583D7957789B06 | 3812 | 0 | 0（3/3） | 0 |

三个 packet 的 rendered content 均未命中本轮指定的无关历史主题标记（具体值仅保留本地）；
定位 latest produced objects 和 Gap 不需要额外 lexical search，实际 search tool calls 为零。
两个 checkpoint 各自持久 publication 都是 claim/proof/evidence 三对象，
均保留 PROVISIONAL / NOT_CHECKED / CURRENT / CONDITIONAL。
共同 Gap 及未知输入保留 UNKNOWN / BLOCKED，未当成已证明的正前提。
checkpoint 元数据仍不授予数学权威，proof 正文没有被悄悄嵌入其他摘要。

直接 failed/counterexample 的检查分母在这些真实目标上为 **0**：没有找到明确 typed target/artifact
关系指向它们的独立失败/反例对象；“缺失为零”不能宣传为已找回某条数学上相关的失败路线。
有直接失败/反例时的召回由合成 6/6 SHOULD 覆盖。未让模型根据全文推断新的负面关系或迁移历史。
这不是数学 relevance gold、全历史正文搜索或任意同义词/公式的质量证明。

审计 hook 禁止研究目录写入/删除/重命名/权限修改，拒绝读取 notes 和普通研究文件。
实际读取的 **68 个 Ledger 文件**前后 SHA-256 相同，写入尝试为零；
已有共享图 reader 内部会扫描 registry 和其他 Problem 的记录，不代表对其他 Problem 开展查询/研究。
未复制数学正文到公开文档；私有 metadata/refs 和哈希明细留在 ignore 的
`dist/_run/context-precision-20261022/real-results.json`、`real-hashes.private.json`。
这是读取范围内字节稳定的观察，不是全局加锁数据库快照，也未修改任何研究记录。

## 文件和交付边界

新增 `retrieval/continuation_selection.py`；修改 `retrieval/packet.py`。
新增 `benchmarks/precision/` 的 corpus/evaluate/README、通用脚本
`scripts/evaluate_context_precision.py` 和 `tests/core_contracts/test_context_precision.py`。
本报告与双语 README 只做必要说明。

完整文件清单：

- 修改：`src/math_research/retrieval/packet.py`、`README.md`、`README.zh-CN.md`。
- 新增：`src/math_research/retrieval/continuation_selection.py`、
  `tests/core_contracts/test_context_precision.py`、`scripts/evaluate_context_precision.py`、
  `benchmarks/precision/__init__.py`、`benchmarks/precision/corpus.py`、
  `benchmarks/precision/evaluate.py`、`benchmarks/precision/README.md` 和本报告。

没有修改真实研究记录、既有 review/receipts、普通 search ranker、Agent policy、DSH 或 Codex enable 配置。
未发布、未刷新已安装插件缓存；before 缓存保留，后续 release/local installation 应明确使用最终源码。
阶段基线 SHA 核对只发现上述预期文件变化，没有丢失原有文件；新增/变更文本的凭据/私钥模式扫描无命中。
私有只读结果、metadata、hash 和所有构建/测试临时状态仍被 dist ignore 排除；没有打包真实研究数据。
模式扫描不等于任意秘密检测保证，本轮未进行正式分发包重建或发布审计。
最终 Git 为 `main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694`：
**37 tracked modifications、51 untracked files**（包含此前成果），index 无暂存，无 commit/push。

本轮支持停止继续增加功能，转入单独授权的 release/commit cleanup：盘点累积变更、确认公开文件/打包面、
版本化和本地安装验收，再由用户决定 commit/push/发布。这里不抢先执行这些 Git/发布步骤。
尚不能证明模型实际选材/事件识别、数学研究质量、任意长程 corpus 的 recall 或所有历史格式均无遗漏。
