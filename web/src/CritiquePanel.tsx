import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type CritiqueSettings, type ObjectKind, type ResearchIntent } from './api'
import { ActionConfirmation, llmDetails, type Confirmation } from './ActionConfirmation'
import { taskAction, useResearchActions } from './researchActions'

export const supportsCritique = (kind: string) => ['claim', 'gap', 'proof', 'counterexample', 'evidence'].includes(kind)

export function CritiquePanel({ problemId, targetId, onTask, onOpen }: {
  problemId: string; targetId: string; onTask: (intent: ResearchIntent) => void
  onOpen: (kind: ObjectKind, id: string) => void
}) {
  const client = useQueryClient(), actions = useResearchActions(problemId)
  const preflight = useQuery({ queryKey: ['critique-preflight', problemId, targetId], queryFn: () => api.critiquePreflight(problemId, targetId) })
  const history = useQuery({ queryKey: ['critiques', problemId, targetId], queryFn: () => api.critiqueHistory(problemId, targetId) })
  const [settings, setSettings] = useState<CritiqueSettings | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const confirmedSignature = useRef('')
  const signature = JSON.stringify([targetId, settings, preflight.data?.bundle_sha256])
  const refreshed = useRef<string | null>(null)
  useEffect(() => { if (preflight.data) setSettings(preflight.data.settings) }, [preflight.data?.settings])
  const selectedId = runId || history.data?.[0]?.critique_id || null
  const poll = useQuery({ queryKey: ['critique-run', problemId, selectedId], queryFn: () => api.critiqueRun(problemId, selectedId!), enabled: !!selectedId,
    refetchInterval: query => !query.state.error && query.state.data?.status === 'RUNNING' ? 1000 : false })
  const selected = poll.data || history.data?.find(run => run.critique_id === selectedId)
  const running = selected?.status === 'RUNNING' || history.data?.some(run => run.status === 'RUNNING')
  const start = useMutation({ mutationFn: (request: { settings: CritiqueSettings; sha: string }) => actions.startCritique(targetId, request.settings, request.sha),
    onSuccess: run => {
      setRunId(run.critique_id); client.setQueryData(['critique-run', problemId, run.critique_id], run)
      void client.invalidateQueries({ queryKey: ['critiques', problemId, targetId] })
    }, onError: () => { void preflight.refetch() } })
  useEffect(() => { if (settings && confirmedSignature.current !== signature) setConfirmation(null) }, [signature, settings])
  useEffect(() => {
    if (selected && selected.status !== 'RUNNING' && refreshed.current !== selected.critique_id) {
      refreshed.current = selected.critique_id
      void client.invalidateQueries({ queryKey: ['critiques', problemId, targetId] })
      void client.invalidateQueries({ queryKey: ['research-map', problemId] })
    }
  }, [selected?.status, selected?.critique_id])
  function confirm() {
    if (!settings || !preflight.data) return
    const request = { settings: { ...settings }, sha: preflight.data.bundle_sha256 }
    confirmedSignature.current = signature
    setConfirmation({ title: 'Confirm independent critique', details: {
      ...llmDetails('Independent Critique', 'Fresh independent context'),
      Target: targetId, Mode: 'Independent critique', Provider: settings.provider, Model: settings.model,
      Reasoning: settings.reasoning_effort, Context: 'Fresh independent context', Authority: 'Advisory only',
    }, run: () => start.mutate(request) })
  }
  const report = selected?.report
  return <section className="task-card critique-panel" aria-label="Independent Critique">
    <h2>Independent Critique</h2><p>Target: {targetId}</p>
    <p className="critique-advisory">Advisory only — not mathematical verification. Critique does not change Human Review, Logical Relations or research authority.</p>
    <p className="meta">Fresh independent context · no Agent trajectory, chat transcript or previous critique. Web and computation tools are disabled.</p>
    {settings && <details><summary>Critique model settings</summary>
      <label className="field">Provider<select aria-label="Critique provider" disabled={!!running} value={settings.provider} onChange={e => setSettings({ ...settings, provider: e.target.value as CritiqueSettings['provider'], reasoning_effort: ['codex', 'openai'].includes(e.target.value) ? 'high' : null })}>{['codex', 'openai', 'anthropic', 'ollama', 'mistral'].map(name => <option key={name}>{name}</option>)}</select></label>
      <label className="field">Model<input aria-label="Critique model" disabled={!!running} value={settings.model} onChange={e => setSettings({ ...settings, model: e.target.value })} /></label>
      <label className="field">Reasoning<select aria-label="Critique reasoning" disabled={!!running} value={settings.reasoning_effort || ''} onChange={e => setSettings({ ...settings, reasoning_effort: (e.target.value || null) as CritiqueSettings['reasoning_effort'] })}><option value="">Provider default</option>{(['codex', 'openai'].includes(settings.provider) ? ['low', 'medium', 'high', ...(settings.provider === 'codex' ? ['xhigh', 'max'] : [])] : []).map(effort => <option key={effort}>{effort}</option>)}</select></label>
    </details>}
    {preflight.data && <details><summary>Critique context ({preflight.data.bundle.context.length + preflight.data.bundle.relations.length + 2} items)</summary>
      {[preflight.data.bundle.target, preflight.data.bundle.problem, ...preflight.data.bundle.context, ...preflight.data.bundle.relations].map(item => <p key={item.record_id}>{item.record_id} · {item.record_type} · {item.authority}<br />{item.reason_included}</p>)}
      {preflight.data.bundle.limitations.map((limit, i) => <p key={i}>{limit}</p>)}
    </details>}
    <button disabled={!settings || !settings.model.trim() || !preflight.data || !!running || start.isPending} onClick={confirm}>Critique this result</button>
    <ActionConfirmation value={confirmation} onClose={() => setConfirmation(null)} />
    {(start.isPending || selected?.status === 'RUNNING' && !poll.error) && <p role="status">RUNNING · Independent critique</p>}
    {(preflight.error || history.error || poll.error || start.error) && <p role="alert">{String(preflight.error || history.error || poll.error || start.error)}</p>}
    <h3>Critique history</h3>
    {history.data?.length === 0 && <p>No critiques yet.</p>}
    {(history.data || []).map(run => <button key={run.critique_id} aria-pressed={selectedId === run.critique_id} onClick={() => { setRunId(run.critique_id); setConfirmation(null) }}>{run.critique_id} · {run.status} · {run.report?.verdict || ''}</button>)}
    {selected?.status === 'FAILED' && <p role="alert">FAILED · {selected.error}</p>}
    {report && <div className="critique-report">
      <h3>{report.verdict}</h3><p>{report.critique_id} · {report.target_id} · {report.created_at}</p>
      <p className="meta">{report.provider} · {report.model} · {report.reasoning_effort || 'provider default'}</p>
      {report.verdict === 'NO_CLEAR_ISSUE' && <p>No clear issue found by this critique. This is not a proof verification.</p>}
      <p>{report.summary}</p><h3>Issues</h3>
      {report.issues.length === 0 && <p>No specific issues recorded.</p>}
      {report.issues.map(issue => <article className="critique-issue" key={issue.issue_id}><h4>[{issue.severity}] {issue.category}</h4><p>Location: {issue.location}</p><p>{issue.explanation}</p><p>Mathematical consequence: {issue.mathematical_consequence}</p><p>Suggested check: {issue.suggested_check}</p></article>)}
      <h3>Suggested checks</h3><ul>{report.suggested_checks.map((check, i) => <li key={i}>{check}</li>)}</ul>
      <h3>Limitations</h3><ul>{report.limitations.map((limit, i) => <li key={i}>{limit}</li>)}</ul>
      <details><summary>Saved context manifest</summary>{report.context_manifest.map(item => <details key={item.record_id}><summary>{item.record_id} · {item.record_type} · {item.authority}</summary><p>{item.reason_included}</p><p className="meta">SHA-256: {item.sha256}</p><pre>{item.content}</pre></details>)}</details>
      <p className="critique-advisory">Advisory only — not mathematical verification.</p>
      <button onClick={() => onOpen(report.target_type, report.target_id)}>Open target in Reader</button>
      {selected?.continuation_target_id && <button onClick={() => onTask(taskAction('CONTINUE_RESEARCH', selected.continuation_target_id))}>Continue Research · {selected.continuation_target_id}</button>}
    </div>}
  </section>
}
