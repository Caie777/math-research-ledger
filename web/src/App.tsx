import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Markdown } from './Markdown'
import { api, type ProposalRow, type Decision, type ObjectKind, type MemoryHit, type RecallFile, type ResearchIntent, type ResearchMapNode } from './api'
import {
  CANDIDATE_LABELS, OBJECT_KINDS, candidateRecordStatus, candidateReviewStatus,
  candidateTitle, type Selection,
} from './researchState'
import './styles.css'
import { RecallPanel } from './RecallPanel'
import { LogicalRelationsPanel } from './LogicalRelationsPanel'
import { ResearchAgentPanel } from './ResearchAgentPanel'
import { ResearchExplorer } from './ResearchExplorer'
import { ResearchAssistant } from './ResearchAssistant'
import { ResearchSettings } from './ResearchSettings'
import { ImportEpisodeTask } from './ImportEpisodeTask'
import { ResearchStatusTask } from './ResearchStatusTask'
import { ResourceReader } from './ResourceReader'
import { ResearchMap } from './ResearchMap'
import { CritiquePanel, supportsCritique } from './CritiquePanel'
import { SourceDigestControl } from './SourceDigest'
import { AddSourceTask, MaintenanceTask, NewProblemTask } from './ProblemTasks'
import { ActionConfirmation, llmDetails, type Confirmation } from './ActionConfirmation'
import { createResearchActions, ResearchOrigin, taskAction, type ActionOrigin } from './researchActions'
import researchUserGuideUrl from '../../README.md?url'

function Badge({ label, tone = 'muted' }: { label: string; tone?: 'muted' | 'warn' | 'good' }) {
  return <span className={`badge ${tone}`}>{label}</span>
}

function ErrorLine({ error }: { error: unknown }) {
  return error ? <p className="error" role="alert">{error instanceof Error ? error.message : String(error)}</p> : null
}

type LinkedRecord = { id: string; statement?: string; title?: string; objective?: string; status?: string; conclusion_relation?: string }
function linkedRecords(metadata: Record<string, unknown>, key: string): LinkedRecord[] {
  const value = metadata[key]
  return Array.isArray(value) ? value.filter((item): item is LinkedRecord =>
    !!item && typeof item === 'object' && typeof item.id === 'string'
  ) : []
}

