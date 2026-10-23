# P1 vertical slice run 1：启动前检查记录

日期：2026-10-22。状态：**PREFLIGHT BLOCKED；尚未开始真实研究**。
命令执行目录均为 `D:\Projects\math-research-ledger`。
本报告是待续的实验记录，不能作为完成 state restore / research / continuity 的证据。

## 当前安装与实际会话

本轮按 [continue-research skill](../skills/continue-research/SKILL.md) 和当前用户明确的
continuation policy 执行；先核对运行实现，再读取真实 Problem。
本会话原始九工具 schema 中，status 没有 since，ingest 没有 dry_run。
原安装缓存 adapter 与当前源码 SHA-256 不同，不能直接开展要求使用 P0-3 的实验。

按本地 update-plugin workflow 和 [Codex 官方安装命令](https://learn.chatgpt.com/docs/developer-commands)，
通过现有 `scripts/prepare_local_plugin.py` 暂存当前运行时源码，保留旧目录，未手工覆盖安装缓存。
只在忽略的本地 marketplace 中切换该插件的 source path；marketplace 原清单已备份。
暂存版本使用 `1.1.0+vslice.20261022` 作为 cachebuster，没有更改工具仓库公开版本或发布。
执行 `codex plugin add math-research-ledger@math-research-ledger-local --json` 成功，退出 0。
新版安装的 94 个 Python/Markdown 运行时文件与当前工作树逐字节一致。

安装成功不等于当前对话的 MCP 连接已经重建：

- 当前对话：工具 schema 仍旧；对已有合成 workspace 的一次原生 `research_status` 探针
  返回 `INTERNAL_ERROR`。没有据此断言具体内部异常根因，也没有尝试对真实数据复现。
- 新启动的 Codex app-server：九工具发现成功，status 有 since、ingest 有 dry_run；
  对同一个已有合成 workspace 的一次 status 成功，包含 explicit Problem / continuation。
  该 Host 没有调用模型，没有读取真实研究记录；它不能替代本对话的实际连接验收。
- 本机受限执行环境的 CIM 进程查询被拒绝，未尝试提权或更改权限。

本地忽略证据目录：`dist/_run/vertical-slice-p1-run1-20261022/`。
其中 `marketplace.before.json` 保存旧本地源清单，`fresh-host-preflight.json` 保存新 Host
schema 判断和合成返回；不包含真实数学正文、认证数据或真实研究 transcript。

## 本轮实验计数

| 阶段 | 实际结果 |
|---|---|
| 当前对话插件探针 | 合成 status 1 次，失败；不计真实 session restore |
| 新 Host 安装探针 | tools inventory 1 次；合成 status 1 次成功 |
| 真实 P1 session-start calls | 0 |
| 真实 Gap 选择 / 人工 relevance baseline | 未执行、未冻结 |
| context retrieval / omission / irrelevant history | 未执行，不能判定 |
| 自由研究 / Ledger 调用 | 未开始 / 0 |
| 后续 event-triggered calls | 0 |
| 避免重复 failed route | 未评估 |
| 研究增量 / preview / ingest | 无 / 0 / 0 |
| next-session continuity | 未执行，按计划留到真正的新会话 |

没有为跑通实验改 gold、ranker、业务代码、DSH、ACL 或认证。
只读取真实 workspace 的 AGENTS.md 以了解研究约束，没有通过工具或底层读取真实 P1 记录。
没有操作其他 Problem、notes repo、canonical/review/verification/acceptance，没有创建真实 Episode。
本轮只新增此实验记录；此前所有未提交代码、未跟踪文件和构建证据保留。
未 add、commit、push。

## 继续步骤

1. 重新加载本对话的 MathResearch Ledger 插件连接；必要时重启 Codex，再回到本对话继续。
   这是启动前恢复，不是最终 ingest 后的 blind continuation。
2. 确认当前连接暴露新版 schema，并可通过合成只读探针。
3. 按用户原任务显式 status(PROBLEM-0001)，精确读取主目标，再判断真实 Gap 及其依赖。
4. 冻结这一个 slice 的少量 relevance/MUST baseline；数学相关性尚未判断的条目留给研究者。
5. 约 8k context 够用即停止 retrieval，执行一次有边界的自由研究；仅事件触发额外读取。
6. 有真实增量才准备完整 Episode，逐项理解 preview warnings，ERROR=0 后最终单次 ingest。
7. 完成 ingest 后立即停止，另起真正新对话做 blind continuity；不在本对话模拟。

本轮没有生产代码变更，不重跑完整回归或重建 Bundle。
P0-3 的 300 passed 是上轮源码回归证据；本轮实际检查为安装、94 文件一致性、新 Host schema/
合成 status 与文档 diff 检查，不能将历史回归数字包装成本轮研究实验结果。
