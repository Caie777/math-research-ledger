# Research Episode Prompt V4

保留本轮研究的完整数学正文。所有对象和关系只生成 pending candidates；
source-reported / validator-qualified / Human Accepted / verifier-passed 分开记录。
不要在输出中声称系统已经接受对象或修改正式 Problem Record。

对象使用二级编号标题；字段名独占一行，字段之间留空行。
RESULT / PROOF / GAP / EVIDENCE / REVISION / FAILED-ATTEMPT / BRANCH 格式继续保留。
局部编号只在本 Episode 内有效；正式引用使用已有 CLAIM / PROOF / APPROACH IDs。
有限范围的成功检查应输出 EVIDENCE，不能替代全称证明。

# 本轮结构化输出 metadata

每轮最终或部分 Episode 顶部使用 YAML front matter，保留以下八个字段（无内容为 []）。
六个对象列表只列出下文实际二级编号对象的局部 ID，按正文顺序排列；
完整数学内容仍保留在对应正文中，不重复生成或摘要替代。复用本轮已有上下文，
不为 metadata 再调用模型，也不要求下游模型重新拆解同一材料。

```yaml
---
new_claims: [RESULT-1]
new_gaps: []
proof_attempts: [PROOF-1]
evidence: []
counterexamples: []
failed_attempts: []
explicit_dependencies:
  - {source_id: PROOF-1, target_id: CLAIM-0001}
relation_hints:
  - {source_id: PROOF-1, relation: TARGETS, target_id: RESULT-1}
  - {source_id: PROOF-1, relation: USES, target_id: CLAIM-0001}
---
```

占位对象必须替换为本轮实际对象。explicit_dependencies 只记录明确使用的对象。
relation_hints 是 Agent-local relation candidates，只保留本轮明确知道的关系，
例如 Proof 的 TARGETS / USES 或 Counterexample 的 REFUTES / INVALIDATES；
不要根据相似性猜测关系。TARGETS 只描述目标，不声明 PROVES。
deterministic parser 直接消费这些字段，所有对象仍是 pending Proposals；
关系仍经过 deterministic provenance → existing Relation Scout → 必要时强判断 / Relation Review。
metadata 不能自动创建 active Logical Relation，不能替代 Human Review 或数学验证。

# 计算 Evidence 与关键算例

ordinary samples -> aggregate Evidence：普通批量样本只记录范围、数量与聚合结果。
important representative case -> key example inside Evidence：边界、极值、最小例外、
首次结构或解释机制的 witness 可保留少量关键算例。
universal statement violated -> Counterexample：实际反驳全称命题的实例必须使用
COUNTEREXAMPLE，不能留作普通 Evidence key example。
debug samples -> do not record：调试样本不记录。
关键算例没有独立 ID / authority / review；随所属 Evidence 一起接受。
默认不要求保存 Python 代码；若已提供 script path、output artifact 或 log，
沿用现有 path / source_artifacts 能力。

## EVIDENCE-1

**类型**

finite_computation / symbolic_computation / exhaustive_search / numerical_evidence

**针对对象**

target: CLAIM-xxxx（或本 Episode 中已有 RESULT 编号）

**验证范围**

实际参数范围、搜索空间与检查数量。

**结果**

聚合数学结果；不要逐项列出普通样本。

**关键算例**

可选；若无可省略。只保留少量具有独立未来研究价值的实例。
每项给出足够重建的参数/对象、关键性质及为什么值得保留。
多项使用 `### Key example 1` / `### Key example 2` 标题，或顶层列表；
实例内部的参数列表使用缩进。独立意义可写为 `Significance: ...`。

**逻辑强度**

明确能推出什么、不能推出什么；有限检查不是全称证明。
英文标签可用 Type / Target / Verification scope / Result / Key examples / Logical strength。

# 新增反例

## COUNTEREXAMPLE-1

**针对对象**

target: CLAIM-xxxx

**构造 / 反例**

给出具体 witness、参数、完整构造；不要只写摘要。

**验证**

保留完整推导，解释这个对象为何违反精确目标版本。

**作用范围**

精确限定被攻击的版本与条件，例如 refutes the statement without r >= 8；
does_not_refute CLAIM-0016。不要省略仍然有效的加强版或特殊情形。

如果只发现 Proof / Approach 的步骤失效，target 必须是该对象；
使用 INVALIDATES，不能推出底层 Claim 为假。
英文标签可使用 **target** / **construction** / **verification** / **scope**。

# 证否

## REFUTATION-1

**针对对象**

target: CLAIM-xxxx

**反例 / 证明**

一般证否的完整论证：假设目标成立，逐步推出矛盾。
此对象经 Human Accept 映射到 ProofAttempt，结论角色为 REFUTES。
有具体 witness 时使用 COUNTEREXAMPLE；不要混入有限成功检查。

# 本轮对象关系

- COUNTEREXAMPLE-1 refutes CLAIM-xxxx
- COUNTEREXAMPLE-2 invalidates PROOF-xxxx
- REFUTATION-1 refutes CLAIM-xxxx

用实际存在的对象替换占位符；关系接受与对象接受分别进行。
REFUTES 攻击 Statement 本身；INVALIDATES 攻击 Proof / Approach。
