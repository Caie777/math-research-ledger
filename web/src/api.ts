export type ObjectKind = 'claim' | 'proof' | 'counterexample' | 'gap' | 'evidence' | 'failed_attempt'
export type Decision = 'accept' | 'reject' | 'defer'

export interface AgentSettings {
  target: { kind: 'claim'; problem_id: string; node_id: string }
  task: string; provider: string; model: string | null; effort: string | null
  tool_policy: 'research_standard'; context_tokens: number; include_provisional: boolean
  checkpoint_every_effective_steps?: number
  budget: { max_agent_steps: number; max_model_calls: number; max_context_tokens: number; max_tool_calls: number; max_web_calls: number; max_python_calls: number; max_wall_time: number }
}

export interface ResearchDefaults {
  research: Omit<AgentSettings, 'target'> & { thread_id?: string | null }
  scout: RelationModelSettings
  adjudicator: RelationModelSettings
  recall: RelationModelSettings
  critique?: CritiqueSettings
  coordinator?: RelationModelSettings | null
  adjudication_tokens: number
  reflection_every_research_decisions: number
}
export interface ProductRole { provider: string; model: string; reasoning_effort: string | null; enabled: boolean }
export type ModelRoles = Record<'coordinator' | 'research' | 'cheap_semantic', ProductRole>
export interface ProductModelSettings {
  roles: ModelRoles; status: Record<keyof ModelRoles, 'configured' | 'missing'>
  credentials: Record<string, 'configured' | 'missing' | 'not_required'>; providers: string[]
}
export type ResearchIntentName = 'CONTINUE_RESEARCH' | 'IMPORT_DECOMPOSE_EPISODE' | 'HUMAN_REVIEW'
  | 'CRITIQUE_RESEARCH_RESULT'
  | 'DIGEST_SOURCE' | 'OPEN_SOURCE_DIGEST' | 'REVIEW_SOURCE_PROPOSAL'
  | 'CREATE_PROBLEM' | 'ADD_SOURCE' | 'SYSTEM_HEALTH' | 'EXPORT_WORKSPACE_SNAPSHOT' | 'VERIFY_SNAPSHOT' | 'EXPORT_RESEARCH_HANDOFF'
  | 'FIND_RELATED_RESEARCH' | 'LOGICAL_RELATIONS' | 'RESEARCH_STATUS' | 'OPEN_RESOURCE'
  | 'STOP_RESEARCH' | 'RESUME_RESEARCH' | 'UNSUPPORTED'
export interface ResearchIntent { intent: ResearchIntentName; target_id: string | null; query: string }

