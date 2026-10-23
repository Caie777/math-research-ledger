# DSH 适配阶段交接：2026-10-22

当前结论：工程构建与回归可交接；**真实 Windows 工作区验收未完成，不能宣传为所有用户安装即用。**
Windows/DSH 真实环境排障按用户要求冻结。本轮没有启动 DSH Desktop、Host 或模型，
没有访问真实研究记录、用户 Profile、认证存储或 notes 仓库，没有修改任何 Windows 安全属性。
本文件是当前状态入口；[Bundle 工程报告](dsh-plugin-report.md) 和
[锁修复报告](windows-lock-fix.md) 保留各自历史证据，不把历史通过等同于当前真实会话验收。

所有本轮代码检查、测试、构建、导入与 Git 命令的执行目录均为
`D:\Projects\math-research-ledger`。本轮只修改文档，并重新构建本地分发包；
保留全部已有源码修改、未跟踪文件、旧运行时、旧包和测试证据。

## 仓库与证据归属

| 位置 | 职责与边界 |
|---|---|
| `D:\Projects\math-research-ledger`，`Caie777/math-research-ledger` | 工具、Codex 插件、DSH Bundle 源码；当前分支 main |
| `D:\Math Research` | 用户/Harness 的统一数学研究工作区，Ledger 只拥有 `.math-research-ledger/` |
| 上述工作区内 `math-research-notes`，`Caie777/math-research-notes` | 嵌套的独立成果发布仓库；只发布用户选择的成熟成果，本轮未操作 |

研究私有状态、workspace.yaml 和研究 AGENTS.md 应保持 local-only；插件不自动 Git staging、
commit、push 或选择公开成果。这里的规范路径是用户要求归档的诊断上下文，不是公开插件默认配置；
分发包不包含这些本机路径。历史 provenance 不改写。

盘点与结束时 HEAD 均为 `60bf0d04b95624bcf9f1269c2e66a7a4a5053694`，index 无暂存变更。
进入本轮时有 9 个已跟踪文件被修改、13 个未跟踪文件；结束时为 9 个被修改、14 个未跟踪，
新增的是本文。原有 DSH Bundle、构建脚本、锁测试和两份专题报告尚未进入 Git；
atomicio.py 与 MCP server 的修复也只在工作树中。既有 1ee3d42、1bdc8d5、ff89a9c、60bf0d0
属于已提交历史，不能据此认为本地 Bundle/锁修复已公开。没有 add、commit、push、reset 或 clean。

完整工作树清单（M 为相对 HEAD 修改，? 为未跟踪；不表示全是本轮新增）：

```text
M .gitignore
M MANIFEST.in
M README.md
M README.zh-CN.md
M docs/finalization-report.md
M docs/research-workspaces.md
M integrations/deepseek-harness/README.md
M src/math_research/core/atomicio.py
M src/math_research/mcp/server.py
? docs/dsh-adaptation-handoff-2026-10-22.md
? docs/dsh-plugin-report.md
? docs/windows-lock-fix.md
? integrations/deepseek-harness/bundle/README.md
? integrations/deepseek-harness/bundle/cordis.patch.yml
? integrations/deepseek-harness/bundle/index.mjs
? integrations/deepseek-harness/bundle/install.py
? integrations/deepseek-harness/bundle/package.json
? integrations/deepseek-harness/bundle/transport.mjs
? integrations/deepseek-harness/host-smoke.cjs
? scripts/build_dsh_bundle.py
? tests/core_contracts/test_dsh_bundle.py
? tests/core_contracts/test_file_lock.py
? tests/core_contracts/test_lock_mcp.py
```

本轮编辑范围仅为本文、README.md、README.zh-CN.md、docs/dsh-plugin-report.md、
docs/windows-lock-fix.md、docs/finalization-report.md、DSH 安装指南和 Bundle README；
其余已有工作保留。忽略目录里的新构建/审计日志另计，不加入 Git。

## A. 已完成并有证据支持

### 官方接入及历史 Host 证据

