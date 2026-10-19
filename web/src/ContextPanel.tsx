import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, type QueryPurpose, type RelatedResearch } from './api'

export function ContextPanel({ problemId, targetId, relatedMemory, queryText = '' }: { problemId: string; targetId: string; relatedMemory?: RelatedResearch; queryText?: string }) {
  const [purpose, setPurpose] = useState<QueryPurpose>('CONTINUE_RESEARCH')
  const [budget, setBudget] = useState(8000)
  const [thread, setThread] = useState('')
  const [provisional, setProvisional] = useState(true)
  const [query, setQuery] = useState(queryText)
  const context = useMutation({ mutationFn: () => api.buildContext(problemId, targetId, purpose, budget, thread, provisional, relatedMemory, query) })
  const bundle = context.data
  function download() {
    if (!bundle) return
    const url = URL.createObjectURL(new Blob([bundle.markdown], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${targetId}-research-context.md`
    link.click()
    URL.revokeObjectURL(url)
  }
  return <section className="related" aria-label="Build Research Context">
    <h3>Build Research Context</h3>
    <p className="meta">Context build · Uses LLM: No</p>
    <p>生成预算内的上下文。待审核结果可作为 working result；Accept 始终由 Human Review 决定。</p>
    <label className="field">Context query<input aria-label="Context query" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <label className="field">Purpose<select aria-label="Context purpose" value={purpose} onChange={e => setPurpose(e.target.value as QueryPurpose)}>
      {(['CONTINUE_RESEARCH', 'RECOVER_PROOF', 'TRACE_HISTORY', 'FIND_FAILURES'] as const).map(value => <option key={value}>{value}</option>)}
    </select></label>
    <label className="field">Token budget<input aria-label="Context token budget" type="number" min={128} max={200000} value={budget} onChange={e => setBudget(Number(e.target.value))} /></label>
    <label className="field">Thread (optional)<input aria-label="Context thread" maxLength={128} value={thread} onChange={e => setThread(e.target.value)} /></label>
    <label><input type="checkbox" checked={provisional} onChange={e => setProvisional(e.target.checked)} /> Include provisional working results</label>
    <button disabled={context.isPending} onClick={() => context.mutate()}>Build Research Context</button>
    {context.error && <p role="alert" className="error">{context.error.message}</p>}
    {bundle && <>
      <p>Estimated tokens {bundle.token_estimate}/{bundle.token_budget} · {bundle.complete ? 'Mandatory context complete' : 'Incomplete mandatory context'}</p>
      {bundle.warnings.map(w => <p className="error" key={w}>{w}</p>)}
      <p>Canonical: {bundle.items.filter(i => i.state.authority === 'CANONICAL').map(i => i.object_id).join(', ') || 'none'}</p>
      <p>Provisional: {bundle.items.filter(i => i.state.authority === 'PROVISIONAL').map(i => i.object_id).join(', ') || 'none'}</p>
      <p>History / rejected: {bundle.items.filter(i => i.state.authority === 'REJECTED/HISTORICAL' || i.section === 'history' || i.section === 'failures').map(i => i.object_id).join(', ') || 'none'}</p>
      <button onClick={download}>Download context</button>
      <details><summary>Context text</summary><pre>{bundle.markdown}</pre></details>
      <details><summary>Budget / exclusions / version</summary><pre>{JSON.stringify({ sections: bundle.tokens_per_section, excluded: bundle.excluded, source_version: bundle.source_version }, null, 2)}</pre></details>
    </>}
  </section>
}
