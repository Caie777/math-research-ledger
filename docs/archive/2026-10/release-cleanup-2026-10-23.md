# Release / commit cleanup：2026-10-23

> Historical engineering evidence; results refer to the recorded revision, not a new acceptance.
> Machine-specific locations are generalized. See [current limitations](../../known-limitations.md).

当前准备版本：**1.2.0，未发布、未提交**。所有检查、测试、构建和 Git 命令执行目录均为
`<repo>`。本轮不开展数学研究，不访问真实研究记录、notes 仓库、
真实 DSH Profile 或认证存储，不修改 ACL / MIC，不运行真实 Harness 或模型。

本报告是当前 release 工程整理入口。2026-10-22 各专项报告中的测试数字、包哈希、
本地安装版本、Git 文件数和“当前”措辞只描述各自当时的状态，不能代替下列本轮结果。
DSH 的冻结状态仍以[阶段交接](dsh-adaptation-handoff-2026-10-22.md)为准。

## Inventory 与公开边界

初始状态为 `main@60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，37 个 tracked 修改、
51 个 untracked 文件，index 无暂存。先生成只读 inventory，再保存候选文件哈希和编辑前副本。
没有删除、移动、覆盖未知文件，也没有 reset 或改写历史。

| 分类 | 结果 |
|---|---|
| A：公开候选 | 初始 78 个源码、合成 fixtures/tests、脚本、清单、说明；另 10 份报告经审查后纳入 |
| B：本地保留 | 初次 Git 枚举 217,612 个 ignored 文件；含证据、缓存、venv、构建包、私有元数据与配置备份 |
| C：需判断 | 初始 10 份历史报告；已核对来源及内容，未留待决文件 |
| 最终计划提交 | 95 个变更文件：42 个 tracked 修改、53 个 untracked；清单见文末 |
| 从候选移出或删除 | 0；已有本地证据全部保留 |

B 类数量是本次 Git 可枚举文件数，旧路径有 Windows 长路径/失效测试链接警告，
不是完整文件系统 census。本轮新增的测试、安装和打包文件也全部留在 ignored `dist/` 下，
未为精确统计缓存而反复遍历。`dist/_run/`、`.local/`、`.local-eval/`、venv、cache、
日志/XML、Bundle 私有 runtime pointer 已被现有规则覆盖；本轮无需额外扩大 ignore 范围。
正式 benchmarks、JSON gold/tasks、脚本、文档均未被误忽略。

对 tracked 与非 ignored untracked 公共候选执行了文件名、文本模式和人工语境审查：

- 未发现密钥赋值、raw token、私钥、Windows 用户主目录、配置备份、私有 candidate JSON、
  corpus 哈希清单或真实 model transcript 被纳入候选。
- email 模式的一处命中实际是 Codex plugin ID 配置键，不是邮箱或账号凭据。
- 历史报告存在已授权的研究定位 IDs、聚合统计与工程执行路径，没有复制研究记录正文或数据库。
  context precision 报告中两处具体研究主题词已泛化；原文副本保留在本地证据目录。
  合成 fixtures 中明确标注的无关主题词不是实际命题/证明，也没有改 gold/ranker 来改善结果。
- `D:\Projects\...` 是历史命令执行位置；少量研究目录路径是现场诊断上下文。
  公共运行时清单没有绑定这些目录。`C:\path\to\your\research`、`/absolute/path/...` 是示例。
- 文档对 ignored evidence 文件名的引用不包含对应内容。本地 cache 的 `+vslice` / `+hardening`
  仅作为历史安装观察保留，不作为正式版本。

这是候选与实际分发包的审计结果，不是秘密检测的绝对保证，也没有重写 Git 历史或扫描真实语料。

## 累积 diff 审查与最小整理

| 范围 | 审查结论 |
|---|---|
| identity / dependency / premise | scoped identity 与 authored pins 共用；无历史 pin 保持 UNKNOWN，不用当前版本伪造历史 |
| Episode / integrity | 预检 ERROR 阻止结构化发布；digest/JSONL fail closed；仍只写 provisional |
| continuation | 显式 Problem；checkpoint/产物导航从持久 proposals/reviews 派生；advisory 不自动生效 |
| retrieval / packet | exact ID 先于 lexical；continuation 只按记录关系选局部材料；可选 proof 给导航，不填满预算 |
| MCP | 仍为九工具；bounded outputs 与 server-side authority gates 保留；同步文件 IO 在线程运行 |
| benchmarks / scripts / tests | fixtures 为合成；gold/tasks 固定；生产代码不导入 benchmark；真实只读证据留在 ignore |
| Codex | project-scoped 使用说明保留；只修正 skill 段落中的句子断裂，没有刷新缓存或改用户配置 |
| DSH | 官方 Bundle/安装器及锁修复的历史工程资产保留；真实 Windows MIC 排障继续冻结 |

未发现需在 cleanup 中扩展架构的事项；未引入 debug/TODO 清理式重构。
旧 `structured-math-research` 仅保留在明确的旧 MCP 迁移命令和历史说明中。
修正了两处将 authoritative JSONL reader 描述为 tolerant/silent-drop 的过时注释。

本轮新增 CHANGELOG；双语 README 仅增加版本和当前整理入口。`MANIFEST.in` 补齐
benchmark Python/JSON/Markdown 与 CHANGELOG，并排除字节码，避免源码包缺少测试依赖的 fixtures。
CI 改为安装 `[dev,mcp]`，把 scripts/benchmarks 纳入 Ruff，并使用 `python -m mypy`，
避免依赖缺失导致 MCP 测试被跳过。本轮没有在远端运行 CI。

## Release identity

本地无 tag；进入本轮时 Python 动态版本、portable plugin、Codex overlay 和 DSH package
均为 1.1.0。未查询注册中心/远端来推断其发布状态。
新增能力保留九工具、主要参数及兼容 aliases，故准备下一个 minor 版本 **1.2.0**。
Python 唯一版本源为 `math_research.__version__`，pyproject 动态读取它；两个插件清单、
DSH package、实际 wheel/sdist 元数据及 README 均一致。

保留 `math_research` import，以及 `math-research-ledger`、`math-research`、`smr` 和 MCP CLI aliases。
收紧损坏内容/无效结构处理是有意的 fail-closed 行为，见 [CHANGELOG](../../../CHANGELOG.md)。
本轮未创建 tag、提交、push 或 registry 发布；既有安装缓存仍是历史本地测试版本。

## 本轮实际验证

执行目录：`<repo>`。使用仓库 Python 环境及新的 dist 临时目录。
完整回归在允许本地 IPC 的普通用户环境运行，不使用管理员权限、真实 DSH 或研究数据。

| 检查 | 实际结果 |
|---|---|
| 完整 pytest | collected 334；334 passed；0 failed、0 errors、0 skipped；648.17s；退出 0 |
| Ruff check src tests scripts benchmarks | 退出 0 |
| Ruff format --check src tests scripts benchmarks | 136 files already formatted；退出 0 |
| python -m mypy | 95 source files；退出 0 |
| git diff --check | 退出 0 |
| Python build | 1.2.0 wheel 与 sdist 构建成功；从解包 sdist 重建 wheel 成功 |
| manifests / portable staging | 既有 plugin 合同测试通过；最终 portable stage 只含源码、skill、清单、launcher 与 license |
| 干净安装 | 新 venv、无 system-site-packages，离线 wheelhouse 安装 `[mcp]` 成功；pip check 退出 0 |
| 安装后真实 stdio smoke | `-I -B` 从新 venv site-packages 加载；实际发现九工具，schema 全匹配；合成 status/search 成功 |
| DSH 打包 | 因同步 package 版本/状态说明而重建并实际 npm pack；8 文件 allowlist 通过；未运行 Host |

pytest 参数包含 `-p no:cacheprovider --basetemp dist/t12`、JUnit、faulthandler；
合成工作区不在仓库根部。锁权限异常、并发原子写入、异步响应性、真实 stdio、
authority/provisional gate 和 Codex 便携合同均在完整套件内实际执行，没有跳过。

临时安装 smoke 脚本最初误假定存在 `ok` 字段，又误把 ref 字典当字符串；
两次均为测试脚本断言错误，按实际既有 schema 修正后成功，没有改产品返回结构。
首次包检查脚本将 METADATA 换行假定为 LF，改用 splitlines 后通过。
所有失败日志/后续结果保留，没有通过删除测试获得绿色结果。

## 实际包边界

wheel 含 102 个文件，其中 96 个 production 源码/模板与当前工作树逐字节一致。
sdist 含正式 tests、benchmark Python/JSON fixtures、插件清单、skill 与文档；
从它重建 wheel 验证源码分发路径可用。最终包清单、SHA-256 与检查结果保存为本地 `packages.json`。

实际 DSH `.tgz` 恰含：

```text
package/LICENSE
package/README.md
package/package.json
package/cordis.patch.yml
package/index.mjs
package/transport.mjs
package/install.py
package/runtime/math_research_ledger-1.2.0-py3-none-any.whl
```

包内 wheel 的 96 个源码/模板也与当前工作树一致。外层及 wheel/sdist 没有 `.venv`、
`.runtime.json`、Ledger 状态目录、研究数据、raw credential、本机 runtime 配置或日志。
源码分发内历史报告的执行路径/聚合元数据按前述边界保留，不作为可执行配置。

本地证据统一放在 ignored `<local-evidence>`：inventory/before 副本、
full.log/xml/exitcode、静态检查、安装/stdio smoke、build/npm-pack/package-audit 及最终清单。
旧 dist 产物、运行时、配置备份和历史证据原样保留。没有安装到真实 Codex/DSH Profile。

## 建议提交顺序（未执行）

1. `fix: bound file locking and package the native DSH adapter`
   包含锁和 MCP scheduling 修复、对应 file_lock/lock_mcp tests，以及原生 Bundle、安装/构建脚本、
   test_dsh_bundle 与其历史说明。错误类型声明可先进入；版本仍保持本阶段一致，最终统一在第 4 项。
2. `feat: harden research identity and episode integrity`
   包含 identity/bindings/premises、统一读取/预检/发布 gate、projection/freshness 及对应 dependency、
   Episode、Ledger、stdio tests；adapter 与 retrieval 只选择属于此项的 hunks。
3. `feat: add continuation navigation and scoped context retrieval`
   包含 continuation/publication、exact-ID/UNKNOWN 导航、memory policy、局部 context 选择、
   benchmarks/fixtures/scripts 与对应 tests；补齐这些 fixtures 的 sdist 清单。
4. `chore: prepare the 1.2.0 release and audit documentation`
   统一四处版本来源、CI、README、CHANGELOG、scope 使用说明、skill 语句修复及剩余历史/整理报告。

共享 adapter、packet、manifest 和 service 文件跨第 2/3 项，后续应按功能 hunks 分配，
不能直接按整文件批量 add。实现和对应测试一起提交；各边界在真正提交前需核对 imports 与针对性测试。
本轮只是计划，未生成这些提交，也没有重写远端历史。

## 暂停点与后续授权

当前仍为 main 和原 HEAD，42 modified + 53 untracked，staged=0，无删除文件。
下面 95 个变更文件可进入下一步逐项 staging/commit 审阅；本轮到此停止，不 add/commit/push。
push 仍需届时核对 remote 和 ahead/behind，再由用户授权。

DSH 真实 Windows 工作区 status/search、Desktop 重启后的读写边界、macOS/Linux Host
仍未通过验收。打包和隔离 MCP smoke 不解决 Low/Medium Integrity 问题，也不替代真实 Host 验收。
Codex 正式 1.2.0 安装刷新与真实会话体验需后续安排；不要把历史 cache 版本当成已升级。
用户此刻无需操作研究目录、权限、认证或 Profile。

## 计划提交的逐文件清单

```text
.codex-plugin/plugin.json
.github/workflows/ci.yml
.gitignore
CHANGELOG.md
MANIFEST.in
README.md
README.zh-CN.md
benchmarks/__init__.py
benchmarks/continuity/README.md
benchmarks/continuity/__init__.py
benchmarks/continuity/corpus.py
benchmarks/continuity/evaluate.py
benchmarks/continuity/gold.json
benchmarks/continuity/tasks.json
benchmarks/precision/README.md
benchmarks/precision/__init__.py
benchmarks/precision/corpus.py
benchmarks/precision/evaluate.py
docs/codex-mcp.md
docs/context-precision-after-vertical-slice-2026-10-22.md
docs/core-product-audit-2026-10-22.md
docs/dsh-adaptation-handoff-2026-10-22.md
docs/dsh-plugin-report.md
docs/finalization-report.md
docs/p0-continuity-evaluation-2026-10-22.md
docs/p0-dependency-closure-2026-10-22.md
docs/p0-episode-integrity-2026-10-22.md
docs/release-cleanup-2026-10-23.md
docs/research-workspaces.md
docs/vertical-slice-continuity-hardening-2026-10-22.md
docs/vertical-slice-p1-run1-2026-10-22.md
docs/windows-lock-fix.md
integrations/deepseek-harness/README.md
integrations/deepseek-harness/bundle/README.md
integrations/deepseek-harness/bundle/cordis.patch.yml
integrations/deepseek-harness/bundle/index.mjs
integrations/deepseek-harness/bundle/install.py
integrations/deepseek-harness/bundle/package.json
integrations/deepseek-harness/bundle/transport.mjs
integrations/deepseek-harness/host-smoke.cjs
plugin.json
scripts/build_dsh_bundle.py
scripts/evaluate_context_precision.py
scripts/evaluate_continuity.py
scripts/prepare_continuity_candidates.py
scripts/replay_continuation_navigation.py
skills/continue-research/SKILL.md
src/math_research/__init__.py
src/math_research/core/atomicio.py
src/math_research/core/errors.py
src/math_research/core/integrity.py
src/math_research/core/jsonl.py
src/math_research/core/research_agents.md
src/math_research/ledger/archive.py
src/math_research/ledger/bindings.py
src/math_research/ledger/continuation.py
src/math_research/ledger/decomposition.py
src/math_research/ledger/dependencies.py
src/math_research/ledger/episodes.py
src/math_research/ledger/identity.py
src/math_research/ledger/manifest.py
src/math_research/ledger/premises.py
src/math_research/ledger/preview.py
src/math_research/ledger/projection.py
src/math_research/ledger/provisional.py
src/math_research/ledger/publication.py
src/math_research/ledger/readers.py
src/math_research/ledger/sources.py
src/math_research/ledger/state.py
src/math_research/ledger/target.py
src/math_research/mcp/adapter.py
src/math_research/mcp/server.py
src/math_research/retrieval/context.py
src/math_research/retrieval/continuation_selection.py
src/math_research/retrieval/index.py
src/math_research/retrieval/memory_policy.py
src/math_research/retrieval/packet.py
src/math_research/retrieval/recall.py
src/math_research/retrieval/selection.py
src/math_research/services/ingest.py
src/math_research/services/research.py
src/math_research/services/retrieval.py
src/math_research/services/stale.py
src/math_research/verification/freshness.py
tests/core_contracts/test_context_precision.py
tests/core_contracts/test_continuation.py
tests/core_contracts/test_continuity_benchmark.py
tests/core_contracts/test_continuity_hardening.py
tests/core_contracts/test_dependency_closure.py
tests/core_contracts/test_dsh_bundle.py
tests/core_contracts/test_episode_integrity.py
tests/core_contracts/test_file_lock.py
tests/core_contracts/test_ledger.py
tests/core_contracts/test_lock_mcp.py
tests/core_contracts/test_mcp_transport.py
```