历史只读调查使用官方 Desktop/CLI/MCP client `0.2.1-rc.2`，Node 24.21.0、pnpm 11.28.5。
本轮未重新查询真实安装。支持范围声明为 DSH `>=0.2.1-rc.2 <0.3.0`、Node 22.15+、Python 3.11+，
不等于已在该范围所有版本验收。

官方 Bundle 契约是 `package.json -> dsh.bundle.patch -> cordis.patch.yml`。
适配入口复用 `@deepseek-ai/dsh-mcp-client` 的连接、发现、注册与释放；Core Services、Ledger、
workspace resolver、九个工具 schema 和人工权威边界与 Codex 共用，没有第二套 Agent loop/数据库。
安装和卸载方式已写入[安装指南](../integrations/deepseek-harness/README.md)：

```text
python scripts/build_dsh_bundle.py FRESH_BUNDLE_DIRECTORY
python FRESH_BUNDLE_DIRECTORY/install.py
dsh plugin --profile PROFILE add ABSOLUTE_BUNDLE_DIRECTORY
dsh plugin --profile PROFILE remove dsh-math-research-ledger
```

预先解包并运行显式安装器，再注册稳定的目录；Desktop 保留 Profile 必须使用 Desktop 自带 dsh。
原生 Plugins 页进行 Profile 级启用/禁用；HMR 可用时即时应用，否则重载/重启。
OFF 不删除数据，卸载也不删除研究状态；关闭后的零工具结果来自历史实际 Host 证据，不是清单推断。
安装器创建 Bundle 私有 `.venv`，验证导入后保存私有 `.runtime.json`，不初始化研究状态。
这是独立依赖环境，仍依赖本机基础 Python，不是附带可移植解释器二进制。

| 证据层级 | 已核对的结果 | 限制 |
|---|---|---|
| 历史隔离 Host | `dist/_run/host-assertions.json`：ON/OFF/ON = 9/0/9；status 为 1 个合成 Problem/对象，search 命中合成 PROBLEM-0001；无模型，合成文件字节不变 | 发生于后续锁修复之前，本轮不重跑，不认证当前真实会话 |
| 历史解释器追踪 | 4 次 MCP 启动均使用 Bundle 内 Python，未用开发 venv | 不是当前运行进程的证明 |
| 用户提供的真实 Desktop 诊断 | 已安装、服务启动、MCP 握手/tools/list 成功，九个工具注册 | 是用户会话观察；本轮不再次读取 Profile 或调用 Host；不等于数据访问成功 |
| 本轮静态/自动化核对 | 九个既有工具的 schema、Bundle 清单、启动/缺失运行时诊断、真实 stdio、锁与权限边界测试均在全套回归中通过 | 不替代 GUI 或真实工作区验收 |

九个工具职责见安装指南；名称为 research_status、research_search、research_get_object、
research_context_packet、research_review_packet、research_stale_report、research_ingest_episode、
research_save_note、research_request_acceptance。模型没有 accept、任意文件写入或 shell 工具。

### 锁修复与异步路径

当前代码链仍为 `research_status -> LedgerAdapter.call -> checkpoint_read -> file_lock(.checkpoint)`。
只读 status 保留临时锁，以免 checkpoint 两个索引发布期间读到混合代际并绕过恢复 journal。
没有为沙箱放宽一致性和权限边界。轮询使用有限 monotonic deadline 并休眠；仅 EEXIST 表示竞争。
普通拒绝访问、无法 stat 或清理会返回可诊断错误；Windows 5/32/303 最多三次短重试，
总 deadline 可更早结束。原子替换、并发互斥、失败清理仍保留。

历史注入错误复现旧代码 201 次 open、仅一次 deadline 检查、零次 sleep，确认旧版确有无限忙等缺陷；
该复现不能证明它就是最早真实 DSH timeout 的根因。当前测试覆盖 23 个锁用例，包括正常释放、
竞争超时、无锁文件时拒绝访问、stat/清理异常、Windows 分支、原子写入失败保留原文、
合成 status 与四进程共 60 次递增。全部包含于本轮 176 项通过结果。

