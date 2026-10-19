import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, type RecallFile, type RelatedResearch } from './api'
import { ContextPanel } from './ContextPanel'
import { useResearchActions } from './researchActions'

export function RecallFiles({ files, problemId, onOpen }: {
  files: RecallFile[]; problemId: string; onOpen: (file: RecallFile) => void
}) {
  return <div>{files.map(file => <details key={`${file.problem_id}:${file.kind}:${file.artifact_id}`}>
    <summary>{file.artifact_id} · {file.title}</summary>
    <p>{file.authority} · {file.state.research_state} · {file.state.verification}</p>
    {file.conclusion_relation && <p>Proof role: {file.conclusion_relation}{file.conclusion_relation === 'REFUTES' && ' · does not support target as true'}</p>}
    <p>Reason: {file.why_relevant.join(', ')}</p>
    <p>Relation: {file.relation_to_target.join('; ') || 'no accepted relation recorded'}</p>
    <p>Scope: {file.problem_scope.join(', ') || 'global source'}</p>
    <p className="meta">{file.path || 'Navigation record; no separate original file'}</p>
    <button onClick={() => onOpen(file)}>Inspect {file.artifact_id}</button>
    {file.path && <a href={api.originalFileUrl(problemId, file)} download>Download original {file.artifact_id}</a>}
    <p className="meta">Provenance: {file.provenance.join('; ')}</p>
    {[...file.warnings, ...file.state.warnings].map((w, i) => <p className="meta" key={i}>{w}</p>)}
  </details>)}</div>
}

export function RecallPanel({ problemId, selectedTarget, contextEpoch, relatedMemory, onOpen, initialQuery = '', recallRequest = 0 }: {
  problemId: string; selectedTarget: string | null; contextEpoch: number;
  relatedMemory?: RelatedResearch; onOpen: (file: RecallFile) => void; initialQuery?: string; recallRequest?: number
}) {
  const actions = useResearchActions(problemId)
  const [target, setTarget] = useState(selectedTarget || '')
  const [query, setQuery] = useState(initialQuery)
  const [cross, setCross] = useState(false)
  const [thread, setThread] = useState('')
  const [limit, setLimit] = useState(50)
  const inputKey = JSON.stringify([problemId, selectedTarget, target, query, cross, thread, limit, contextEpoch])
  const files = useMutation({ mutationFn: async (override?: { target: string; query: string; key: string }) => ({ key: override?.key || inputKey, result: await actions.findRelated(override?.target ?? target, override?.query ?? query, cross, thread, limit) }) })
  const history = useMutation({ mutationFn: async () => ({ key: inputKey, result: await actions.checkHistory(target, query, cross, thread, limit) }) })
  const fileResult = files.data?.key === inputKey ? files.data.result : undefined
  const historyResult = history.data?.key === inputKey ? history.data.result : undefined
  useEffect(() => { setTarget(selectedTarget || ''); setQuery(initialQuery); setCross(false); setThread('') }, [problemId, selectedTarget, initialQuery])
  useEffect(() => { files.reset(); history.reset() }, [problemId, selectedTarget, target, query, cross, thread, limit, contextEpoch])
  useEffect(() => {
    if (recallRequest && (selectedTarget || initialQuery)) {
      const key = JSON.stringify([problemId, selectedTarget, selectedTarget || '', initialQuery, false, '', 50, contextEpoch])
      files.mutate({ target: selectedTarget || '', query: initialQuery, key })
    }
  }, [recallRequest])
  const disabled = !target.trim() && !query.trim()
  const supporting = historyResult ? [
    ...historyResult.canonical_matches, ...historyResult.open_matches, ...historyResult.failed_routes,
    ...historyResult.counterexamples, ...historyResult.proofs, ...historyResult.source_files,
  ].filter((file, index, all) => all.findIndex(f => f.artifact_id === file.artifact_id && f.problem_id === file.problem_id) === index) : []
  return <>
    <p className="meta">Recall V2 · Uses LLM: No · 查找已有研究；召回与历史检查只读。</p>
    <label className="field">Target ID<input aria-label="Recall target" value={target} onChange={e => setTarget(e.target.value)} placeholder="留空以自由数学问题查询" /></label>
    <label className="field">Mathematical query<input aria-label="Recall query" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <label><input type="checkbox" checked={cross} onChange={e => setCross(e.target.checked)} /> Search across Problems</label>
    <label className="field">Thread hint<input aria-label="Recall thread" maxLength={128} value={thread} onChange={e => setThread(e.target.value)} /></label>
    <label className="field">File limit<input aria-label="Recall file limit" type="number" min={1} max={100} value={limit} onChange={e => setLimit(Number(e.target.value))} /></label>
    <div className="action-row">
      <button disabled={disabled || files.isPending} onClick={() => files.mutate(undefined)}>Find Related Files</button>
      <button disabled={disabled || history.isPending} onClick={() => history.mutate()}>Check Prior Research</button>
    </div>
    {(files.error || history.error) && <p role="alert" className="error">{(files.error || history.error)?.message}</p>}
    {fileResult && <section aria-label="Related files"><h3>Original files</h3>
      <RecallFiles files={fileResult.files} problemId={problemId} onOpen={onOpen} />
      {!fileResult.files.length && <p>No matching files.</p>}
    </section>}
    {historyResult && <section aria-label="Prior research"><h3>{historyResult.classification}</h3>
      <p>{historyResult.basis === 'HARD_STATE' ? 'Hard state · accepted current mathematical memory' : historyResult.basis === 'SOFT_OVERLAP' ? 'Soft overlap · similarity only' : 'No match in this scope'}</p>
      {historyResult.warnings.map((w, i) => <p className="meta" key={i}>{w}</p>)}
      <h4>{historyResult.basis === 'HARD_STATE' ? 'Supporting objects / original files' : 'Retrieved objects / original files (similarity only)'}</h4><RecallFiles files={supporting} problemId={problemId} onOpen={onOpen} />
      <h4>Soft overlap</h4><RecallFiles files={historyResult.soft_overlaps} problemId={problemId} onOpen={onOpen} />
    </section>}
    <details><summary>Advanced: Build Research Context</summary>
    {target.startsWith('CLAIM-') ? <ContextPanel key={`${problemId}:${target}:${query}:${contextEpoch}`} problemId={problemId} targetId={target} queryText={query} relatedMemory={target === selectedTarget ? relatedMemory : undefined} />
      : <p>Build Research Context：选择正式 Claim / Gap 目标后设置预算与 purpose。</p>}
    </details>
  </>
}