export interface CritiqueSettings {
  provider: 'codex' | 'openai' | 'anthropic' | 'ollama' | 'mistral'
  model: string; reasoning_effort: 'low' | 'medium' | 'high' | 'xhigh' | 'max' | null
}
export interface CritiqueContextItem {
  record_id: string; record_type: string; authority: string; status: string
  reason_included: string; content: string; sha256: string
}
export interface CritiqueBundle {
  problem_id: string; target: CritiqueContextItem; problem: CritiqueContextItem
  context: CritiqueContextItem[]; relations: CritiqueContextItem[]; limitations: string[]
  continuation_target_id: string | null; computation_available: false
}
export interface CritiqueIssue {
  issue_id: string; category: string; severity: 'CRITICAL' | 'MAJOR' | 'MINOR' | 'NOTE'
  location: string; explanation: string; mathematical_consequence: string; suggested_check: string
}
export interface CritiqueReport {
  critique_id: string; target_id: string; target_type: 'claim' | 'proof' | 'counterexample' | 'evidence'
  created_at: string; provider: string; model: string; reasoning_effort: string | null
  context_manifest: CritiqueContextItem[]; verdict: 'NO_CLEAR_ISSUE' | 'ISSUE_FOUND' | 'INCONCLUSIVE'
  summary: string; issues: CritiqueIssue[]; suggested_checks: string[]; limitations: string[]
  bundle_sha256: string; session_id: string; authority: 'ADVISORY'
}
export interface CritiqueRun {
  critique_id: string; problem_id: string; target_id: string; target_type: CritiqueReport['target_type']
  created_at: string; settings: CritiqueSettings; bundle_sha256: string; session_id: string
  continuation_target_id: string | null; status: 'RUNNING' | 'COMPLETED' | 'FAILED'
  report: CritiqueReport | null; error: string | null; authority: 'ADVISORY'
}
export interface CritiquePreflight { bundle: CritiqueBundle; bundle_sha256: string; settings: CritiqueSettings }
export interface DigestSettings extends CritiqueSettings { max_chunks: number }
export interface SourceLocator { page?: number | null; page_end?: number | null; line_start?: number | null; line_end?: number | null; heading?: string | null }
export interface SourceProposal {
  proposal_id: string; proposal_type: 'claim' | 'evidence' | 'gap' | 'counterexample' | 'failed_attempt' | 'relation'
  title: string; statement: string; source_id: string; source_filename: string; digest_id: string; candidate_id: string
  locator: SourceLocator | null; supporting_span: string; confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  relation_to_problem: 'DIRECT' | 'SUPPORTING' | 'BACKGROUND' | 'POSSIBLE'
  citation_kind: 'SOURCE_PRIMARY' | 'SOURCE_CITES_EXTERNAL'; target_id: string | null; notes: string
  relation: string | null; source_candidate_id: string | null
  provenance_status: 'VALID' | 'PROVENANCE_INCOMPLETE' | 'INVALID'; possible_duplicate_ids: string[]
  additional_support: { locator: SourceLocator | null; supporting_span: string }[]
  review_decision: string | null; mapped_id: string | null
}
export interface SourceDigest {
  digest_id: string; source_id: string; source_filename: string; source_sha256: string; problem_id: string
  created_at: string; model: string; reasoning_effort: string | null; summary: string
  notation: string[]; definitions: string[]; results: string[]; methods: string[]; assumptions: string[]; limitations: string[]
  proposals: SourceProposal[]; coverage_complete: boolean; processed_ranges: SourceLocator[]; omitted_ranges: SourceLocator[]
  validation_warnings: string[]; authority: 'ADVISORY'
}
export interface DigestRun {
  digest_id: string; source_id: string; problem_id: string; source_sha256: string; created_at: string
  settings: DigestSettings; status: 'RUNNING' | 'COMPLETED' | 'PARTIAL' | 'FAILED'; digest: SourceDigest | null
  error: string | null; source_changed: boolean; authority: 'ADVISORY'
}
export interface DigestPreflight {
  context: { problem_id: string; source_filename: string; source_sha256: string; format: string; total_units: number; unit: string; chunks: { chunk_id: string; text: string; page: number | null; line_start: number | null; line_end: number | null }[]; limitations: string[] }
  context_sha256: string; settings: DigestSettings
}
export interface StagedSourceProposal { candidate_id: string; episode_id: string; proposal_id: string; digest_id: string }
export interface ProblemInput { title: string; statement: string; target_type: 'Claim' | 'Gap'; description: string }
export interface ProblemPreview extends ProblemInput { source_count: number; sources: { filename: string; sha256: string; size: number }[]; digest: string }
export interface CreatedProblem { problem_id: string; target_id: string; target_type: 'Claim' | 'Gap'; status: string; source_ids: string[] }
export interface HealthReport { protocol: string; status: string; checks: { name: string; status: string; detail: string }[] }
export interface EpisodePreflight extends Preview {
  target_id: string | null; content_sha256: string; parse_summary: Record<string, number>; candidate_count: number
}
export interface AgentEvent { event: string; at?: string; episode_id?: string; stop_reason?: string; [key: string]: unknown }
export interface AgentRun {
  started_at?: string; ended_at?: string | null
  run_id: string; request: AgentSettings; status: 'running' | 'finished'; stop_reason: string | null
  steps: number; model_calls: number; tool_calls: number; web_calls: number; python_calls: number
  current_action: string; usage: Record<string, unknown>; artifacts: string[]; checkpoint_path: string | null
  episode_id: string | null; candidate_ids: string[]; error: string | null; availability: Record<string, string>
  executor_attached?: boolean | null
  effective_steps?: number; latest_checkpoint?: string | null; last_checkpoint_step?: number
  uncheckpointed_public_events?: number; resume_available?: boolean; resume_unavailable_reason?: string | null
  attempt?: number
  research_decisions?: number; last_reflection_decision?: number
}

// Durable operational projection; mathematical authority stays with Episode / Review.
export interface ResearchRunProgress {
  schema_version: 1; run_id: string; problem_id: string; target_id: string
  status: 'running' | 'finished'
  current_phase: 'initializing' | 'loading_context' | 'researching' | 'using_tools' | 'checkpointing' | 'finalizing' | 'stopping' | 'terminal'
  started_at: string; updated_at: string; last_activity_at: string
  last_checkpoint_at: string | null; finished_at: string | null
  step_count: number; model_call_count: number; tool_call_count: number
  checkpoint_count: number; public_event_count: number
  budget: AgentSettings['budget']; stop_reason: string | null; error_type: string | null
  latest_public_progress: { id: number; kind: string; summary: string } | null
  stop_requested: boolean; source: 'snapshot' | 'reconstructed'; snapshot_error: boolean
}

export type CoordinatorTool = 'list_problems' | 'get_problem_state' | 'get_recent_research' | 'get_unresolved_targets'
  | 'get_research_portfolio' | 'search_research_memory' | 'get_run_progress' | 'list_research_runs'
  | 'start_research' | 'stop_research' | 'resume_research' | 'open_episode_import'