MCP 通过 AnyIO worker thread 执行同步 LedgerAdapter 服务调用，锁等待不会直接占用 stdio 事件循环。
两个真实注册 handler 的异步 heartbeat 测试覆盖 Windows 拒绝访问和锁竞争；本轮均实际执行通过。
workspace 解析中的少量同步路径/元数据检查仍存在；测试不声称为任意慢盘或网络文件系统提供硬实时保证。
没有发现本轮需要进一步重构的证据。

### 本轮实际回归（非历史数字）

执行目录统一为 `D:\Projects\math-research-ledger`；沿用已授权的普通用户本地 IPC 测试环境，
不使用管理员权限，不启动 DSH，不改变沙箱/ACL/账户配置。TMP/TEMP 和 basetemp 均在本轮 dist 子目录。

```powershell
$env:TMP = (Resolve-Path dist/_run/archive-20261022/tmp).Path
$env:TEMP = $env:TMP
.\.venv-win\Scripts\python.exe -X faulthandler -m pytest -p no:cacheprovider --basetemp dist/_run/archive-20261022/pytest-temp --junitxml dist/_run/archive-20261022/pytest.xml -o faulthandler_timeout=30
.\.venv-win\Scripts\python.exe -m ruff check src tests scripts
.\.venv-win\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv-win\Scripts\python.exe -m mypy --cache-dir dist/_run/archive-20261022/mypy-cache
git diff --check
```

复现时应选新的临时目录，不复用已经存在的 basetemp。

| 本轮检查 | 实际结果 | 退出码 |
|---|---|---|
| 完整 pytest | 收集/执行 176，passed 176，skipped 0，failed/errors 0；69.87 秒 | 0 |
| 锁/异步/stdio 子集（从同次 JUnit 核对，不重复执行） | 23 锁 + 2 异步 + 12 stdio，均通过 | 完整 pytest 为 0 |
| Ruff | All checks passed | 0 |
| 格式 | 110 files already formatted；与历史报告的 111 分属不同次记录 | 0 |
| mypy | 86 source files 无问题 | 0 |
| git diff --check | 通过；Git 的换行转换提示不是检查失败 | 0 |
| Python wheel 构建 / 实际 npm pack | 两者成功，实际 8 个成员 | 各 0 |
| 既有 Bundle Python `-I -B` 导入 | math_research.mcp.server 与 mcp 成功导入 | 0 |

历史受限环境 faulthandler 日志再次核对为 socket.accept -> fallback_socketpair ->
asyncio self-pipe/new_event_loop -> anyio.run，发生在 handler 执行之前；不是锁测试已运行的证据。
本轮完整测试实际通过，没有把历史 151、161+1 或 176 的结果替代当前执行，也没有删测试。
Codex 清单、Skills、MCP schema、checkpoint 协议和其他 Ledger/检索/验证业务源码相对 HEAD 没有改动；
既有 atomicio/server 修改本轮未再编辑。现有 Codex 合约及真实 stdio 测试通过，不声称重新验收了真实 Codex 会话。

### 当前产物与旧证据分开保存

新产物：`dist/_run/archive-20261022/dsh-math-research-ledger-1.1.0.tgz`。
SHA-256：`f69e17c001e1b78f838cd024c008085bdcda70dab8a8213fa1fecf4cd2c11ec5`。
构建到新的 `dist/_run/archive-20261022/bundle`，没有覆盖已有安装目录或运行时；本轮只更新包内说明。
新 wheel 的全部 math_research 包文件与当前 src 逐字节一致；七个外层文件与当前 Bundle 源文件/许可证一致。
实际 npm pack JSON 与 tar 成员一致，恰好包含：

```text
package/LICENSE
package/README.md
package/cordis.patch.yml
package/index.mjs
package/install.py
package/package.json
package/runtime/math_research_ledger-1.1.0-py3-none-any.whl
package/transport.mjs
```

外层与内层 wheel 共扫描 100 个文件，无私有研究数据、实际本机路径、凭据标记、运行时指针或本地配置发现。
清单不存在 .venv、研究目录、Profile、日志或 transcript；这是本地包内容审计，不是远端发布审计。
两个已有本地 Bundle 的 wheel 全包文件、已安装 atomicio/server 均与当前修复源码一致；没有重装或重启它们。
固定源码 SHA-256：

