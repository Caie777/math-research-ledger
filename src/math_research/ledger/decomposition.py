"""Deterministic adapter for numbered, field-labelled research Episodes.

This module only reads Markdown. It makes no mathematical truth judgments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBERED = re.compile(
    r"^## (RESULT|PROOF|COUNTEREXAMPLE|REFUTATION|REVISION|EVIDENCE|GAP|"
    r"FAILED-ATTEMPT|BRANCH)-(\d+)\s*$",
    re.I,
)
_BOLD_FIELD = re.compile(r"^\*\*([^*]+)\*\*\s*(?::\s*(.*))?$")
_LOCAL_ID = re.compile(
    r"\b(?:RESULT|PROOF|COUNTEREXAMPLE|REFUTATION|REVISION|EVIDENCE|GAP|FAILED-ATTEMPT|BRANCH)-\d+\b",
    re.I,
)
_RELATION = re.compile(
    r"^\s*-\s*`?((?:RESULT|PROOF|COUNTEREXAMPLE|REFUTATION|REVISION|EVIDENCE|GAP|FAILED-ATTEMPT|BRANCH)-\d+)\s+"
    r"(proves|uses|depends_on|refutes|revises|supersedes|strengthens|weakens|"
    r"special_case_of|generalizes|related_to|invalidates|blocks|supports)\s+"
    r"((?:RESULT|PROOF|COUNTEREXAMPLE|REFUTATION|REVISION|EVIDENCE|GAP|"
    r"FAILED-ATTEMPT|BRANCH|CLAIM|APPROACH|APPR)-(?:\d+|P[0-9A-F]{16}))\b",
    re.I,
)
_FIELDS = frozenset(
    {
        "陈述",
        "状态",
        "目标",
        "证明摘要",
        "完整证明",
        "使用的已有结果",
        "known gap",
        "与已有对象的关系",
        "针对对象",
        "结论",
        "反例 / 证明",
        "旧对象",
        "变更类型",
        "原因",
        "修正后的内容",
        "类型",
        "结果",
        "逻辑强度",
        "阻碍对象",
        "缺失步骤",
        "当前状态",
        "失败原因",
        "研究路线",
        "statement",
        "status",
        "target",
        "summary",
        "proof",
        "uses",
        "evidence",
        "revision",
        "reason",
        "approach",
        "gap",
        "full proof",
    }
)
COUNTEREXAMPLE_FIELDS = frozenset(
    {
        "构造 / 反例",
        "构造",
        "反例",
        "construction",
        "counterexample",
        "验证",
        "verification",
        "作用范围",
        "scope",
    }
)
EVIDENCE_FIELDS = frozenset(
    {
        "验证范围",
        "范围",
        "verification scope",
        "scope",
        "关键算例",
        "代表性算例",
        "key example",
        "key examples",
        "representative example",
        "representative cases",
        "type",
        "result",
        "logical strength",
    }
)


@dataclass(frozen=True)
class NumberedSection:
    local_id: str
    kind: str
    heading: str
    raw_markdown: str
    fields: dict[str, str]
    start_line: int
    end_line: int


@dataclass(frozen=True)
class LocalRelation:
    source_id: str
    relation: str
    target_id: str
    raw_markdown: str
    line: int


def local_ids(text: str) -> list[str]:
    return list(
        dict.fromkeys(
            m.group().upper() for m in _LOCAL_ID.finditer("\n".join(mathematical_lines(text)))
        )
    )


def mathematical_lines(content: str) -> list[str]:
    """Mask reserved planning blocks while preserving original source line numbers."""
    result = []
    planning = False
    for line in content.splitlines():
        if line.strip().upper() == "## CURRENT RESEARCH HANDOFF":
            planning = True
        elif line.startswith("# "):
            planning = False
        result.append("" if planning else line)
    return result


def parse_numbered_episode(content: str) -> tuple[list[NumberedSection], list[LocalRelation]]:
    """Split H2 objects exactly, retaining source text and one-based line spans."""
    lines = content.splitlines()
    math_lines = mathematical_lines(content)
    starts = [(i, match) for i, line in enumerate(math_lines) if (match := _NUMBERED.match(line))]
    sections: list[NumberedSection] = []
    for position, (start, match) in enumerate(starts):
        later_h2 = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        end = next(
            (
                i
                for i in range(start + 1, later_h2)
                if lines[i].startswith("# ")
                or lines[i].strip().upper() == "## CURRENT RESEARCH HANDOFF"
            ),
            later_h2,
        )
        field_starts = [
            (i, field)
            for i in range(start + 1, end)
            if (field := _BOLD_FIELD.match(lines[i]))
            and field.group(1).strip().casefold()
            in (
                _FIELDS | COUNTEREXAMPLE_FIELDS
                if match.group(1).upper() == "COUNTEREXAMPLE"
                else _FIELDS | EVIDENCE_FIELDS
                if match.group(1).upper() == "EVIDENCE"
                else _FIELDS
            )
            and (i == start + 1 or not lines[i - 1].strip())
        ]
        fields: dict[str, str] = {}
        for index, (line_no, field) in enumerate(field_starts):
            field_end = field_starts[index + 1][0] if index + 1 < len(field_starts) else end
            value = "\n".join(lines[line_no + 1 : field_end]).strip()
            fields[field.group(1).strip().casefold()] = (
                f"{field.group(2)}\n{value}" if field.group(2) else value
            ).strip()
        sections.append(
            NumberedSection(
                local_id=f"{match.group(1).upper()}-{match.group(2)}",
                kind=match.group(1).upper(),
                heading=lines[start],
                raw_markdown="\n".join(lines[start:end]).rstrip(),
                fields=fields,
                start_line=start + 1,
                end_line=end,
            )
        )
    relations = [
        LocalRelation(
            source_id=match.group(1).upper(),
            relation=match.group(2).upper(),
            target_id=match.group(3).upper(),
            raw_markdown=line,
            line=i + 1,
        )
        for i, line in enumerate(math_lines)
        if (match := _RELATION.match(line))
    ]
    return sections, relations


def has_numbered_headings(content: str) -> bool:
    return any(_NUMBERED.match(line) for line in mathematical_lines(content))