export interface CoordinatorAction { name: CoordinatorTool; problem_ref?: string | null; target_ref?: string | null; run_ref?: string | null; query?: string; active_only?: boolean }
export interface CoordinatorRefs { problem_id: string | null; target_id: string | null; run_id: string | null }
export interface CoordinatorRequest {
  message?: string; action?: CoordinatorAction; selected_problem_id?: string | null
  selected_object_id?: string | null; active_run_id?: string | null
}
export interface CoordinatorResponse {
  kind: 'QUERY_RESULT' | 'ACTION_RESULT' | 'MODEL_RESPONSE' | 'CONFIG_REQUIRED' | 'AMBIGUOUS' | 'ERROR'
  message: string; resolved_refs: CoordinatorRefs; actions_executed: { name: CoordinatorTool; refs: CoordinatorRefs; reused: boolean }[]
  run_id: string | null; structured_payload: { open_task?: 'IMPORT_DECOMPOSE_EPISODE'; progress?: ResearchRunProgress; runs?: ResearchRunProgress[]; portfolio?: Record<string, unknown>[]; targets?: { problem_id: string; target_id: string; title: string }[]; memory?: { id: string; title: string; authority: string }[]; query?: string }
  model_used: boolean; model_role: 'coordinator' | 'research' | null; error_code: string | null
  choices: CoordinatorRefs[]; pending_action?: CoordinatorAction | null
}

export interface Problem {
  id: string
  title: string
  primary_claim_id: string | null
}

export interface ResearchMapNode {
  id: string
  type: 'problem' | ObjectKind
  title: string
  status: string
  authority: string
  is_primary: boolean
  group: 'current' | 'failed_routes' | 'historical'
  review: string
  verification: string
  warnings: string[]
  episode_id: string | null
  research_target_id: string | null
  critique_count?: number
}
export interface ResearchMapEdge {
  source: string; target: string; relation_type: string; authority: string; witness_id: string | null
}
export interface ResearchMap {
  problem_id: string; primary_target_id: string | null
  nodes: ResearchMapNode[]; edges: ResearchMapEdge[]
  groups: { id: string; title: string; node_ids: string[] }[]
  warnings: string[]
}

export interface ResearchObject {
  state?: KnowledgeState | null
  id: string
  kind: ObjectKind
  title: string
  status: string
  body: string
  metadata: Record<string, unknown>
  provenance: string[]
  source_reported_status: string | null
  human_review: string | null
  source_episode_id: string | null
  summary: string | null
}

export interface EpisodeMeta {
  episode_id: string
  problem_id: string
  primary_problem_id?: string | null
  related_problem_ids?: string[]
  thread_ids?: string[]
  archive_path: string
  imported_at: string
  source_filename: string
  source_language: string | null
  content_sha256: string
  provenance: string | null
}

export interface EpisodeSummary {
  episode: EpisodeMeta
  candidate_count: number
  accepted: number
  rejected: number
  deferred: number
  pending: number
}

export interface EpisodeDetail {
  episode: EpisodeMeta
  raw_markdown: string
  parse_summary: Record<string, number>
  candidate_count: number
}

export interface Proposal {
  candidate_id: string
  episode_id: string
  problem_id: string
  kind: string
  title: string
  body: string
  summary: string
  target_id: string | null
  relation: string | null
  relation_wording: string
  local_id: string | null
  source_local_id: string | null
  source_reported_status: string
  source_section: string
  start_line: number
  end_line: number
  raw_markdown: string
  source_fields: Record<string, string>
  uses: string[]
  semantic_validation_status?: string | null
  semantic_confidence?: number | null
}

export interface Review {
  candidate_id: string
  decision: Decision
  mapped_id: string | null
  decided_at: string
  relation: string | null
  source_id: string | null
  target_id: string | null
}

export interface ProposalRow {
  candidate: Proposal
  review: Review | null
  state?: KnowledgeState | null
}

export interface KnowledgeState {
  kind?: string
  usable_premise?: boolean
  authority: string
  review: string
  verification: string
  research_state: string
  warnings: string[]
  dependencies: string[]
  resolution_ids: string[]
  replacement_ids: string[]
}
export type QueryPurpose = 'CONTINUE_RESEARCH' | 'RECOVER_PROOF' | 'TRACE_HISTORY' | 'FIND_FAILURES'
export interface ResearchContextBundle {
  target: { problem_id: string; node_id: string; kind: string }
  purpose: QueryPurpose
  thread_id: string | null
  source_version: string
  markdown: string
  items: { object_id: string; section: string; state: KnowledgeState; full_text: boolean }[]
  excluded: { object_id: string; reason: string }[]
  warnings: string[]
  token_budget: number
  token_estimate: number
  tokens_per_section: Record<string, number>
  complete: boolean
}

export type UploadResult = Omit<EpisodeDetail, 'raw_markdown'> & { duplicate: boolean; summary?: Record<string, string | number | null> }

export interface Preview {
  filename: string
  size_bytes: number
  front_matter: Record<string, unknown>
  body: string
}

export interface SearchHit {
  artifact_id: string
  artifact_type: string
  title: string
  text: string
  problem_id: string
}

export interface MemoryHit {
  object_id: string
  object_type: string
  title: string
  excerpt: string
  record_status?: string | null
  caveats?: string[]
  retrieval_score: number
  retrieval_reasons: string[]
  hard_relation: string | null
  relevance_score: number | null
  category: string | null
  short_reason: string
  validation_status: string
  navigation_kind: string
}

