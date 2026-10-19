"""Public same-session policy and a narrow finalization guard; no math authority."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from math_research.memory.handoff import HANDOFF_FIELDS, read_handoff, resolved_work_ids
from math_research.memory.state import KnowledgeStateResolver
from math_research.memory.target import ResearchTarget

CompletionState = Literal["CONTINUE", "TARGET_RESOLVED", "ROUTES_EXHAUSTED", "LOW_MARGINAL_VALUE"]
COMPLETION_STATES = ("CONTINUE", "TARGET_RESOLVED", "ROUTES_EXHAUSTED", "LOW_MARGINAL_VALUE")

REFLECTION_EVERY = 8
MAX_CONSECUTIVE_TOOL_FAILURES = 3
CONTINUATION_POLICY = """继续研究所选的未解决目标。
先利用既有 canonical / provisional 研究历史和最新 Research Handoff，避免重复已经完成的工作。
PROVISIONAL 和 source-reported 结果只是工作假设，不是定理真值；
MODEL_CONFIRMED 和 verifier passed 都不等于 Human Accept。
可自由探索证明、等价改写、结构分类、精确计算、文献、反例和边界分析。
此前成功的路线可以继续，但不是强制路线；真正有进展时不必为了换路线而换路线。

当你得到有价值的中间结果、引理、分类、计算规律或局部证明时，先通过 save_notes、
save_experiment_result 保存进展，利用周期 checkpoint，然后在同一个 native thread 继续研究。
得到新的 lemma / RESULT / PROOF，不等于整个 Explore Session 应该结束。
不要仅仅因为已有可写入 Research Episode 的阶段性成果，就调用最终交接工具或结束会话。
如果当前目标仍未解决，而且能明确指出一个值得执行的下一步，原则上应继续推进。

只有以下情况之一成立时，才主动结束当前 Explore Session：
1. 当前目标已经被证明、反驳或实质解决；
2. 当前可见的高价值路线基本耗尽，没有明确值得执行的下一步；
3. 多轮换路线、证明、反例搜索和计算仍没有有效推进，继续当前会话的边际价值明显很低；
4. 用户主动 Stop；
5. 触发硬安全预算或不可恢复故障。
预算只是保险丝，不是期望工作时长，不要为了填满预算重复无效工作。

正面证明受阻时始终注意反例、边界情形和等价改写。
若连续推进只产生更多 case split、辅助引理、参数细分或有限样本，
却没有让主问题更接近闭合，应主动复盘并考虑换表示或换路线。
有限计算只能算 Evidence，不能当作普遍证明。保留有效失败及明确障碍。
只有得到充分支持时才记录 RESULT / PROOF / COUNTEREXAMPLE，
否则准确记录 EVIDENCE / GAP / FAILED-ATTEMPT。
已解决子问题只在确实需要其机制时重读；依赖完整证明时按 ID 读取原文。
只保存可复用的公开研究状态，禁止输出或持久化 private chain-of-thought。

