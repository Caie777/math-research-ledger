import type { Proposal, ProposalRow, EpisodeSummary, ObjectKind, RecallFile } from './api'
import { normalizeLatexMarkdown } from './latexRendering'

export type Selection =
  | { type: 'episode'; id: string }
  | { type: 'candidate'; id: string }
  | { type: 'object'; kind: ObjectKind; id: string }
  | { type: 'memory'; artifactType: string; id: string }
  | { type: 'resource'; file: RecallFile; id: string }

export const OBJECT_KINDS: { kind: ObjectKind; label: string }[] = [
  { kind: 'claim', label: 'Claims' },
  { kind: 'proof', label: 'Proofs' },
  { kind: 'counterexample', label: 'Counterexamples' },
  { kind: 'gap', label: 'Gaps' },
  { kind: 'evidence', label: 'Evidence' },
  { kind: 'failed_attempt', label: 'Failed Attempts' },
]

export const CANDIDATE_LABELS: Record<string, string> = {
  claim: 'Result / Claim', proof: 'Proof', counterexample: 'Counterexample', refutation: 'Refutation',
  revision: 'Revision', evidence: 'Evidence', gap: 'Gap',
  failed_attempt: 'Failed Attempt', branch: 'Branch', relation: 'Relation',
}

export function currentEpisode(selection: Selection | null, episodes: EpisodeSummary[], rows: ProposalRow[]): string | null {
  if (selection?.type === 'episode') return selection.id
  if (selection?.type === 'candidate') {
    return rows.find(row => row.candidate.candidate_id === selection.id)?.candidate.episode_id || null
  }
  return episodes[0]?.episode.episode_id || null
}

export function candidateReviewStatus(row: ProposalRow): string {
  return row.review?.decision || 'pending'
}

export function candidateRecordStatus(row: ProposalRow): string {
  return row.review?.decision === 'accept' ? 'committed; verification separate' : 'not committed'
}

export function candidateTitle(candidate: Proposal): string {
  return candidate.local_id || candidate.title || candidate.candidate_id
}

/** Legacy display helper; normalization remains exclusive to rendering. */
export function displayMath(markdown: string): string {
  return normalizeLatexMarkdown(markdown)
}
