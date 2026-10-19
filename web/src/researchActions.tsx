import { createContext, useContext } from 'react'
import { api, type AgentSettings, type Decision, type RelationModelSettings, type ResearchIntent, type RelationPolicy, type ProblemInput } from './api'

export type ActionOrigin = 'quick_action' | 'research_chat'
export const ResearchOrigin = createContext<ActionOrigin>('quick_action')

/** Both entrances choose a task. Only explicit workflow controls commit actions. */
export function taskAction(intent: ResearchIntent['intent'], target_id: string | null = null, query = ''): ResearchIntent {
  return { intent, target_id, query }
}

export function createResearchActions(pid: string, origin: ActionOrigin) {
  // Ephemeral UI audit only; authoritative audit remains in each existing workflow.
  const audit = (action: string) => window.dispatchEvent(new CustomEvent('research-action', { detail: { action, origin, problem_id: pid } }))
  return {
    previewProblem: (metadata: ProblemInput, files: File[]) => { audit('PREVIEW_PROBLEM'); return api.previewProblem(metadata, files) },
    createProblem: (metadata: ProblemInput, files: File[], digest: string) => { audit('CREATE_PROBLEM'); return api.createProblem(metadata, files, digest) },
    addSource: (file: File) => { audit('ADD_SOURCE'); return api.addSource(pid, file) },
    preflight: (file: File) => { audit('PREFLIGHT_EPISODE'); return api.preflightEpisode(pid, file) },
    importEpisode: (file: File, digest: string) => { audit('COMMIT_EPISODE_IMPORT'); return api.commitEpisode(pid, file, digest) },
    startResearch: (settings: AgentSettings, entry: 'web' | 'operator' = 'web') => { audit('START_RESEARCH'); return entry === 'operator' ? api.startOperatorAgent(pid, settings) : api.startAgent(pid, settings) },
    startCritique: (target: string, settings: import('./api').CritiqueSettings, bundleSha: string) => { audit('CRITIQUE_RESEARCH_RESULT'); return api.startCritique(pid, target, settings, bundleSha) },
    startSourceDigest: (source: string, settings: import('./api').DigestSettings, sha: string) => { audit('DIGEST_SOURCE'); return api.startSourceDigest(pid, source, settings, sha) },
    reviewSourceProposal: (digest: string, proposal: string) => { audit('REVIEW_SOURCE_PROPOSAL'); return api.stageSourceProposal(pid, digest, proposal) },
    confirmSourceLocation: (digest: string, proposal: string, locator: import('./api').SourceLocator, span: string) => { audit('CONFIRM_SOURCE_LOCATION'); return api.confirmSourceLocation(pid, digest, proposal, locator, span) },
    stopResearch: (id: string) => { audit('STOP_RESEARCH'); return api.stopAgent(pid, id) },
    resumeResearch: (id: string) => { audit('RESUME_RESEARCH'); return api.resumeAgent(pid, id) },
    review: (id: string, decision: Decision, edits?: Record<string, unknown>) => { audit('APPLY_REVIEW'); return api.review(pid, id, decision, edits) },
    batchReview: (ids: string[], decision: Decision) => { audit('APPLY_BATCH_REVIEW'); return api.batchReview(pid, ids, decision) },
    findRelated: (target: string, query: string, cross: boolean, thread: string, limit: number) => { audit('FIND_RELATED_RESEARCH'); return api.findFiles(pid, target, query, cross, thread, limit) },
    checkHistory: (target: string, query: string, cross: boolean, thread: string, limit: number) => { audit('CHECK_PRIOR_RESEARCH'); return api.checkHistory(pid, target, query, cross, thread, limit) },
    rerank: (target: string, query: string, settings: RelationModelSettings, expansionIds: string[]) => { audit('SMART_RECALL'); return api.rerankMemory(pid, target, query, settings.provider, settings.model, settings.reasoning_effort, expansionIds) },
    scout: (eid: string, settings: RelationModelSettings, ids: string[] | null, rerun: boolean) => { audit('RUN_HARD_SCOUT'); return api.hardScout(pid, eid, settings, ids, rerun) },
    adjudicate: (eid: string | null, settings: RelationModelSettings, ids: string[] | null, tokens: number) => { audit('RUN_HARD_ADJUDICATION'); return api.hardAdjudicate(pid, eid, settings, ids, tokens) },
    humanRelation: (id: string, action: string, rationale: string, relation: string | null, target: string | null) => { audit('HUMAN_RELATION'); return api.hardHuman(pid, id, action, rationale, relation, target) },
    setPolicy: (value: RelationPolicy) => { audit('SET_RELATION_POLICY'); return api.setRelationPolicy(pid, value) },
    enroll: (eid: string) => { audit('ENROLL_EXPLICIT_RELATIONS'); return api.hardEnroll(pid, eid) },
  }
}

export function useResearchActions(pid: string) { return createResearchActions(pid, useContext(ResearchOrigin)) }