emit_research_episode 是本次 Explore Session 的最终交接输出，不能用来仅保存中间 RESULT。
最终交接应给出 completion_state：TARGET_RESOLVED、ROUTES_EXHAUSTED 或 LOW_MARGINAL_VALUE。
TARGET_RESOLVED 仅表示本轮公开报告认为主目标已解决，不授予 canonical 或验证权威。
若还有明确可执行的高价值动作，使用 CONTINUE 并保存 milestone；
不要一边报告路线耗尽一边列出应立即执行的动作。
工具可用 next_action 明确写出该动作；直接返回 Episode 时，在 handoff 的字段前使用
Session completion: <上述枚举>。没有可执行动作时，Next worthwhile directions 明确写“暂无”。
远期设想或当前无法执行的方向应明确注明限制，不等于当前可执行动作。
最终 Episode 的数学正文结束后，单独添加一套 operational 标题和公开 handoff：
# Research operations
## CURRENT RESEARCH HANDOFF
Target: <所选目标 ID>
Session completion: <上述枚举>
### What changed this session
### Resolved / no longer needs work
### Active obstacles
### Active routes worth continuing
### Routes not worth repeating
### Boundary / counterexample status
### Next worthwhile directions
各字段简短记录公开发现、路线名/ID、原因和下一步；未知内容如实说明。
handoff 是研究规划，不是新数学对象；不要在其中放 numbered RESULT/PROOF/GAP 或数学关系声明。
只有明确 Human Review / Accept 才能将数学输出提升到 canonical Problem Record。
"""

REFLECTION_REMINDER = """继续推进前，在同一个活跃研究会话中快速检查当前状态：
- 当前路线是否真的让主问题更接近闭合？
- 是否只是在累积 case split、辅助引理或有限样本？
- 当前最核心的障碍是什么？
- 是否值得改变表示或换路线？
- 正面证明持续受阻时，是否应该针对性搜索反例或边界情形？
若仍有明确高价值下一步，保存阶段进展并继续研究，不要仅因已有 RESULT / PROOF 而结束。
真正有进展时可以继续当前路线；只有主目标已解决、路线耗尽或继续的边际价值很低时才最终交接。
只外显简短的公开 assessment 和 next action，禁止保存 private chain-of-thought。
"""

CONTINUE_AFTER_MILESTONE = """阶段进展已经保存，当前不能据此结束整个 Explore Session。
主目标仍未解决，且还有明确值得执行的下一步。请在同一个 native thread 继续研究。
优先执行已指出的动作；受阻时考虑反例、边界或等价改写。
仅在目标已解决、路线耗尽或继续会话边际价值很低时才最终交接；仍遵守原累计预算和权限。
"""


def continuation_instruction(steering: str = "") -> str:
    """Steering augments the common policy; the saved request stays unchanged."""
    return CONTINUATION_POLICY + (
        "\n用户可选 steering（补充默认政策）：\n" + steering.strip() if steering.strip() else ""
    )


@dataclass(frozen=True)
class FinalizationDecision:
    continue_research: bool
    reason: str
    next_action: str = ""


def assess_finalization(
    ot_dir: Path,
    target: ResearchTarget,
    markdown: str,
    *,
    completion_state: CompletionState | None = None,
    next_action: str | None = None,
) -> FinalizationDecision:
    """Only explicit operational intent triggers continuation; never judge a proof."""
    states = KnowledgeStateResolver(ot_dir).resolve(target.problem_id)
    target_state = states[target.node_id]
    if target_state.research_state == "REFUTED" or target.node_id in resolved_work_ids(states):
        return FinalizationDecision(False, "既有 Resolver 显示目标已解决或反驳。")
    if completion_state is None:
        reserved = re.search(r"^## CURRENT RESEARCH HANDOFF[ \t]*$", markdown, re.M)
        block = markdown[reserved.end() :].split("\n# ", 1)[0] if reserved else ""
        match = re.search(
            r"^Session completion:\s*"
            r"(CONTINUE|TARGET_RESOLVED|ROUTES_EXHAUSTED|LOW_MARGINAL_VALUE)\s*$",
            block,
            re.M,
        )
        if match:
            completion_state = match.group(1)  # type: ignore[assignment]
    if completion_state == "TARGET_RESOLVED":
        return FinalizationDecision(
            False, "本轮公开报告主目标已解决；仍需 Human Review，未提升数学权威。"
        )
    _, handoff = read_handoff(markdown)
    action = "\n".join([next_action or "", handoff.get(HANDOFF_FIELDS[6], "")])
    # Explicit absence/defer markers are operational declarations, not inferred math.
    absence = re.compile(
        r"^(?:(?:暂无|无)(?:明确|具体|可执行|高价值|值得)?(?:的)?(?:下一步|动作|方向)?[。.!]?|"
        r"没有(?:明确|具体|可执行|高价值|值得)?(?:的)?(?:下一步|动作|方向).*|"
        r"none\b.*|no (?:concrete |worthwhile |executable )?"
        r"(?:next |further )?(?:action|direction|step).*|"
        r"暂不可执行[:：].*|远期设想[:：].*|deferred[:：].*)$",
        re.I,
    )
    actions = []
    for line in action.splitlines():
        entry = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if entry and not absence.fullmatch(entry):
            actions.append(entry)
    worthwhile = "\n".join(actions)[:2400]
    if completion_state == "CONTINUE" or worthwhile:
        return FinalizationDecision(
            True, "主目标仍未解决，公开输出仍列有值得执行的下一步。", worthwhile
        )
    return FinalizationDecision(False, "没有明确可执行下一步；保留既有最终 Episode 兼容入口。")
