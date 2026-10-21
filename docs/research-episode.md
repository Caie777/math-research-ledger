# External Research Episode contract

Supply UTF-8 Markdown up to 10 MiB. Preserve complete statements/proofs and explicit failures. Pass provenance separately to identify the external harness session or original source.

Consolidate meaningful checkpoints; keep ongoing reasoning light. Use two top-level
sections: **Confirmed Research Increment** and **Next Research Directions**. The first
records what actually changed this round, including failures and remaining gaps; it
does not mean mathematically verified or human accepted. The second is advisory.
`research_save_note` is for a few important isolated captures, never every chat turn.

```markdown
---
target_claim_id: CLAIM-0001
thread_ids: [external-session-reference]
---

# Confirmed Research Increment

## Claim: descriptive title

Complete quantified statement, domain and assumptions.

## Proof: descriptive title
Target: CLAIM-0001
Uses: CLAIM-0002

Complete proof body; preserve unresolved steps explicitly.

## Gap: unresolved step
Target: CLAIM-0001

Precise missing argument.

## Failed Attempt: route to avoid
Target: CLAIM-0001

Attempted method, failure reason, scope and reusable obstruction.

# Next Research Directions

Advisory only: try another route after inspecting this checkpoint's gap.
```

IDs above are placeholders. Use actual records from the Problem. Existing numbered RESULT/PROOF/EVIDENCE/COUNTEREXAMPLE/revision parsing is also retained. Each candidate preserves Episode identity, original section, source lines, full body, explicit fields and stable provisional identity. Unknown prose remains source material.

## Machine-readable increment

Ingestion retains exact raw Markdown and persists `state_delta[]` on ResearchEpisode:
action, reference, complete statement, source_sha256, start_line and end_line. Supported
actions are Added, Revised, Invalidated, Refuted and Still Open. Recognized objects
derive Added; Gaps derive Still Open; explicit revision/refutation/relation proposals
derive their corresponding reported actions. References are Episode-local or stable
provisional IDs; source spans and SHA256 bind them to the exact original bytes.

For an explicit assertion about an existing object, front matter may contain:

```yaml
state_delta:
  - action: Revised
    reference: PROBLEM-0001:claim:CLAIM-0001
    statement: Source-reported correction and its scope; requires human review.
```

The service supplies digest/spans. Extra authority fields are rejected. These are source
assertions, not a second truth system: no target is automatically revised, invalidated,
refuted, checked or accepted. Authority services still decide current use. Typed data
is available from research_get_object with explicit truncation/offset metadata; complete
raw bodies remain pageable.

Next Directions are separately stored and advisory even when their prose contains
Claim/RESULT headings, dependency wording or proposed results. They cannot generate
research candidates or dependencies. Legacy Episodes lacking these fields load without
rewriting history or changing old versions. Use H1 wrapper sections and existing H2
object headings, as in the example.

Ingestion serializes metadata with a durable rollback journal. Readers fail closed on
interrupted publication; trusted-human `ingest recover` restores both indexes. Raw bytes
are retained even after failed publication. No automatic chat/tool-call hook or Git
operation is involved.

Preview is read-only. Pass its SHA-256 as expected_sha256 to refuse changed bytes. Duplicate bytes reuse archive identity/proposals. Parsing ignores a UTF-8 BOM while archive bytes stay exact.

External output remains provisional regardless of source-reported status. ingest review is a human canonicalization path, blocked in automated scope. Canonicalization, soft review, hard check, correspondence and acceptance remain independent.

## Input version pins

An external harness can return the packet versions it actually used in front matter:

```yaml
input_versions:
  - ref: {problem_id: PROBLEM-0001, kind: definition, object_id: DEF-0001}
    version: <64-character version from the input packet>
```

Only explicitly declared Uses/proof-target links consume these pins. Context relevance does not become a logical dependency. Version pins survive human canonicalization, so work produced under old definitions remains visibly stale. Do not replace an old input version with the current one merely to clear a warning.

## Independent review output

The reviewer consumes ReviewPacket. Return ReviewReport fields id, target (copy the packet target ref/version), reviewer, verdict, findings, and packet_version (copy packet.source_version). The authority field must remain ADVISORY. Use review record to store the report; no model is invoked. Human candidate edits can be supplied as a JSON object via ingest review --edits <file>.

New PDF sources are pinned as original artifacts; existing extracted text is reused when available. Text/Markdown bodies are directly readable by scoped object tools. PDF extraction/OCR is left to the external harness when no extracted text exists.