export interface RelatedResearch {
  problem_id: string
  target_id: string
  query: string
  hits: MemoryHit[]
  expansion_suggestions: { object_id: string; short_reason: string; validation_status: string; hit: MemoryHit | null }[]
  warnings: string[]
  provider: string | null
  actual_models: string[]
  elapsed_seconds: number
  usage: Record<string, number> | null
}

interface ModelJob<T> {
  job_id: string
  status: 'running' | 'completed' | 'failed'
  result: T | null
  error: string | null
}

export type MemoryJob = ModelJob<RelatedResearch>

export interface RelationPolicy { mode: 'HUMAN_ONLY' | 'MODEL_OR_HUMAN'; require_human_for_state_changing: boolean }
export interface RelationDecision {
  decision_id: string; proposal_id: string; decision: string; confirmed_by: 'human' | 'model'
  rationale: string; model: string | null; reasoning_effort: string | null; created_at: string
}
export interface RelationPoolItem {
  proposal_id: string; source_candidate_id: string; proposed_relation: string; target_id: string
  episode_id: string; origin: string; scout_model: string | null; confidence: number; rationale: string
  current_status: string; confirmation: string | null; active: boolean; inactive_reason: string | null
  source_id: string | null; effective_relation: string | null; effective_target_id: string | null
  latest_decision: RelationDecision | null; scout_run_ids: string[]
}
export interface RelationRun {
  run_id: string; status: string; usage: Record<string, number> | null; elapsed_seconds: number
  [key: string]: unknown
}
export type RelationJob = ModelJob<RelationRun | RelationRun[]>
export interface RelationModelSettings { provider: string; model: string; reasoning_effort: string | null }

export interface RecallFile {
  artifact_id: string
  kind: string
  path: string | null
  title: string
  why_relevant: string[]
  state: KnowledgeState
  authority: string
  relation_to_target: string[]
  problem_id: string | null
  problem_scope: string[]
  provenance: string[]
  conclusion_relation: 'PROVES' | 'REFUTES' | null
  warnings: string[]
}

export interface FileSearchResult {
  problem_id: string
  target_id: string | null
  query: string
  cross_problem: boolean
  files: RecallFile[]
  warnings: string[]
}

