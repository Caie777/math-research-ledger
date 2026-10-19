import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type DigestSettings, type ResearchIntent, type SourceLocator, type SourceProposal } from './api'
import { ActionConfirmation, llmDetails, type Confirmation } from './ActionConfirmation'
import { taskAction, useResearchActions } from './researchActions'

export function locatorLabel(value: SourceLocator | null): string {
  if (!value) return 'Location missing'
  const range = value.page ? `page ${value.page}${value.page_end && value.page_end !== value.page ? `–${value.page_end}` : ''}` : `lines ${value.line_start}–${value.line_end}`
  return `${range}${value.heading ? ` · ${value.heading}` : ''}`
}

/** Read-only preflight on entry. Only the confirmation callback starts a model. */
export function SourceDigestControl({ problemId, sourceId, onStarted }: {
  problemId: string; sourceId: string; onStarted: (id: string) => void
}) {
  const actions = useResearchActions(problemId), client = useQueryClient()
  const preflight = useQuery({ queryKey: ['digest-preflight', problemId, sourceId], queryFn: () => api.digestPreflight(problemId, sourceId) })
  const history = useQuery({ queryKey: ['source-digests', problemId, sourceId], queryFn: () => api.sourceDigests(problemId, sourceId),
    refetchInterval: query => query.state.error ? false : query.state.data?.some(run => run.status === 'RUNNING') ? 1000 : false })
  const running = history.data?.some(run => run.status === 'RUNNING')
  const [settings, setSettings] = useState<DigestSettings | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const confirmedSignature = useRef('')
  const signature = JSON.stringify([sourceId, settings, preflight.data?.context_sha256])
  useEffect(() => { if (preflight.data) setSettings(preflight.data.settings) }, [preflight.data?.settings])
  useEffect(() => { if (settings && confirmedSignature.current !== signature) setConfirmation(null) }, [signature, settings])
  const start = useMutation({ mutationFn: (request: { settings: DigestSettings; sha: string }) => actions.startSourceDigest(sourceId, request.settings, request.sha),
    onSuccess: run => { client.setQueryData(['source-digest', problemId, run.digest_id], run); client.setQueryData(['source-digests', problemId, sourceId], (previous: typeof history.data) => [run, ...(previous || []).filter(item => item.digest_id !== run.digest_id)]); void client.invalidateQueries({ queryKey: ['source-digests', problemId, sourceId] }); onStarted(run.digest_id) },
    onError: () => { void preflight.refetch() } })
  function confirm() {
    if (!settings || !preflight.data || running || start.isPending || history.isPending || history.error) return
    const request = { settings: { ...settings }, sha: preflight.data.context_sha256 }
    confirmedSignature.current = signature
    setConfirmation({ title: 'Confirm Source Digest', details: {
      ...llmDetails('Source Digest', 'selected source and bounded problem context'),
      Source: preflight.data.context.source_filename, Problem: problemId, Mode: 'Source Digest',
      Model: settings.model, Provider: settings.provider, Reasoning: settings.reasoning_effort,
      Output: 'Advisory proposals only', Authority: 'Requires Human Review',
    }, run: () => start.mutate(request) })
  }
  return <section className="task-card" aria-label="Digest Source settings"><h2>Digest Source</h2>
    <p>Source extraction produces Proposals, not accepted knowledge.</p>
    {preflight.data && <p className="meta">{preflight.data.context.source_filename} · {preflight.data.context.total_units} {preflight.data.context.unit}s · at most 4 extraction chunks + 1 structure call</p>}
    {settings && <details><summary>Digest model settings</summary>
      <label className="field">Provider<select aria-label="Digest provider" value={settings.provider} onChange={e => setSettings({ ...settings, provider: e.target.value as DigestSettings['provider'], reasoning_effort: ['codex', 'openai'].includes(e.target.value) ? 'high' : null })}>{['codex', 'openai', 'anthropic', 'ollama', 'mistral'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="field">Model<input aria-label="Digest model" value={settings.model} onChange={e => setSettings({ ...settings, model: e.target.value })} /></label>
      <label className="field">Reasoning<select aria-label="Digest reasoning" value={settings.reasoning_effort || ''} onChange={e => setSettings({ ...settings, reasoning_effort: (e.target.value || null) as DigestSettings['reasoning_effort'] })}><option value="">Provider default</option>{(['codex', 'openai'].includes(settings.provider) ? ['low', 'medium', 'high', ...(settings.provider === 'codex' ? ['xhigh', 'max'] : [])] : []).map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="field">Extraction chunks<input aria-label="Digest max chunks" type="number" min={1} max={4} value={settings.max_chunks} onChange={e => setSettings({ ...settings, max_chunks: Number(e.target.value) })} /></label>
    </details>}
    <button disabled={!settings?.model.trim() || !preflight.data || start.isPending || !!running || history.isPending || !!history.error || !settings || settings.max_chunks < 1 || settings.max_chunks > 4} onClick={confirm}>Digest Source</button>
    <ActionConfirmation value={confirmation} onClose={() => setConfirmation(null)} />
    {start.isPending && <p role="status">Starting Source Digest…</p>}
    {running && !history.error && <p role="status">RUNNING · Source Digest</p>}
    {(preflight.error || history.error || start.error) && <p role="alert">{String(preflight.error || history.error || start.error)}</p>}
  </section>
}

function ConfirmLocation({ problemId, proposal, onConfirmed }: { problemId: string; proposal: SourceProposal; onConfirmed: () => void }) {
  const actions = useResearchActions(problemId)
  const [page, setPage] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState(''), [heading, setHeading] = useState('')
  const [span, setSpan] = useState(proposal.supporting_span)
  const mutation = useMutation({ mutationFn: () => actions.confirmSourceLocation(proposal.digest_id, proposal.proposal_id,
    { page: page ? Number(page) : null, line_start: start ? Number(start) : null, line_end: end ? Number(end) : null, heading: heading || null }, span), onSuccess: onConfirmed })
  return <details><summary>Confirm source location before review</summary><p>Inspect the Source, then supply an exact page or line range and a short matching excerpt.</p>
    <label className="field">PDF page<input aria-label="Source PDF page" type="number" min={1} value={page} onChange={e => setPage(e.target.value)} /></label>
    <label className="field">Line start<input aria-label="Source line start" type="number" min={1} value={start} onChange={e => setStart(e.target.value)} /></label>
    <label className="field">Line end<input aria-label="Source line end" type="number" min={1} value={end} onChange={e => setEnd(e.target.value)} /></label>
    <label className="field">Heading<input value={heading} onChange={e => setHeading(e.target.value)} maxLength={200} /></label>
    <label className="field">Supporting span<textarea aria-label="Confirm supporting span" maxLength={350} value={span} onChange={e => setSpan(e.target.value)} /></label>
    <button disabled={mutation.isPending || !span.trim() || !(page || start && end)} onClick={() => mutation.mutate()}>I inspected this source location</button>
    {mutation.error && <p role="alert">{String(mutation.error)}</p>}
  </details>
}

export function SourceDigestReader({ problemId, sourceId, digestId, onSelect, onTask, onLocate }: {
  problemId: string; sourceId: string; digestId: string | null; onSelect: (id: string) => void
  onTask: (intent: ResearchIntent) => void; onLocate: (value: SourceLocator | null) => void
}) {
  const client = useQueryClient()
  const history = useQuery({ queryKey: ['source-digests', problemId, sourceId], queryFn: () => api.sourceDigests(problemId, sourceId) })
  const selectedId = digestId || history.data?.[0]?.digest_id || null
  const poll = useQuery({ queryKey: ['source-digest', problemId, selectedId], queryFn: () => api.sourceDigest(problemId, selectedId!), enabled: !!selectedId,
    refetchInterval: query => !query.state.error && query.state.data?.status === 'RUNNING' ? 1000 : false })
  const run = poll.data || history.data?.find(item => item.digest_id === selectedId)
  const digest = run?.digest
  const ordered = [...(digest?.proposals || [])].sort((a, b) => Number(['BACKGROUND', 'POSSIBLE'].includes(a.relation_to_problem)) - Number(['BACKGROUND', 'POSSIBLE'].includes(b.relation_to_problem)))
  return <section aria-label="Source Digest Reader"><h2>Source Digest</h2>
    <p>Advisory source understanding · Requires Human Review · not theorem verification.</p>
    <h3>Digests / Pending Proposals</h3>
    {history.data?.length === 0 && <p>No digests yet. Use Digest Source to start an explicitly confirmed run.</p>}
    {(history.data || []).map(item => <button key={item.digest_id} aria-pressed={item.digest_id === selectedId} onClick={() => onSelect(item.digest_id)}>{item.digest_id} · {item.status}</button>)}
    {(history.error || poll.error) && <p role="alert">{String(history.error || poll.error)}</p>}
    {run?.status === 'RUNNING' && !poll.error && <p role="status">RUNNING · Source Digest</p>}
    {run?.status === 'FAILED' && <p role="alert">FAILED · {run.error}</p>}
    {run?.source_changed && <p role="alert">Source changed since this digest. Review is blocked; no automatic re-digest.</p>}
    {digest && <>
      <p className="meta">{digest.digest_id} · {digest.source_filename} · {digest.model} · {digest.reasoning_effort || 'provider default'} · {digest.created_at}</p>
      <p className="meta">Source SHA-256: {digest.source_sha256}</p>
      <h3>{digest.coverage_complete ? 'Complete source coverage' : 'Partial digest'}</h3>
      <p>Processed: {digest.processed_ranges.map(locatorLabel).join('; ') || 'none'}</p>
      <p>Omitted / partially read: {digest.omitted_ranges.map(locatorLabel).join('; ') || 'none'}</p>
      <h3>Summary</h3><p>{digest.summary}</p>
      {(['notation', 'definitions', 'results', 'methods', 'assumptions', 'limitations'] as const).map(key => <div key={key}><h3>{key}</h3><ul>{digest[key].map((value, i) => <li key={i}>{value}</li>)}</ul></div>)}
      <h3>Research Proposals</h3><p className="meta">{ordered.filter(p => !p.review_decision && p.provenance_status === 'VALID').length} pending · {ordered.filter(p => p.review_decision === 'accept').length} accepted · {ordered.filter(p => p.review_decision === 'reject').length} rejected</p>
      {ordered.map(proposal => <article className="critique-issue" key={proposal.proposal_id}>
        <h4>[{proposal.proposal_type}] {proposal.title}</h4><p>{proposal.statement}</p>
        <p className="meta">{proposal.proposal_id} · {proposal.relation_to_problem} · Extraction confidence: {proposal.confidence} · {proposal.provenance_status}</p>
        {proposal.relation && <p>Relation candidate: {proposal.source_candidate_id} → {proposal.relation} → {proposal.target_id} · requires Human Relation Review</p>}
        {proposal.confidence === 'LOW' && <p>LOW extraction confidence requires Edit before Human Accept.</p>}
        <p>{proposal.source_filename} · {proposal.source_id} · {locatorLabel(proposal.locator)}</p>
        <blockquote>{proposal.supporting_span || 'Supporting span missing'}</blockquote>
        {proposal.additional_support.map((support, i) => <p key={i}>{locatorLabel(support.locator)}: {support.supporting_span}</p>)}
        {proposal.citation_kind === 'SOURCE_CITES_EXTERNAL' && <p>Reported by this source; original proof not inspected.</p>}
        {proposal.possible_duplicate_ids.length > 0 && <p>Possible overlap with {proposal.possible_duplicate_ids.join(', ')} · no automatic merge.</p>}
        {proposal.notes && <p>{proposal.notes}</p>}
        {proposal.review_decision && <p>Human Review: {proposal.review_decision} {proposal.mapped_id}</p>}
        <button onClick={() => onLocate(proposal.locator)}>Open Source · {locatorLabel(proposal.locator)}</button>
        <button disabled={!!run?.source_changed || proposal.provenance_status !== 'VALID'} onClick={() => onTask(taskAction('REVIEW_SOURCE_PROPOSAL', digest.digest_id, proposal.proposal_id))}>Open Human Review</button>
        {!run?.source_changed && proposal.provenance_status === 'PROVENANCE_INCOMPLETE' && <ConfirmLocation problemId={problemId} proposal={proposal} onConfirmed={() => { void client.invalidateQueries({ queryKey: ['source-digest', problemId, selectedId] }) }} />}
      </article>)}
      {digest.validation_warnings.length > 0 && <details><summary>Validation warnings</summary><ul>{digest.validation_warnings.map((value, i) => <li key={i}>{value}</li>)}</ul></details>}
    </>}
  </section>
}