function stringList(metadata: Record<string, unknown>, key: string): string[] {
  const value = metadata[key]
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function neighborState(metadata: Record<string, unknown>, id: string): string {
  const states = metadata.neighbor_states as Record<string, { research_state?: string }> | undefined
  return states?.[id]?.research_state || 'state not loaded'
}

function counterexampleRelation(metadata: Record<string, unknown>, id: string): string {
  const relations = (metadata.confirmed_relations || metadata.human_confirmed_relations || metadata.relations) as { source_id: string; relation: string; target_id: string }[] | undefined
  const accepted = relations?.filter(r => r.source_id === id && ['REFUTES', 'INVALIDATES'].includes(r.relation)) || []
  return accepted.length ? accepted.map(r => `accepted ${r.relation} ${r.target_id}`).join('; ') : 'object only; no accepted REFUTES / INVALIDATES'
}

export function App() {
  const queryClient = useQueryClient()
  const [activeIntent, setActiveIntent] = useState<ResearchIntent | null>(null)
  const [origin, setOrigin] = useState<ActionOrigin>('quick_action')
  const [retrievalMode, setRetrievalMode] = useState<'explorer' | 'search' | 'recall'>('explorer')
  const [recallQuery, setRecallQuery] = useState('')
  const [recallRequest, setRecallRequest] = useState(0)
  const [recallTarget, setRecallTarget] = useState<string | null>(null)
  const [reviewScope, setReviewScope] = useState<'episode' | 'pending'>('episode')
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const settings = useQuery({ queryKey: ['research-settings'], queryFn: api.researchSettings })
  const problems = useQuery({ queryKey: ['problems'], queryFn: api.problems })
  const [problemId, setProblemId] = useState('')
  useEffect(() => {
    if (!problemId && problems.data?.length && activeIntent?.intent !== 'CREATE_PROBLEM') setProblemId(problems.data[0].id)
  }, [problemId, problems.data, activeIntent?.intent])
  const currentProblem = useRef(problemId)
  currentProblem.current = problemId
  const [episodeId, setEpisodeId] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [readerView, setReaderView] = useState<'document' | 'map'>('document')
  const [digestView, setDigestView] = useState(false)
  const [digestId, setDigestId] = useState<string | null>(null)
  useEffect(() => { setDigestView(false); setDigestId(null) }, [problemId, selection?.id])
  const [candidateFilter, setCandidateFilter] = useState('all')
  const [rawView, setRawView] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editBody, setEditBody] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const [editTarget, setEditTarget] = useState('')
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [effort, setEffort] = useState('default')
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([])
  const [notice, setNotice] = useState('')
  const [contextEpoch, setContextEpoch] = useState(0)
  const [memoryQuery, setMemoryQuery] = useState('')
  const [memoryJobId, setMemoryJobId] = useState<string | null>(null)
  const [memoryPreferences, setMemoryPreferences] = useState<Record<string, string>>({})
  const memoryTargetId = selection?.id || null
  const actions = createResearchActions(problemId, origin)
  useEffect(() => { if (settings.data) { setProvider(settings.data.recall.provider); setModel(settings.data.recall.model); setEffort(settings.data.recall.reasoning_effort || 'default') } }, [settings.data])

  const episodes = useQuery({
    queryKey: ['episodes', problemId], queryFn: () => api.episodes(problemId), enabled: !!problemId,
  })
  const sources = useQuery({ queryKey: ['sources', problemId], queryFn: () => api.sources(problemId), enabled: !!problemId })
  const objectQueries = useQueries({ queries: OBJECT_KINDS.map(({ kind }) => ({
    queryKey: ['objects', problemId, kind], queryFn: () => api.objects(problemId, kind), enabled: !!problemId,
  })) })
  const episode = useQuery({
    queryKey: ['episode', problemId, episodeId],
    queryFn: () => api.episode(problemId, episodeId!), enabled: !!episodeId,
  })
  const candidates = useQuery({
    queryKey: ['candidates', problemId, episodeId],
    queryFn: () => api.candidates(problemId, episodeId!), enabled: !!episodeId,
  })
  const pendingQueries = useQueries({ queries: (episodes.data || []).map(row => ({
    queryKey: ['candidates', problemId, row.episode.episode_id], queryFn: () => api.candidates(problemId, row.episode.episode_id),
    enabled: activeIntent?.intent === 'HUMAN_REVIEW' && reviewScope === 'pending',
  })) })
  const reviewRows = reviewScope === 'pending' ? pendingQueries.flatMap(query => (query.data || []).filter(row => !row.review)) : candidates.data || []
  const selectedCandidate = reviewRows.find(row =>
    selection?.type === 'candidate' && row.candidate.candidate_id === selection.id
  ) || null
  const selectedObject = useQuery({
    queryKey: ['object', problemId, selection],
    queryFn: () => {
      if (!selection || selection.type !== 'object') throw new Error('No object selected')
      return api.object(problemId, selection.kind, selection.id)
    },
    enabled: selection?.type === 'object',
  })
  const memoryObject = useQuery({
    queryKey: ['memory-object', problemId, selection],
    queryFn: () => {
      if (selection?.type !== 'memory') throw new Error('No memory object selected')
      return api.memoryObject(problemId, selection.id, selection.artifactType)
    }, enabled: selection?.type === 'memory',
  })
  const relatedMemory = useQuery({
    queryKey: ['related-memory', problemId, memoryTargetId, memoryQuery],
    queryFn: () => api.relatedMemory(problemId, memoryTargetId!, memoryQuery),
    enabled: !!memoryTargetId,
  })
  const memoryJob = useQuery({
    queryKey: ['memory-job', memoryJobId], queryFn: () => api.memoryJob(memoryJobId!),
    enabled: !!memoryJobId,
    refetchInterval: query => query.state.data?.status === 'running' ? 1000 : false,
  })
  const rerankMemory = useMutation({
    mutationFn: (expansionIds: string[]) => actions.rerank(memoryTargetId!, memoryQuery, { provider, model, reasoning_effort: effort === 'default' ? null : effort }, expansionIds), onSuccess: result => setMemoryJobId(result.job_id),
  })
  const related = (memoryJob.data?.result?.target_id === memoryTargetId
    ? memoryJob.data.result : null) || relatedMemory.data
  useEffect(() => {
    setMemoryJobId(null)
    setMemoryPreferences({})
    setMemoryQuery('')
  }, [problemId, memoryTargetId])
  useEffect(() => { setMemoryJobId(null) }, [memoryQuery])

  useEffect(() => {
    if (!episodeId && episodes.data?.length) {
      const id = episodes.data[0].episode.episode_id
      setEpisodeId(id)
      if (!selection) setSelection({ type: 'episode', id })
    }
  }, [episodeId, episodes.data, selection])
  useEffect(() => {
    setEditOpen(false)
    setEditBody(selectedCandidate?.candidate.body || '')
    setEditSummary(selectedCandidate?.candidate.summary || '')
    setEditTarget(selectedCandidate?.candidate.target_id || '')
  }, [selectedCandidate?.candidate.candidate_id])

  const review = useMutation({
    mutationFn: ({ id, decision, edits }: { id: string; decision: Decision; edits?: Record<string, unknown> }) =>
      actions.review(id, decision, edits),
    onSuccess: async result => {
      setNotice(`${result.candidate_id}: ${result.decision} · Problem Record ${result.mapped_id || '无写入'}`)
      setEditOpen(false)
      setContextEpoch(current => current + 1)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['candidates', problemId, episodeId] }),
        queryClient.invalidateQueries({ queryKey: ['hard'] }),
        queryClient.invalidateQueries({ queryKey: ['episodes', problemId] }),
        queryClient.invalidateQueries({ queryKey: ['objects', problemId] }),
        queryClient.invalidateQueries({ queryKey: ['object', problemId] }),
        queryClient.invalidateQueries({ queryKey: ['memory-object', problemId] }),
        queryClient.invalidateQueries({ queryKey: ['related-memory', problemId] }),
      ])
      setMemoryJobId(null)
    },
  })
  const batchReview = useMutation({
    mutationFn: ({ ids, decision }: { ids: string[]; decision: Decision }) => actions.batchReview(ids, decision),
    onSuccess: async results => {
      setContextEpoch(current => current + 1)
      setMemoryJobId(null)
      setNotice(results.map(r => `${r.candidate_id}: ${r.error || r.review?.decision}`).join(' · '))
      await queryClient.invalidateQueries()
    },
  })
  const sourceReview = useMutation({
    mutationFn: ({ digest, proposal }: { digest: string; proposal: string }) => actions.reviewSourceProposal(digest, proposal),
    onSuccess: async result => {
      setEpisodeId(result.episode_id); setReviewScope('episode')
      setSelection({ type: 'candidate', id: result.candidate_id }); setReaderView('document')
      setActiveIntent(taskAction('HUMAN_REVIEW', result.candidate_id))
      await queryClient.invalidateQueries({ queryKey: ['episodes', problemId] })
      await queryClient.invalidateQueries({ queryKey: ['candidates', problemId, result.episode_id] })
    }, onError: error => setNotice(String(error)),
  })

  function chooseProblem(id: string) {
    setReaderView('document')
    setActiveIntent(null); setConfirmation(null); setRetrievalMode('explorer'); setRecallQuery(''); setRecallRequest(0); setReviewScope('episode')
    setProblemId(id)
    setEpisodeId(null)
    setSelection(null)
    setSelectedCandidateIds([])
  }
  function chooseEpisode(id: string) {
    setReaderView('document')
    setConfirmation(null)
    setEpisodeId(id)
    setSelection({ type: 'episode', id })
    setSelectedCandidateIds([])
    setRawView(false)
  }
  function chooseCandidate(row: ProposalRow) {
    setReaderView('document')
    setConfirmation(null)
    setEpisodeId(row.candidate.episode_id)
    setSelection({ type: 'candidate', id: row.candidate.candidate_id })
    setRawView(false)
  }
  function chooseSearchObject(id: string, artifactType: string) {
    setReaderView('document')
    if (artifactType === 'dossier:source') {
      const file = sources.data?.find(source => source.artifact_id === id)
      if (file) setSelection({ type: 'resource', file, id })
      return
    }
    if (artifactType === 'dossier:episode') { chooseEpisode(id); return }
    if (!['dossier:claim', 'dossier:proof', 'dossier:counterexample', 'dossier:evidence', 'dossier:failed'].includes(artifactType)) {
      setSelection({ type: 'memory', artifactType, id }); return
    }
    const kind: ObjectKind = artifactType === 'dossier:proof' ? 'proof'
      : artifactType === 'dossier:counterexample' ? 'counterexample'
      : artifactType === 'dossier:evidence' ? 'evidence'
      : artifactType === 'dossier:failed' ? 'failed_attempt'
      : objectQueries[OBJECT_KINDS.findIndex(item => item.kind === 'gap')].data?.some(item => item.id === id) ? 'gap' : 'claim'
    setSelection({ type: 'object', kind, id })
  }
  function openMemory(hit: MemoryHit) {
    setReaderView('document')
    if (hit.navigation_kind === 'gap') setSelection({ type: 'object', kind: 'gap', id: hit.object_id })
    else chooseSearchObject(hit.object_id, hit.object_type)
  }
  function openRecallFile(file: RecallFile) {
    setReaderView('document')
    if (file.problem_id === null || file.kind === 'dossier:source' || !file.kind.startsWith('dossier:')) { setSelection({ type: 'resource', file, id: file.artifact_id }); return }
    if (file.problem_id && file.problem_id !== problemId) chooseProblem(file.problem_id)
    if (file.kind === 'dossier:claim' && file.state.kind === 'OPEN_GAP') {
      setSelection({ type: 'object', kind: 'gap', id: file.artifact_id })
    } else chooseSearchObject(file.artifact_id, file.kind)
  }

  const [leftWidth, setLeftWidth] = useState(20)
  const [rightWidth, setRightWidth] = useState(30)
  const shellRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<'left' | 'right' | null>(null)
  useEffect(() => {
    function move(event: PointerEvent) {
      if (!dragRef.current || !shellRef.current) return
      const rect = shellRef.current.getBoundingClientRect()
      const percent = (event.clientX - rect.left) / rect.width * 100
      if (dragRef.current === 'left') setLeftWidth(Math.min(35, Math.max(15, percent)))
      else setRightWidth(Math.min(45, Math.max(18, 100 - percent)))
    }
    function stop() { dragRef.current = null }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop) }
  }, [])

  const visibleProposals = reviewRows.filter(row =>
    candidateFilter === 'all' || row.candidate.kind === candidateFilter
  )

  function dispatchTask(intent: ResearchIntent, source: ActionOrigin) {
    setOrigin(source); setConfirmation(null)
    if (!problemId && !problems.isPending && !['CREATE_PROBLEM', 'SYSTEM_HEALTH', 'EXPORT_WORKSPACE_SNAPSHOT', 'VERIFY_SNAPSHOT'].includes(intent.intent)) {
      setNotice('请先新建或选择研究问题。'); return
    }
    if (intent.intent === 'UNSUPPORTED') { setNotice('当前 Research Assistant 不支持该任务。'); return }
    if (intent.intent === 'REVIEW_SOURCE_PROPOSAL') {
      if (intent.target_id && intent.query) sourceReview.mutate({ digest: intent.target_id, proposal: intent.query })
      return
    }
    if (['DIGEST_SOURCE', 'OPEN_SOURCE_DIGEST'].includes(intent.intent)) {
      const file = (queryClient.getQueryData<RecallFile[]>(['sources', problemId]) || sources.data)?.find(file => file.artifact_id === intent.target_id)
      if (!file) { setNotice('请选择当前 Problem 中的 Source。'); return }
      setSelection({ type: 'resource', id: file.artifact_id, file }); setReaderView('document')
      // Source selection resets local Reader state; open the Digest tab on the next render.
      setActiveIntent(intent)
      return
    }
    if (intent.intent === 'OPEN_RESOURCE') {
      const id = intent.target_id
      const object = objectQueries.flatMap(query => query.data || []).find(object => object.id === id)
      if (object) { setSelection({ type: 'object', kind: object.kind, id: object.id }); return }
      if (episodes.data?.some(row => row.episode.episode_id === id)) { chooseEpisode(id!); return }
      setNotice('未在已加载资源中找到该 ID。请使用左栏 Recall 查找原资源。'); return
    }
    setActiveIntent(intent)
    if (intent.intent === 'HUMAN_REVIEW' && episodes.data?.[0]) { chooseEpisode(episodes.data[0].episode.episode_id); setReviewScope('episode') }
    if (intent.intent === 'FIND_RELATED_RESEARCH') { setRetrievalMode('recall'); setRecallQuery(intent.query); setRecallTarget(intent.target_id); setRecallRequest(current => current + 1) }
    if (intent.target_id && ['CONTINUE_RESEARCH', 'RESEARCH_STATUS'].includes(intent.intent)) {
      const object = objectQueries.flatMap(query => query.data || []).find(object => object.id === intent.target_id)
      if (object) setSelection({ type: 'object', kind: object.kind, id: object.id })
    }
  }
  function openMapNode(node: ResearchMapNode) {
    setReaderView('document'); setRawView(false); setConfirmation(null)
    if (node.episode_id) {
      setEpisodeId(node.episode_id)
      setSelection({ type: 'candidate', id: node.id })
    } else if (node.type !== 'problem') {
      setSelection({ type: 'object', kind: node.type, id: node.id })
    }
  }
  function requestReview(id: string, decision: Decision, edits?: Record<string, unknown>) {
    setConfirmation({ title: `Human ${decision}`, details: { Proposal: id, Decision: decision, 'Problem Record authority': 'Human Review；不等于数学验证' }, run: () => review.mutate({ id, decision, edits }) })
  }
  function requestBatch(decision: Decision) {
    const ids = [...selectedCandidateIds]
    setConfirmation({ title: `确认批量 Human ${decision}`, details: { Proposals: ids.join(', '), Count: ids.length, Decision: decision }, run: () => batchReview.mutate({ ids, decision }) })
  }
  return <div className="app">
    <header className="topbar">
      <strong>Structured Mathematical Research · Research IDE</strong>
      <span>{problems.data?.find(p => p.id === problemId)?.title || problemId}</span>
      <ResearchSettings />
      <a href={researchUserGuideUrl} download="README.md" title="下载 Quick Start">使用说明</a>
      <Badge label="local workspace" />
    </header>
    {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
    <div ref={shellRef} className="panels" style={{ gridTemplateColumns: `${leftWidth}% 6px minmax(0,1fr) 6px ${rightWidth}%` }}>
      <aside className="panel tree" aria-label="Research Explorer">
        <h2>Retrieval</h2><p className="meta">Search · Uses LLM: No</p>
        <label className="field">Problem
          <select aria-label="Problem" value={problemId} onChange={e => chooseProblem(e.target.value)}>
            {!problemId && <option value="">请新建或选择研究问题</option>}
            {(problems.data || []).map(problem => <option key={problem.id} value={problem.id}>{problem.id} · {problem.title}</option>)}
          </select>
        </label>
        <ErrorLine error={problems.error || episodes.error} />
        <div className="retrieval-tabs" role="tablist" aria-label="Retrieval modes">{(['explorer', 'search', 'recall'] as const).map(mode => <button role="tab" aria-selected={retrievalMode === mode} key={mode} onClick={() => { setRetrievalMode(mode); setRecallRequest(0) }}>{mode === 'explorer' ? 'Explorer' : mode === 'search' ? 'Search' : 'Recall'}</button>)}</div>
        <div hidden={retrievalMode === 'recall'}><ResearchExplorer key={problemId} episodes={episodes.data || []}
          sources={sources.data || []} onSource={openRecallFile}
          objects={Object.fromEntries(OBJECT_KINDS.map(({ kind }, index) => [kind, objectQueries[index].data || []]))}
          selection={selection} onEpisode={chooseEpisode}
          onObject={(kind, id) => { setReaderView('document'); setSelection({ type: 'object', kind, id }); setRawView(false) }} /></div>
        {retrievalMode === 'recall' && <ResearchOrigin.Provider value={origin}>
        <section id="navigator" className="research-navigator" aria-label="Recall">
          <h2 id="navigator-heading">Smart Recall</h2>
          <RecallPanel key={`${problemId}:${recallRequest}`} initialQuery={recallQuery} recallRequest={recallRequest} problemId={problemId} selectedTarget={recallRequest ? recallTarget : memoryTargetId} contextEpoch={contextEpoch} relatedMemory={related} onOpen={openRecallFile} />
        <details className="related-memory" aria-label="Related Research"><summary>Smart Recall rerank / related objects</summary>
          <p className="meta">当前目标 {memoryTargetId || '未选择'} · 分数只服务本次查询，不是数学关系。</p>
          <label className="field">Memory query<input aria-label="Memory query" value={memoryQuery} onChange={e => setMemoryQuery(e.target.value)} placeholder="留空使用当前对象" /></label>
          <p>{relatedMemory.data?.hits.length || 0} retrieval candidates · approximately {relatedMemory.data?.hits.length ? 1 : 0} rerank batch</p>
          <button disabled={!memoryTargetId || !model.trim() || !relatedMemory.data?.hits.length || rerankMemory.isPending || memoryJob.data?.status === 'running'} onClick={() => setConfirmation({ title: 'Smart Recall semantic rerank', details: { ...llmDetails('Semantic Rerank', 'selected recalled research records'), Target: memoryTargetId, Provider: provider, Model: model, Reasoning: effort }, run: () => rerankMemory.mutate([]) })}>Rerank related memory ({provider === 'codex' ? 'Codex CLI' : 'model API'})</button>
          <ErrorLine error={relatedMemory.error || rerankMemory.error || memoryJob.error} />
          {memoryJob.data && <p>Rerank: {memoryJob.data.status} · {memoryJob.data.error}</p>}
          {related?.provider && <small>{related.provider}/{related.actual_models.join(', ')} · {related.elapsed_seconds.toFixed(1)}s · usage {JSON.stringify(related.usage)}</small>}
          {(related?.hits || []).map(hit => <details key={`${hit.object_type}:${hit.object_id}`}>
            <summary>{hit.object_id} · {hit.relevance_score === null ? 'lexical / structural recall' : `${(hit.relevance_score * 100).toFixed(0)}% relevance`} · {hit.category || 'not reranked'}</summary>
            <button onClick={() => openMemory(hit)}>Open {hit.object_id}</button>
            <p>{hit.title}</p><p>{hit.short_reason}</p><small>Basis: {hit.retrieval_reasons.join(', ')}{hit.hard_relation && ` · recorded relation: ${hit.hard_relation}`}</small>
            {hit.record_status && <p>Ledger status: {hit.record_status} · relevance is not verification</p>}
            {(hit.caveats || []).map((caveat, index) => <p className="meta" key={index}>{caveat}</p>)}

            <div className="action-row">{['include', 'exclude', 'pin'].map(preference => <button key={preference} aria-pressed={memoryPreferences[hit.object_id] === preference} onClick={() => setMemoryPreferences(current => ({ ...current, [hit.object_id]: preference }))}>{preference}</button>)}</div>
            <small>Current query preference: {memoryPreferences[hit.object_id] || 'recommended'}</small>
          </details>)}
          {(related?.expansion_suggestions || []).map((suggestion, index) => <div className="proposal" key={index}>
            <strong>Retrieval expansion: {suggestion.object_id}</strong> <Badge label={suggestion.validation_status} />
            <p>{suggestion.short_reason}</p>
            {suggestion.hit && <><button onClick={() => openMemory(suggestion.hit!)}>Open suggested memory</button><button disabled={!model.trim() || rerankMemory.isPending || memoryJob.data?.status === 'running'} onClick={() => setConfirmation({ title: 'Expand Smart Recall', details: { ...llmDetails('Semantic Rerank', 'selected recalled research records with explicit expansion'), Resource: suggestion.object_id, Model: model, Reasoning: effort }, run: () => rerankMemory.mutate([suggestion.object_id]) })}>Expand & rerank ({provider === 'codex' ? 'Codex CLI' : 'model API'})</button></>}
          </div>)}
          {(related?.warnings || []).map((warning, index) => <p key={index} className="meta">{warning}</p>)}
          <small>Include / exclude / pin 仅保存当前页面查询偏好；不修改 Problem Record。</small>
        </details>
        </section>
        </ResearchOrigin.Provider>}
        {objectQueries.map((query, index) => <ErrorLine key={OBJECT_KINDS[index].kind} error={query.error} />)}
      </aside>
      <div className="resize-handle" role="separator" aria-label="Resize Research Explorer" onPointerDown={() => { dragRef.current = 'left' }} />
      <main className="panel workspace" aria-label="Main Workspace">
        <div className="retrieval-tabs" role="tablist" aria-label="Reader views">
          <button id="document-tab" role="tab" aria-selected={readerView === 'document'} aria-controls="document-view" onClick={() => setReaderView('document')}>Document</button>
          <button id="map-tab" role="tab" aria-selected={readerView === 'map'} aria-controls="map-view" onClick={() => setReaderView('map')}>Research Map</button>
        </div>
        <div id="map-view" role="tabpanel" aria-labelledby="map-tab" hidden={readerView !== 'map'}>
          {readerView === 'map' && <ResearchMap key={problemId} problemId={problemId} onOpen={openMapNode} onTask={intent => dispatchTask(intent, 'quick_action')} />}
        </div>
        <div id="document-view" role="tabpanel" aria-labelledby="document-tab" hidden={readerView !== 'document'}>
        <h2>Knowledge Reader</h2>
        {selection?.type === 'episode' && <>
          <h1>{episode.data?.episode.source_filename || selection.id}</h1>
          <div className="badges"><Badge label={selection.id} /><Badge label="archived source" /></div>
          {episode.data && <>
            <p className="meta">Imported {episode.data.episode.imported_at} · {episode.data.episode.archive_path}<br />SHA-256 {episode.data.episode.content_sha256}<br />Provenance: {episode.data.episode.provenance || 'not supplied'}</p>
            <div className="parse-summary">{Object.entries(episode.data.parse_summary).map(([kind, count]) => <Badge key={kind} label={`${count} ${CANDIDATE_LABELS[kind] || kind}`} />)}</div>
            <p>{episode.data.candidate_count} candidates · deterministic parse counts above; includes staged model proposals if present. Viewing makes no model call.</p>
            <button onClick={() => setRawView(!rawView)}>{rawView ? 'Rendered Markdown' : 'Raw source'}</button>
            {rawView ? <pre className="raw-source">{episode.data.raw_markdown}</pre> : <Markdown text={episode.data.raw_markdown} />}
          </>}
          <ErrorLine error={episode.error} />
        </>}
        {selection?.type === 'candidate' && selectedCandidate && <>
          <h1>{candidateTitle(selectedCandidate.candidate)}</h1>
          <div className="badges">
            <Badge label={`Source: ${selectedCandidate.candidate.source_reported_status || 'not reported'}`} tone="warn" />
            <Badge label={`Review: ${candidateReviewStatus(selectedCandidate)}`} />
            <Badge label={`Problem Record: ${candidateRecordStatus(selectedCandidate)}`} />
          </div>
          <p className="meta">{selectedCandidate.candidate.candidate_id} · {selectedCandidate.candidate.source_section} · lines {selectedCandidate.candidate.start_line}–{selectedCandidate.candidate.end_line}<br />Episode {selectedCandidate.candidate.episode_id} · Target {selectedCandidate.candidate.target_id || 'not resolved'}</p>
          {selectedCandidate.candidate.summary && <p><strong>Summary:</strong> {selectedCandidate.candidate.summary}</p>}
          {selectedCandidate.candidate.relation && <p>Local/source relation: {selectedCandidate.candidate.relation_wording || selectedCandidate.candidate.relation} → {selectedCandidate.candidate.target_id}</p>}
          <button onClick={() => setRawView(!rawView)}>{rawView ? 'Rendered body' : 'Raw Episode section'}</button>
          {rawView ? <pre className="raw-source">{selectedCandidate.candidate.raw_markdown || selectedCandidate.candidate.body}</pre> : <Markdown text={selectedCandidate.candidate.body} />}
          {Object.keys(selectedCandidate.candidate.source_fields).length > 0 && <details><summary>Source fields / provenance</summary><pre>{JSON.stringify(selectedCandidate.candidate.source_fields, null, 2)}</pre></details>}
        </>}
        {selection?.type === 'object' && <>
          <h1>{selectedObject.data?.title || selection.id}</h1>
          {selectedObject.data && <>
            <div className="badges"><Badge label={`${selection.kind}: ${selection.id}`} /><Badge label={`Source: ${selectedObject.data.source_reported_status || 'not separately recorded'}`} /><Badge label={`Human: ${selectedObject.data.human_review || 'not recorded'}`} /><Badge label={`Problem Record: ${selectedObject.data.status}`} tone={selectedObject.data.status === 'verified' ? 'good' : 'warn'} /></div>
            <p className="meta">Provenance: {selectedObject.data.provenance.filter(Boolean).join(' · ') || 'not recorded'}</p>
            {selectedObject.data.state && <>
              <div className="badges"><Badge label={`Research: ${selectedObject.data.state.research_state}`} /><Badge label={`Authority: ${selectedObject.data.state.authority}`} /><Badge label={`Verification: ${selectedObject.data.state.verification}`} /></div>
              {selectedObject.data.state.warnings.map(w => <p className="error" key={w}>{w}</p>)}
            </>}
            {selectedObject.data.source_episode_id && <button onClick={() => chooseEpisode(selectedObject.data!.source_episode_id!)}>Open source Episode {selectedObject.data.source_episode_id}</button>}
            {selectedObject.data.summary && <p><strong>Source summary:</strong> {selectedObject.data.summary}</p>}
            <Markdown text={selectedObject.data.body} />
            {(selection.kind === 'claim' || selection.kind === 'gap') && <>
              {stringList(selectedObject.data.metadata, 'assumptions').length > 0 && <section className="related"><h3>Assumptions</h3>{stringList(selectedObject.data.metadata, 'assumptions').map((item, index) => <p key={index}>{item}</p>)}</section>}
              {([
                ['dependencies', 'Direct dependencies', 'claim'],
                ['gaps', 'Related gaps (current and historical)', 'gap'],
                ['failed_attempts', 'Failed routes', 'failed_attempt'],
                ['counterexamples', 'Counterexamples', 'claim'],
                ['special_cases', 'Special cases', 'claim'],
                ['evidence', 'Evidence', 'evidence'],
              ] as const).map(([field, label, kind]) => {
                const records = linkedRecords(selectedObject.data!.metadata, field)
                return records.length > 0 && <section className="related" key={field}><h3>{label}</h3>{records.map(record => <button key={record.id} onClick={() => setSelection({ type: 'object', kind: record.id.startsWith('COUNTEREXAMPLE-') ? 'counterexample' : kind as ObjectKind, id: record.id })}>{record.id} · {record.statement || record.title || record.status || ''}{field === 'gaps' && ` · ${neighborState(selectedObject.data!.metadata, record.id)}`}{field === 'counterexamples' && ` · ${counterexampleRelation(selectedObject.data!.metadata, record.id)}`}</button>)}</section>
              })}
              {(['PROVES', 'REFUTES'] as const).map(role => {
                const records = linkedRecords(selectedObject.data!.metadata, 'proofs').filter(p => (p.conclusion_relation || 'PROVES') === role)
                return records.length > 0 && <section className="related" key={role}><h3>{role === 'PROVES' ? 'Proofs · PROVES' : 'Refutations · REFUTES'}</h3>{records.map(p => <button key={p.id} onClick={() => setSelection({ type: 'object', kind: 'proof', id: p.id })}>{p.id} · {p.title} · {neighborState(selectedObject.data!.metadata, p.id)}</button>)}</section>
              })}
              {['proofs', 'branches'].flatMap(field => linkedRecords(selectedObject.data!.metadata, field)).some(p => neighborState(selectedObject.data!.metadata, p.id) === 'INVALIDATED') && <section className="related"><h3>Invalidated Proofs / Routes</h3><p>Route invalidation does not refute the underlying Claim.</p>{['proofs', 'branches'].flatMap(field => linkedRecords(selectedObject.data!.metadata, field)).filter(p => neighborState(selectedObject.data!.metadata, p.id) === 'INVALIDATED').map(p => <p key={p.id}>{p.id} · {p.title || p.objective}</p>)}</section>}
              {Array.isArray(selectedObject.data.metadata.confirmed_relations) && selectedObject.data.metadata.confirmed_relations.length > 0 && <section className="related"><h3>Confirmed relations</h3>{selectedObject.data.metadata.confirmed_relations.map((item, i) => {
                const r = item as { source_id: string; relation: string; target_id: string; confirmed_by: string; model: string | null; reasoning_effort: string | null }
                return <p key={i}>{r.source_id} {r.relation} {r.target_id} · confirmed: {r.confirmed_by}{r.confirmed_by === 'model' ? ` · ${r.model} · ${r.reasoning_effort}` : ''}</p>
              })}</section>}
              {linkedRecords(selectedObject.data.metadata, 'branches').length > 0 && <section className="related"><h3>Related research branches</h3>{linkedRecords(selectedObject.data.metadata, 'branches').map(branch => <p key={branch.id}>{branch.id} · {branch.objective || branch.title || ''}</p>)}</section>}
              {stringList(selectedObject.data.metadata, 'revisions').length > 0 && <section className="related"><h3>Revisions</h3>{stringList(selectedObject.data.metadata, 'revisions').map((item, index) => <p key={index}>{item}</p>)}</section>}
              {Array.isArray(selectedObject.data.metadata.source_episodes) && selectedObject.data.metadata.source_episodes.length > 0 && <section className="related"><h3>Source Episodes</h3>{selectedObject.data.metadata.source_episodes.map((item, index) => {
                const source = item as { episode_id?: string; source_filename?: string }
                return source.episode_id && <button key={index} onClick={() => chooseEpisode(source.episode_id!)}>{source.episode_id} · {source.source_filename}</button>
              })}</section>}
            </>}
            {selection.kind === 'proof' && <section className="related"><h3>Proof record</h3><p>Conclusion role: {String(selectedObject.data.metadata.conclusion_relation || 'PROVES')}</p>{selectedObject.data.metadata.conclusion_relation === 'REFUTES' && <p>This proof refutes its target; it does not support the target as true.</p>}<p>Targets: {stringList(selectedObject.data.metadata, 'claim_links').join(', ') || 'not linked'}</p><p>Gaps: {stringList(selectedObject.data.metadata, 'gaps').join('; ') || 'none recorded'}</p><p>Full body path: {String(selectedObject.data.metadata.body_path || 'not materialized')}</p></section>}
            {selection.kind === 'counterexample' && <section className="related"><h3>Counterexample record</h3><p>Target: {String(selectedObject.data.metadata.target_id || '')}</p><p>{counterexampleRelation(selectedObject.data.metadata, selection.id)}</p><p>REFUTES attacks the statement itself. INVALIDATES attacks a proof/route; underlying claim is not thereby refuted.</p><p>Object acceptance and relation acceptance are independent.</p></section>}
            <details><summary>Related records / metadata</summary><pre>{JSON.stringify(selectedObject.data.metadata, null, 2)}</pre></details>
          </>}
          <ErrorLine error={selectedObject.error} />
        </>}
        {selection?.type === 'memory' && <>
          <h1>{memoryObject.data?.title || selection.id}</h1>
          <p className="meta">{selection.artifactType} · {selection.id} · Problem {problemId}</p>
          {memoryObject.data && <Markdown text={memoryObject.data.text} />}
          <ErrorLine error={memoryObject.error} />
        </>}
        {selection?.type === 'resource' && <ResourceReader key={`${problemId}-${selection.id}`} problemId={problemId} file={selection.file} digestView={digestView || ['DIGEST_SOURCE', 'OPEN_SOURCE_DIGEST'].includes(activeIntent?.intent || '')} digestId={digestId} onDigestView={value => { setDigestView(value); if (!value && activeIntent?.intent === 'OPEN_SOURCE_DIGEST') setActiveIntent(null); if (!value && activeIntent?.intent === 'DIGEST_SOURCE') setActiveIntent(null) }} onDigestSelect={setDigestId} onTask={intent => dispatchTask(intent, origin)} />}
        {!selection && <p>选择左栏 Research Files / Research Objects 或右栏 Proposal 开始研究。</p>}
        </div>
      </main>
      <div className="resize-handle" role="separator" aria-label="Resize Review Panel" onPointerDown={() => { dragRef.current = 'right' }} />
      <aside className="panel review" aria-label="Research Actions">
        <ResearchOrigin.Provider value={origin}>
        <ResearchAssistant problemId={problemId} targetId={selection?.type === 'object' ? selection.id : null} onTask={dispatchTask} onOpenEpisode={chooseEpisode} onProblem={chooseProblem}>
        {activeIntent?.intent === 'DIGEST_SOURCE' && selection?.type === 'resource' && <SourceDigestControl key={`${problemId}-${selection.id}`} problemId={problemId} sourceId={selection.id} onStarted={id => { setDigestId(id); setDigestView(true) }} />}
        {selection?.type === 'object' && supportsCritique(selection.kind) && activeIntent?.intent !== 'CRITIQUE_RESEARCH_RESULT' && <button onClick={() => dispatchTask(taskAction('CRITIQUE_RESEARCH_RESULT', selection.id), 'quick_action')}>Critique this result</button>}
        {activeIntent?.intent === 'CRITIQUE_RESEARCH_RESULT' && (activeIntent.target_id || selection?.type === 'object' && selection.id) && <CritiquePanel key={`${problemId}-${activeIntent.target_id || selection?.id}`} problemId={problemId} targetId={activeIntent.target_id || selection!.id} onTask={intent => dispatchTask(intent, origin)} onOpen={(kind, id) => { setReaderView('document'); setSelection({ type: 'object', kind, id }); setRawView(false) }} />}
        {activeIntent?.intent === 'CREATE_PROBLEM' && <NewProblemTask problemId={problemId} onCreated={() => { void queryClient.invalidateQueries({ queryKey: ['problems'] }) }}
          onOpen={result => { chooseProblem(result.problem_id); setSelection({ type: 'object', kind: result.target_type === 'Gap' ? 'gap' : 'claim', id: result.target_id }) }}
          onAddSource={result => { chooseProblem(result.problem_id); setActiveIntent(taskAction('ADD_SOURCE', result.target_id)) }}
          onResearch={result => { chooseProblem(result.problem_id); setSelection({ type: 'object', kind: result.target_type === 'Gap' ? 'gap' : 'claim', id: result.target_id }); setActiveIntent(taskAction('CONTINUE_RESEARCH', result.target_id)) }} />}
        {activeIntent?.intent === 'ADD_SOURCE' && <AddSourceTask key={problemId} problemId={problemId} onSaved={async () => {
          for (const key of ['sources', 'search', 'navigator-files', 'related-memory']) void queryClient.invalidateQueries({ queryKey: [key, problemId] })
          await sources.refetch()
        }} onTask={intent => { if (currentProblem.current === problemId) dispatchTask(intent, origin) }} onImported={result => {
          if (currentProblem.current !== problemId) return
          chooseEpisode(result.episode.episode_id); setNotice(`已导入 ${result.episode.episode_id} · ${result.candidate_count} Proposals`)
          for (const key of ['episodes', 'episode', 'candidates', 'objects', 'object', 'agent-state', 'research-portfolio', 'related-memory']) void queryClient.invalidateQueries({ queryKey: [key, problemId] })
          void queryClient.invalidateQueries({ queryKey: ['research-portfolio'] }); setContextEpoch(v => v + 1)
        }} />}
        {activeIntent && ['SYSTEM_HEALTH', 'EXPORT_WORKSPACE_SNAPSHOT', 'VERIFY_SNAPSHOT', 'EXPORT_RESEARCH_HANDOFF'].includes(activeIntent.intent) && <MaintenanceTask key={`${problemId}-${activeIntent.intent}`} intent={activeIntent} problemId={problemId} targets={objectQueries.flatMap(query => query.data || []).filter(object => object.kind === 'claim' || object.kind === 'gap')} />}
        {!activeIntent && <p className="meta">选择一个 Quick Action，或输入支持的任务请求。</p>}
        {activeIntent && <div className="current-task"><p>{activeIntent.intent}</p><button onClick={() => { setActiveIntent(null); setConfirmation(null) }}>关闭任务卡</button></div>}
        {activeIntent?.intent === 'IMPORT_DECOMPOSE_EPISODE' && <ImportEpisodeTask key={problemId} problemId={problemId} onImported={result => {
          if (currentProblem.current !== problemId) return
          chooseEpisode(result.episode.episode_id); setNotice(`已导入 ${result.episode.episode_id} · ${result.candidate_count} Proposals`)
          for (const key of ['episodes', 'episode', 'candidates', 'objects', 'object', 'agent-state', 'research-portfolio', 'related-memory']) void queryClient.invalidateQueries({ queryKey: [key, problemId] })
          void queryClient.invalidateQueries({ queryKey: ['research-portfolio'] }); setContextEpoch(v => v + 1)
        }} onScout={() => dispatchTask(taskAction('LOGICAL_RELATIONS'), origin)} />}
        {activeIntent?.intent === 'RESEARCH_STATUS' && <ResearchStatusTask problemId={problemId} targetId={activeIntent.target_id || (selection?.type === 'object' ? selection.id : null)} targets={objectQueries.flatMap(query => query.data || []).filter(o => o.kind === 'claim' || o.kind === 'gap')} episodes={episodes.data || []} onOpenEpisode={chooseEpisode} />}
        {activeIntent?.intent === 'FIND_RELATED_RESEARCH' && <p>已打开左栏 Recall；选择真实召回结果在中栏阅读。</p>}
        {activeIntent && ['CONTINUE_RESEARCH', 'STOP_RESEARCH', 'RESUME_RESEARCH'].includes(activeIntent.intent) && <>
        <ResearchAgentPanel key={problemId} intent={activeIntent || undefined} problemId={problemId} selectedTarget={activeIntent?.target_id || (selection?.type === 'object' && ['claim', 'gap'].includes(selection.kind) ? selection.id : null)} onChanged={() => {
          setContextEpoch(current => current + 1)
          for (const key of ['episodes', 'candidates', 'related-memory', 'hard']) void queryClient.invalidateQueries({ queryKey: [key] })
        }} />
        </>}

        {activeIntent?.intent === 'HUMAN_REVIEW' && <>
        <section id="candidate-review" className="task-card" aria-labelledby="candidate-review-heading">
        <h2 id="candidate-review-heading" className="review-section-heading">Proposal Review</h2>
        <p className="meta">{review.isPending || batchReview.isPending ? 'REVIEWING' : selectedCandidate ? 'REVIEW_ACTION' : episodeId ? 'SELECT_CANDIDATE' : 'SELECT_SCOPE'}</p>
        <div className="action-row"><button onClick={() => { setReviewScope('episode'); if (episodes.data?.[0]) chooseEpisode(episodes.data[0].episode.episode_id) }}>最新 Episode</button><button onClick={() => setReviewScope('pending')}>全部 Pending</button></div>
        <label className="field">Episode scope<select aria-label="Review Episode scope" value={episodeId || ''} onChange={e => { setReviewScope('episode'); chooseEpisode(e.target.value) }}><option value="">Choose Episode</option>{episodes.data?.map(row => <option key={row.episode.episode_id} value={row.episode.episode_id}>{row.episode.source_filename} · {row.pending} pending</option>)}</select></label>
        {reviewScope === 'pending' && pendingQueries.map((query, index) => <ErrorLine key={index} error={query.error} />)}
        <p className="meta">{episodeId || 'Select an Episode'} · {candidates.data?.length || 0} candidates</p>
        <label className="field">Type
          <select aria-label="Proposal type" value={candidateFilter} onChange={e => setCandidateFilter(e.target.value)}>
            <option value="all">All</option>
            {Object.entries(CANDIDATE_LABELS).map(([kind, label]) => <option value={kind} key={kind}>{label}</option>)}
          </select>
        </label>
        <div className="candidate-list">
          {visibleProposals.map(row => <div className="candidate-entry" key={row.candidate.candidate_id}>
            <input type="checkbox" aria-label={`Select ${candidateTitle(row.candidate)}`}
              disabled={row.candidate.kind === 'relation'}
              checked={selectedCandidateIds.includes(row.candidate.candidate_id)}
              onChange={event => setSelectedCandidateIds(current => event.target.checked
                ? [...current, row.candidate.candidate_id]
                : current.filter(id => id !== row.candidate.candidate_id))} />
            <button
            className={`candidate-card ${selection?.type === 'candidate' && selection.id === row.candidate.candidate_id ? 'selected' : ''}`}
            onClick={() => chooseCandidate(row)}>
            <strong>{candidateTitle(row.candidate)}</strong> <small>{CANDIDATE_LABELS[row.candidate.kind] || row.candidate.kind}</small>
            <small>{row.candidate.candidate_id} · local {row.candidate.local_id || 'none'} · target {row.candidate.target_id || 'none'}</small>
            <span>{row.candidate.title}</span>
            {row.candidate.relation && <small>Source relation: {row.candidate.relation_wording || row.candidate.relation}</small>}
            <small>Source: {row.candidate.source_reported_status || 'not reported'} · Review: {candidateReviewStatus(row)}</small>
            <small>Episode {row.candidate.episode_id} · lines {row.candidate.start_line}–{row.candidate.end_line}</small>
            </button>
          </div>)}
        </div>
        <div className="action-row">
          {(['accept', 'reject', 'defer'] as const).map(decision => <button key={decision}
            disabled={!selectedCandidateIds.length || batchReview.isPending}
            onClick={() => requestBatch(decision)}>Batch {decision}</button>)}
        </div>
        <ErrorLine error={batchReview.error} />
        {selectedCandidate && <section className="review-actions">
          <h3>{candidateTitle(selectedCandidate.candidate)}</h3>
          {selectedCandidate.state && <>
            <p>{selectedCandidate.state.authority} · {selectedCandidate.state.verification} · {selectedCandidate.state.research_state}</p>
            {selectedCandidate.state.warnings.map(w => <p className="error" key={w}>{w}</p>)}
          </>}
          <p>Local ID: {selectedCandidate.candidate.local_id || 'none'}<br />Target: {selectedCandidate.candidate.target_id || 'unresolved'}<br />Relation: {selectedCandidate.candidate.relation || selectedCandidate.candidate.relation_wording || 'none'}</p>
          <div className="badges"><Badge label={`Source: ${selectedCandidate.candidate.source_reported_status || 'not reported'}`} tone="warn" /><Badge label={`Human: ${candidateReviewStatus(selectedCandidate)}`} /><Badge label={`Problem Record: ${candidateRecordStatus(selectedCandidate)}`} /></div>
          {selectedCandidate.candidate.source_fields.origin === 'source_digest' && <>
            <p>Source Digest: {selectedCandidate.candidate.source_fields.digest_id} · {selectedCandidate.candidate.source_fields.proposal_id}</p>
            <p>Source: {selectedCandidate.candidate.source_fields.source_filename} · {selectedCandidate.candidate.source_fields.source_id} · {selectedCandidate.candidate.source_fields.locator}</p>
            <blockquote>{selectedCandidate.candidate.source_fields.supporting_span}</blockquote>
            <p>Extraction confidence: {selectedCandidate.candidate.source_fields.confidence} · {selectedCandidate.candidate.source_fields.relation_to_problem}</p>
            {selectedCandidate.candidate.source_fields.confidence === 'LOW' && <p>Inspect and Edit before acceptance.</p>}
            {selectedCandidate.candidate.source_fields.citation_kind === 'SOURCE_CITES_EXTERNAL' && <p>Reported by this source; original proof not inspected.</p>}
            <p>Possible overlaps: {selectedCandidate.candidate.source_fields.possible_duplicate_ids}</p>
            <button onClick={() => dispatchTask(taskAction('OPEN_SOURCE_DIGEST', selectedCandidate.candidate.source_fields.source_id), origin)}>Open Digest / Source</button>
          </>}
          {selectedCandidate.review?.relation && <p>Human-confirmed relation: {selectedCandidate.review.relation} → {selectedCandidate.review.target_id}</p>}
          {selectedCandidate.review?.decision !== 'accept' && selectedCandidate.review?.decision !== 'reject' && <div className="action-row">
            <button disabled={review.isPending || selectedCandidate.candidate.source_fields.origin === 'source_digest' && selectedCandidate.candidate.source_fields.confidence === 'LOW'} onClick={() => requestReview(selectedCandidate.candidate.candidate_id, 'accept')}>Accept</button>
            <button disabled={review.isPending} onClick={() => requestReview(selectedCandidate.candidate.candidate_id, 'reject')}>Reject</button>
            <button disabled={review.isPending} onClick={() => requestReview(selectedCandidate.candidate.candidate_id, 'defer')}>Defer</button>
            <button onClick={() => setEditOpen(!editOpen)}>Edit</button>
          </div>}
          {editOpen && <div className="edit-form">
            <label>Full body<textarea value={editBody} onChange={e => setEditBody(e.target.value)} /></label>
            <label>Summary<input value={editSummary} onChange={e => setEditSummary(e.target.value)} /></label>
            <label>Target ID<input value={editTarget} onChange={e => setEditTarget(e.target.value)} /></label>
            <button disabled={review.isPending} onClick={() => requestReview(selectedCandidate.candidate.candidate_id, 'accept', {
              body: editBody, summary: editSummary, target_id: editTarget || null,
            })}>Accept edited candidate</button>
          </div>}
          <ErrorLine error={review.error} />
          <small>Human Accept 写入 Problem Record；不代表数学证明已验证。</small>
        </section>}
        </section>
        </>}
        {activeIntent?.intent === 'LOGICAL_RELATIONS' && <>
        <LogicalRelationsPanel problemId={problemId} episodeId={episodeId || null} rows={candidates.data || []} selectedCandidateIds={selectedCandidateIds} onChanged={() => { setMemoryJobId(null); void queryClient.invalidateQueries({ queryKey: ['candidates'] }); void queryClient.invalidateQueries({ queryKey: ['memory-object'] }); void queryClient.invalidateQueries({ queryKey: ['objects'] }); void queryClient.invalidateQueries({ queryKey: ['object'] }); void queryClient.invalidateQueries({ queryKey: ['related-memory'] }); setContextEpoch(v => v + 1) }} />

        </>}
        <ActionConfirmation value={confirmation} onClose={() => setConfirmation(null)} />
        </ResearchAssistant>
        </ResearchOrigin.Provider>
      </aside>
    </div>
  </div>
}