export interface HistoryCheckResult {
  classification: 'NEW' | 'PARTIAL_OVERLAP' | 'POSSIBLE_OVERLAP' | 'ALREADY_PROVED' | 'ALREADY_REFUTED' | 'KNOWN_FAILED_ROUTE' | 'CURRENT_OPEN_WORK'
  basis: 'HARD_STATE' | 'SOFT_OVERLAP' | 'NO_MATCH'
  target_id: string | null
  query: string
  canonical_matches: RecallFile[]
  open_matches: RecallFile[]
  failed_routes: RecallFile[]
  counterexamples: RecallFile[]
  proofs: RecallFile[]
  source_files: RecallFile[]
  soft_overlaps: RecallFile[]
  warnings: string[]
  recommended_context_ids: string[]
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const stringArray = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string')
const hasStrings = (value: Record<string, unknown>, keys: string[]) => keys.every(key => typeof value[key] === 'string')
const nullableString = (value: unknown) => value === null || typeof value === 'string'
const arrayOf = (value: unknown, valid: (item: unknown) => boolean) => Array.isArray(value) && value.every(valid)
const modelSettings = (value: unknown) => isObject(value) && hasStrings(value, ['model', 'provider']) && nullableString(value.reasoning_effort)
const contextItem = (value: unknown) => isObject(value) && hasStrings(value, ['record_id', 'record_type', 'authority', 'status', 'reason_included', 'sha256', 'content'])
const sourceLocator = (value: unknown) => isObject(value) && ['page', 'page_end', 'line_start', 'line_end'].every(key => value[key] == null || typeof value[key] === 'number') && (value.heading == null || typeof value.heading === 'string')

// Check response fields consumed by these workflows before they enter the UI cache.
// TypeScript assertions alone cannot protect rendering from malformed HTTP 200 responses.
function researchMapResponse(value: unknown): boolean {
  return isObject(value) && typeof value.problem_id === 'string' && nullableString(value.primary_target_id) && stringArray(value.warnings)
    && arrayOf(value.nodes, node => isObject(node) && hasStrings(node, ['id', 'title', 'type', 'status', 'authority', 'review', 'verification', 'group']) && stringArray(node.warnings)
      && ['problem', 'claim', 'gap', 'proof', 'evidence', 'counterexample', 'failed_attempt'].includes(String(node.type)) && typeof node.is_primary === 'boolean' && nullableString(node.research_target_id) && nullableString(node.episode_id))
    && arrayOf(value.edges, edge => isObject(edge) && hasStrings(edge, ['source', 'target', 'relation_type', 'authority'])) && Array.isArray(value.groups)
}
function critiquePreflightResponse(value: unknown): boolean {
  return isObject(value) && typeof value.bundle_sha256 === 'string' && modelSettings(value.settings) && isObject(value.bundle)
    && contextItem(value.bundle.target) && contextItem(value.bundle.problem) && arrayOf(value.bundle.context, contextItem) && arrayOf(value.bundle.relations, contextItem) && stringArray(value.bundle.limitations)
}
function critiqueRunResponse(value: unknown): boolean {
  if (!isObject(value) || !hasStrings(value, ['critique_id', 'problem_id', 'target_id', 'target_type']) || !['RUNNING', 'COMPLETED', 'FAILED'].includes(String(value.status)) || value.authority !== 'ADVISORY' || !nullableString(value.error) || !nullableString(value.continuation_target_id)) return false
  if (value.report === null) return value.status !== 'COMPLETED'
  const report = value.report
  return isObject(report) && hasStrings(report, ['critique_id', 'target_id', 'target_type', 'summary', 'provider', 'model', 'created_at']) && ['NO_CLEAR_ISSUE', 'ISSUE_FOUND', 'INCONCLUSIVE'].includes(String(report.verdict))
    && arrayOf(report.context_manifest, contextItem) && stringArray(report.limitations) && stringArray(report.suggested_checks)
    && arrayOf(report.issues, issue => isObject(issue) && hasStrings(issue, ['issue_id', 'category', 'location', 'explanation', 'mathematical_consequence', 'suggested_check']) && ['CRITICAL', 'MAJOR', 'MINOR', 'NOTE'].includes(String(issue.severity)))
}
function digestPreflightResponse(value: unknown): boolean {
  return isObject(value) && typeof value.context_sha256 === 'string' && modelSettings(value.settings) && isObject(value.settings) && typeof value.settings.max_chunks === 'number' && isObject(value.context)
    && hasStrings(value.context, ['problem_id', 'source_filename', 'source_sha256', 'format', 'unit']) && typeof value.context.total_units === 'number' && Array.isArray(value.context.chunks) && stringArray(value.context.limitations)
}
function digestRunResponse(value: unknown): boolean {
  if (!isObject(value) || !hasStrings(value, ['digest_id', 'problem_id', 'source_id', 'source_sha256']) || !['RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED'].includes(String(value.status)) || value.authority !== 'ADVISORY' || typeof value.source_changed !== 'boolean' || !nullableString(value.error)) return false
  if (value.digest === null) return ['RUNNING', 'FAILED'].includes(String(value.status))
  const digest = value.digest
  return isObject(digest) && hasStrings(digest, ['digest_id', 'source_id', 'problem_id', 'source_filename', 'source_sha256', 'model', 'summary', 'created_at']) && digest.authority === 'ADVISORY'
    && ['notation', 'definitions', 'results', 'methods', 'assumptions', 'limitations', 'validation_warnings'].every(key => stringArray(digest[key]))
    && typeof digest.coverage_complete === 'boolean' && arrayOf(digest.processed_ranges, sourceLocator) && arrayOf(digest.omitted_ranges, sourceLocator)
    && arrayOf(digest.proposals, proposal => isObject(proposal) && hasStrings(proposal, ['proposal_id', 'candidate_id', 'digest_id', 'source_id', 'source_filename', 'title', 'statement', 'supporting_span', 'notes'])
      && ['claim', 'evidence', 'gap', 'counterexample', 'failed_attempt', 'relation'].includes(String(proposal.proposal_type)) && ['HIGH', 'MEDIUM', 'LOW'].includes(String(proposal.confidence)) && ['VALID', 'PROVENANCE_INCOMPLETE', 'INVALID'].includes(String(proposal.provenance_status))
      && ['DIRECT', 'SUPPORTING', 'BACKGROUND', 'POSSIBLE'].includes(String(proposal.relation_to_problem)) && ['SOURCE_PRIMARY', 'SOURCE_CITES_EXTERNAL'].includes(String(proposal.citation_kind)) && (proposal.locator === null || sourceLocator(proposal.locator)) && stringArray(proposal.possible_duplicate_ids)
      && arrayOf(proposal.additional_support, support => isObject(support) && typeof support.supporting_span === 'string' && (support.locator === null || sourceLocator(support.locator))))
}
function recallFileResponse(value: unknown): boolean {
  return isObject(value) && hasStrings(value, ['artifact_id', 'kind', 'title', 'authority']) && isObject(value.state) && hasStrings(value.state, ['research_state', 'verification']) && stringArray(value.state.warnings)
    && ['why_relevant', 'relation_to_target', 'problem_scope', 'provenance', 'warnings'].every(key => stringArray(value[key]))
}
function fileSearchResponse(value: unknown): boolean {
  return isObject(value) && typeof value.problem_id === 'string' && arrayOf(value.files, recallFileResponse) && stringArray(value.warnings)
}
function historyResponse(value: unknown): boolean {
  return isObject(value) && hasStrings(value, ['classification', 'basis']) && stringArray(value.warnings)
    && ['canonical_matches', 'open_matches', 'failed_routes', 'counterexamples', 'proofs', 'source_files', 'soft_overlaps'].every(key => arrayOf(value[key], recallFileResponse))
}

async function request<T>(path: string, init?: RequestInit, valid?: (value: unknown) => boolean): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string | { kind: string; role: string; message?: string } } | null
    throw new Error(typeof body?.detail === 'object' ? `${body.detail.kind}: ${body.detail.message || body.detail.role + ' model is not configured. Settings → Models'}` : body?.detail || `HTTP ${response.status}`)
  }
  let value: unknown
  try { value = await response.json() } catch { throw new Error('Malformed API response: invalid JSON') }
  if (valid && !valid(value)) throw new Error('Malformed API response: unexpected workflow payload')
  return value as T
}

