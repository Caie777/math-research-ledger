# External Research Episode contract

Supply UTF-8 Markdown up to 10 MiB. Preserve complete statements/proofs and explicit failures. Pass provenance separately to identify the external harness session or original source.

```markdown
---
target_claim_id: CLAIM-0001
thread_ids: [external-session-reference]
---

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
```

IDs above are placeholders. Use actual records from the Problem. Existing numbered RESULT/PROOF/EVIDENCE/COUNTEREXAMPLE/revision parsing is also retained. Each candidate preserves Episode identity, original section, source lines, full body, explicit fields and stable provisional identity. Unknown prose remains source material.

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