```text
atomicio.py 32340f12e360eb97718962db0f6610862af6fcf9f028acc358f71ce4603e2508
mcp/server.py cae09d50d96761d0d9ff7fa15dbde6c23bda9483bec6ffc878d037e0e31073e4
```

旧 `dist/dsh-math-research-ledger-1.1.0.tgz` 仍保留，SHA-256 为
`947113b7e762751c7128a0e7011446d2e2bfd32b0ef2b4cff868f44cbb200799`。
旧 wheel 的服务代码仍匹配；其 README 不含本轮状态告知，不能当作最新分发包。
新旧哈希不同是重新构建/说明更新，不能混用旧报告哈希标记新包。

本轮日志、JUnit、退出码、npm-pack.json、静态检查和 current/original-artifact-audit.json
位于忽略的 `dist/_run/archive-20261022/`；早期 dist/_run/lock-fix、lock-fix-ipc、Host 证据全部保留。
dist 未被 Git tracked，运行时、临时 Profile、日志不会进入此 tarball；不得把整个 dist 上传。

## B. 已确认的真实环境问题：观察与解释分开

**用户提供的直接观察（本轮不独立重测）：**真实 DSH 会话九个工具已注册，MCP 链路可工作；
对 `D:\Math Research` 调用 research_status 仍被拒绝创建 `.math-research-ledger\.checkpoint.lock`。
沙箱 Python 为 Low Integrity；工作区根目录已成功取得 Low Integrity 标签，
但既有 `.math-research-ledger` 目录及旧内容仍为 Medium Integrity。

**依据这些观察的机制解释：**Windows Mandatory Integrity Control 的 no-write-up 限制
禁止 Low Integrity 进程向 Medium Integrity Ledger 子目录创建锁文件，是当前拒绝访问的直接机制。
仅根目录的标签变化不证明既有子树已变化；这与最早 timeout 是否由旧忙等触发是两个不同判断。
锁修复使权限错误在有限重试后明确返回，不负责修改安全属性，也没有解决当前 MIC 问题。
本轮未执行 icacls、安全属性查询/修复或任何真实数据调用，不把解释冒充为本轮独立测量。

## C. 明确未完成

1. 真实数学工作区的 research_status 尚未成功。
2. 状态查询失败，真实工作区 research_search 尚未通过验收；不借用 Codex 或合成结果替代。
3. 尚未对真实 `.math-research-ledger` 执行用户批准的定向完整性标签修复；本轮没有执行该操作。
4. 尚未证明重启 Desktop 后真实工作区可正常读写，GUI 用户会话的完整启停/重启验收也未完成。
5. macOS/Linux Host 未测试；跨平台路径实现和自动化适配合约不等于 Host 实测。
6. 当前锁修复后没有新的隔离 DSH Host 9/0/9 测试；本轮按冻结要求不补跑 Host。
7. 没有社区/注册中心发布；所有改动仍待用户代码审查与独立决定提交。

## D. 下一阶段按依赖恢复（本轮只归档）

1. 用户明确批准后，先决定是否对 `.math-research-ledger` 做定向 Low Integrity 标签修复；
   单独审查安全影响、备份和目标范围，不改整个研究目录 ACL/所有者，不自动改 Full Access。
2. 核对使用的包与上述源码哈希，使用 Desktop 官方方式重新加载插件并新建真实工作区会话；
   文件更新不代表旧进程已经重新导入模块。
3. 只调用 research_status，核对 workspace 和预期计数；成功后再用 bounded research_search
   核对 PROBLEM-0001 的实际命中，不预设结果、不扩大读取范围。
4. 另行授权后验证真实研究记录的读取与写入边界、provisional/human authority、重启后的行为，
   不为验收自动生成研究内容或 human acceptance。
5. 根据实际结果补齐安装/卸载、Windows 故障排查与必要的 macOS/Linux Host 验收。

用户目前无需为工程归档执行任何手动操作。上述真实安全属性决策、Desktop 重载和会话验收
均留给用户后续安排；本阶段安全暂停，不继续真实 DSH 排障。