function mutation(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers)
  headers.set('X-Research-IDE', '1')
  return { ...init, headers }
}

const scope = (problemId: string) => `/api/problems/${encodeURIComponent(problemId)}`

async function downloadZip(url: string, filename: string) {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `HTTP ${response.status}`)
  }
  const href = URL.createObjectURL(await response.blob())
  const link = document.createElement('a'); link.href = href; link.download = filename
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}

const contextRequest = (route: string, pid: string, id: string, purpose: QueryPurpose, tokenBudget: number, threadId: string, includeProvisional: boolean, relatedMemory?: RelatedResearch, query = '') =>
  request<ResearchContextBundle>(`${scope(pid)}/${route}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target: { kind: 'claim', problem_id: pid, node_id: id },
      purpose, token_budget: tokenBudget, thread_id: threadId || null, include_provisional: includeProvisional, related_memory: relatedMemory || null, query }),
  })

const navigatorParams = (targetId: string, query: string, crossProblem: boolean, thread: string, limit: number) =>
  new URLSearchParams({ ...(targetId.trim() ? { target_id: targetId.trim() } : {}), q: query,
    cross_problem: String(crossProblem), ...(thread.trim() ? { thread_id: thread.trim() } : {}), limit: String(limit) })

export const api = {
  researchPortfolio: () => request<Record<string, unknown>[]>('/api/research/portfolio'),
  modelSettings: () => request<ProductModelSettings>('/api/settings/models'),
  saveModelSettings: (value: { roles: ModelRoles; credentials: Record<string, string> }) => request<ProductModelSettings>('/api/settings/models', mutation({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })),
  critiquePreflight: (pid: string, target: string) => request<CritiquePreflight>(`${scope(pid)}/records/${encodeURIComponent(target)}/critique-context`, undefined, critiquePreflightResponse),
  startCritique: (pid: string, target: string, settings: CritiqueSettings, bundleSha: string) => request<CritiqueRun>(`${scope(pid)}/records/${encodeURIComponent(target)}/critique`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings, bundle_sha256: bundleSha }) }), critiqueRunResponse),
  critiqueHistory: (pid: string, target: string) => request<CritiqueRun[]>(`${scope(pid)}/records/${encodeURIComponent(target)}/critiques`, undefined, value => arrayOf(value, critiqueRunResponse)),
  critiqueRun: (pid: string, id: string) => request<CritiqueRun>(`${scope(pid)}/critiques/${encodeURIComponent(id)}`, undefined, critiqueRunResponse),
  previewProblem: (metadata: ProblemInput, files: File[]) => {
    const data = new FormData(); data.append('metadata', JSON.stringify(metadata)); files.forEach(file => data.append('files', file))
    return request<ProblemPreview>('/api/problems/preview', mutation({ method: 'POST', body: data }))
  },
  createProblem: (metadata: ProblemInput, files: File[], digest: string) => {
    const data = new FormData(); data.append('metadata', JSON.stringify(metadata)); data.append('digest', digest); data.append('confirmed', 'true'); files.forEach(file => data.append('files', file))
    return request<CreatedProblem>('/api/problems', mutation({ method: 'POST', body: data }))
  },
  sources: (pid: string) => request<RecallFile[]>(`${scope(pid)}/sources`),
  digestPreflight: (pid: string, source: string) => request<DigestPreflight>(`${scope(pid)}/sources/${encodeURIComponent(source)}/digest-context`, undefined, digestPreflightResponse),
  startSourceDigest: (pid: string, source: string, settings: DigestSettings, sha: string) => request<DigestRun>(`${scope(pid)}/sources/${encodeURIComponent(source)}/digest`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings, context_sha256: sha, confirmed: true }) }), digestRunResponse),
  sourceDigests: (pid: string, source: string) => request<DigestRun[]>(`${scope(pid)}/sources/${encodeURIComponent(source)}/digests`, undefined, value => arrayOf(value, digestRunResponse)),
  sourceDigest: (pid: string, id: string) => request<DigestRun>(`${scope(pid)}/source-digests/${encodeURIComponent(id)}`, undefined, digestRunResponse),
  stageSourceProposal: (pid: string, digest: string, proposal: string) => request<StagedSourceProposal>(`${scope(pid)}/source-digests/${encodeURIComponent(digest)}/proposals/${encodeURIComponent(proposal)}/review`, mutation({ method: 'POST' })),
  confirmSourceLocation: (pid: string, digest: string, proposal: string, locator: SourceLocator, span: string) => request(`${scope(pid)}/source-digests/${encodeURIComponent(digest)}/proposals/${encodeURIComponent(proposal)}/location`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ locator, supporting_span: span, confirmed: true }) })),
  addSource: (pid: string, file: File) => {
    const data = new FormData(); data.append('file', file); data.append('confirmed', 'true')
    return request<{ source_id: string; filename: string; sha256: string }>(`${scope(pid)}/sources`, mutation({ method: 'POST', body: data }))
  },
  systemHealth: () => request<HealthReport>('/api/maintenance/health'),
  downloadSnapshot: () => downloadZip('/api/maintenance/snapshot', 'workspace_snapshot.zip'),
  downloadHandoff: (pid: string, tid: string) => downloadZip(`${scope(pid)}/handoff/${encodeURIComponent(tid)}`, `${tid}_handoff.zip`),
  verifySnapshot: (file: File) => {
    const data = new FormData(); data.append('file', file)
    return request<{ valid: boolean; file_count: number }>('/api/maintenance/snapshot/verify', mutation({ method: 'POST', body: data }))
  },
  researchSettings: () => request<ResearchDefaults>('/api/settings'),
  saveResearchSettings: (settings: ResearchDefaults) => request<ResearchDefaults>('/api/settings', mutation({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) })),
  routeResearchIntent: (text: string, allowModel = false) => request<{ action: ResearchIntent | null; source: string }>('/api/actions/intent', mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, allow_model: allowModel }) })),
  preflightEpisode: (pid: string, file: File) => {
    const data = new FormData(); data.append('file', file)
    return request<EpisodePreflight>(`${scope(pid)}/episodes/preflight`, mutation({ method: 'POST', body: data }))
  },
  commitEpisode: (pid: string, file: File, digest: string) => {
    const data = new FormData(); data.append('file', file); data.append('digest', digest)
    return request<UploadResult>(`${scope(pid)}/episodes/import`, mutation({ method: 'POST', body: data }))
  },
  agentRuns: (pid: string) => request<AgentRun[]>(`${scope(pid)}/research-runs`),
  agentEvents: (pid: string, id: string) => request<AgentEvent[]>(`${scope(pid)}/research-runs/${encodeURIComponent(id)}/events`),
  startAgent: (pid: string, settings: AgentSettings) => request<AgentRun>(`${scope(pid)}/research-runs?entry=web`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) })),
  startOperatorAgent: (pid: string, settings: AgentSettings) => request<AgentRun>(`${scope(pid)}/research-runs?entry=operator`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) })),
  researchState: (pid: string, target: string, provisional = true) => request<{ markdown: string; research_status: string; latest_handoff_episode_id: string | null }>(`${scope(pid)}/research-runs/state?target_id=${encodeURIComponent(target)}&include_provisional=${provisional}`),
  agentRun: (pid: string, id: string) => request<AgentRun>(`${scope(pid)}/research-runs/${encodeURIComponent(id)}`),
  agentProgress: (pid: string, id: string) => request<ResearchRunProgress>(`${scope(pid)}/research-runs/${encodeURIComponent(id)}/progress`),
  coordinator: (value: CoordinatorRequest) => request<CoordinatorResponse>('/api/coordinator', mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })),
  stopAgent: (pid: string, id: string) => request<{ stop_requested: boolean }>(`${scope(pid)}/research-runs/${encodeURIComponent(id)}/stop`, mutation({ method: 'POST' })),
  resumeAgent: (pid: string, id: string) => request<AgentRun>(`${scope(pid)}/research-runs/${encodeURIComponent(id)}/resume`, mutation({ method: 'POST' })),
  agentAuditUrl: (pid: string, id: string) => `${scope(pid)}/research-runs/${encodeURIComponent(id)}/audit`,
  agentArtifactUrl: (pid: string, id: string, path: string) => `${scope(pid)}/research-runs/${encodeURIComponent(id)}/artifact?${new URLSearchParams({ path })}`,
  hardPolicy: (pid: string) => request<RelationPolicy>(`${scope(pid)}/relations/policy`),
  setRelationPolicy: (pid: string, policy: RelationPolicy) => request<RelationPolicy>(`${scope(pid)}/relations/policy`, mutation({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(policy) })),
  hardPool: (pid: string, eid: string | null, status = '') => request<RelationPoolItem[]>(`${scope(pid)}/relations/pool?${new URLSearchParams({ ...(eid ? { episode_id: eid } : {}), ...(status ? { status } : {}) })}`),
  hardScout: (pid: string, eid: string, settings: RelationModelSettings, ids: string[] | null, rerun: boolean) => request<RelationJob>(`${scope(pid)}/episodes/${encodeURIComponent(eid)}/relation-scout`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...settings, candidate_ids: ids, rerun }) })),
  hardAdjudicate: (pid: string, eid: string | null, settings: RelationModelSettings, ids: string[] | null, tokenBudget: number) => request<RelationJob>(`${scope(pid)}/relations/adjudicate`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...settings, episode_id: eid, proposal_ids: ids, token_budget: tokenBudget }) })),
  hardJob: (id: string) => request<RelationJob>(`/api/relation-jobs/${encodeURIComponent(id)}`),
  hardScoutRuns: (pid: string, eid: string | null) => request<RelationRun[]>(`${scope(pid)}/relations/scout-runs?${new URLSearchParams(eid ? { episode_id: eid } : {})}`),
  hardAdjudicationRuns: (pid: string) => request<RelationRun[]>(`${scope(pid)}/relations/adjudication-runs`),
  hardHistory: (pid: string) => request<RelationDecision[]>(`${scope(pid)}/relations/history`),
  hardHuman: (pid: string, id: string, decision: string, rationale: string, relation: string | null = null, target: string | null = null) => request<RelationDecision>(`${scope(pid)}/relations/${encodeURIComponent(id)}/human`, mutation({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, rationale, corrected_relation: relation, corrected_target_id: target }) })),
  hardEnroll: (pid: string, eid: string) => request<RelationPoolItem[]>(`${scope(pid)}/episodes/${encodeURIComponent(eid)}/relations/enroll-explicit`, mutation({ method: 'POST' })),
  findFiles: (pid: string, targetId: string, query: string, crossProblem: boolean, thread: string, limit: number) =>
    request<FileSearchResult>(`${scope(pid)}/recall/find-files?${navigatorParams(targetId, query, crossProblem, thread, limit)}`, undefined, fileSearchResponse),
  checkHistory: (pid: string, targetId: string, query: string, crossProblem: boolean, thread: string, limit: number) =>
    request<HistoryCheckResult>(`${scope(pid)}/recall/check-history?${navigatorParams(targetId, query, crossProblem, thread, limit)}`, undefined, historyResponse),
  originalFileUrl: (pid: string, file: RecallFile) =>
    `${scope(file.problem_id || pid)}/recall/file?${new URLSearchParams({ artifact_id: file.artifact_id, kind: file.kind, cross_problem: String(file.problem_id === null) })}`,
  readOriginalFile: async (pid: string, file: RecallFile) => {
    const response = await fetch(api.originalFileUrl(pid, file))
    if (!response.ok) throw new Error(`Unable to read resource: HTTP ${response.status}`)
    return response.blob()
  },
  buildContext: (pid: string, id: string, purpose: QueryPurpose, tokenBudget: number, threadId: string, includeProvisional: boolean, relatedMemory?: RelatedResearch, query = '') =>
    contextRequest('recall/context', pid, id, purpose, tokenBudget, threadId, includeProvisional, relatedMemory, query),
  batchReview: (pid: string, ids: string[], decision: Decision) =>
    request<{ candidate_id: string; review: Review | null; error: string | null }[]>(`${scope(pid)}/reviews/batch`, mutation({
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: ids.map(candidate_id => ({ candidate_id, decision })) }),
    })),
  problems: () => request<Problem[]>('/api/problems'),
  researchMap: (pid: string) => request<ResearchMap>(`${scope(pid)}/research-map`, undefined, researchMapResponse),
  objects: (pid: string, kind: ObjectKind) =>
    request<ResearchObject[]>(`${scope(pid)}/records?kind=${kind}`),
  object: (pid: string, kind: ObjectKind, id: string) =>
    request<ResearchObject>(`${scope(pid)}/records/${kind}/${encodeURIComponent(id)}`),
  episodes: (pid: string) => request<EpisodeSummary[]>(`${scope(pid)}/episodes`),
  episode: (pid: string, eid: string) =>
    request<EpisodeDetail>(`${scope(pid)}/episodes/${encodeURIComponent(eid)}`),
  candidates: (pid: string, eid: string) =>
    request<ProposalRow[]>(`${scope(pid)}/episodes/${encodeURIComponent(eid)}/proposals`),
  review: (pid: string, id: string, decision: Decision, edits?: Record<string, unknown>) =>
    request<Review>(`${scope(pid)}/reviews/${encodeURIComponent(id)}`, mutation({
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, edits: edits || null }),
    })),
  relatedMemory: (pid: string, targetId: string, query: string) =>
    request<RelatedResearch>(`${scope(pid)}/recall/related?target_id=${encodeURIComponent(targetId)}&q=${encodeURIComponent(query)}`),
  memoryObject: (pid: string, id: string, artifactType: string) =>
    request<SearchHit>(`${scope(pid)}/recall/record/${encodeURIComponent(id)}?object_type=${encodeURIComponent(artifactType)}`),
  rerankMemory: (pid: string, targetId: string, query: string, provider: string, model: string, effort: string | null, expansionIds: string[]) =>
    request<MemoryJob>(`${scope(pid)}/recall/related/rerank`, mutation({
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_id: targetId, query, provider, model, reasoning_effort: effort, expansion_ids: expansionIds }),
    })),
  memoryJob: (id: string) => request<MemoryJob>(`/api/recall-jobs/${encodeURIComponent(id)}`),
}
