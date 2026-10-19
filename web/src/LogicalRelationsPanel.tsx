import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ProposalRow, type RelationModelSettings, type RelationPoolItem, type RelationPolicy } from './api'
import { useResearchActions } from './researchActions'
import { ActionConfirmation, llmDetails, type Confirmation } from './ActionConfirmation'

const RELATIONS = ['SAME_AS', 'PROVES', 'REFUTES', 'INVALIDATES', 'USES', 'DEPENDS_ON', 'SPECIAL_CASE_OF', 'GENERALIZES', 'STRENGTHENS', 'WEAKENS', 'REVISES', 'SUPERSEDES']
function ModelFields({ name, settings, onChange }: { name: string; settings: RelationModelSettings; onChange: (value: RelationModelSettings) => void }) {
  return <>
    <label className="field">{name} Provider<select aria-label={`${name} Provider`} value={settings.provider} onChange={e => onChange({ ...settings, provider: e.target.value, reasoning_effort: e.target.value === 'codex' || e.target.value === 'openai' ? 'medium' : null })}>
      <option value="codex">Codex CLI / ChatGPT quota</option>{['openai', 'anthropic', 'ollama', 'mistral'].map(p => <option key={p}>{p}</option>)}
    </select></label>
    <label className="field">{name} Model<input aria-label={`${name} Model`} value={settings.model} onChange={e => onChange({ ...settings, model: e.target.value })} /></label>
    <label className="field">{name} Reasoning<select aria-label={`${name} Reasoning`} value={settings.reasoning_effort || 'default'} onChange={e => onChange({ ...settings, reasoning_effort: e.target.value === 'default' ? null : e.target.value })}>
      <option value="default">default</option>{['codex', 'openai'].includes(settings.provider) && <><option>low</option><option>medium</option><option>high</option></>}{settings.provider === 'codex' && <><option>xhigh</option><option>max</option></>}
    </select></label>
  </>
}

function HumanControls({ item, decide, disabled }: { item: RelationPoolItem; decide: (id: string, action: string, rationale: string, relation?: string, target?: string) => void; disabled: boolean }) {
  const [rationale, setRationale] = useState('')
  const [relation, setRelation] = useState(item.proposed_relation)
  const [target, setTarget] = useState(item.target_id)
  return <details><summary>Human adjudication / override · {item.proposal_id}</summary>
    <label className="field">Rationale<textarea aria-label={`Rationale ${item.proposal_id}`} value={rationale} onChange={e => setRationale(e.target.value)} /></label>
    {['CONFIRM', 'REJECT', 'UNCERTAIN'].map(action => <button key={action} disabled={disabled || !rationale.trim()} onClick={() => decide(item.proposal_id, action, rationale)}>Human {action === 'UNCERTAIN' ? 'defer / uncertain' : action.toLowerCase()}</button>)}
    <label className="field">Corrected relation<select aria-label={`Corrected relation ${item.proposal_id}`} value={relation} onChange={e => setRelation(e.target.value)}>{RELATIONS.map(r => <option key={r}>{r}</option>)}</select></label>
    <label className="field">Corrected target<input aria-label={`Corrected target ${item.proposal_id}`} value={target} onChange={e => setTarget(e.target.value)} /></label>
    <button disabled={disabled || !rationale.trim() || !target.trim()} onClick={() => decide(item.proposal_id, 'CORRECT', rationale, relation, target)}>Human correct</button>
    <p>追加历史记录；Human override 优先于模型。对象正文仍需在 Human Review 中 Accept。</p>
  </details>
}

export function LogicalRelationsPanel({ problemId, episodeId, rows, selectedCandidateIds, onChanged }: {
  problemId: string; episodeId: string | null; rows: ProposalRow[]; selectedCandidateIds: string[]; onChanged: () => void
}) {
  const client = useQueryClient()
  const actions = useResearchActions(problemId)
  const defaults = useQuery({ queryKey: ['research-settings'], queryFn: api.researchSettings })
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [scout, setScout] = useState<RelationModelSettings>({ provider: '', model: '', reasoning_effort: null })
  const [adjudicator, setAdjudicator] = useState<RelationModelSettings>({ provider: '', model: '', reasoning_effort: null })
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [budget, setBudget] = useState(0)
  useEffect(() => { if (defaults.data) { setScout(defaults.data.scout); setAdjudicator(defaults.data.adjudicator); setBudget(defaults.data.adjudication_tokens) } }, [defaults.data])
  const [scoutJobId, setScoutJobId] = useState<string | null>(null)
  const [adjudicationJobId, setAdjudicationJobId] = useState<string | null>(null)
  const policy = useQuery({ queryKey: ['hard', 'policy', problemId], queryFn: () => api.hardPolicy(problemId) })
  const pool = useQuery({ queryKey: ['hard', 'pool', problemId, episodeId, filter], queryFn: () => api.hardPool(problemId, episodeId, filter) })
  const scoutRuns = useQuery({ queryKey: ['hard', 'scout-runs', problemId, episodeId], queryFn: () => api.hardScoutRuns(problemId, episodeId) })
  const adjudicationRuns = useQuery({ queryKey: ['hard', 'adjudication-runs', problemId], queryFn: () => api.hardAdjudicationRuns(problemId) })
  const history = useQuery({ queryKey: ['hard', 'history', problemId], queryFn: () => api.hardHistory(problemId) })
  const scoutJob = useQuery({ queryKey: ['hard-job', scoutJobId], queryFn: () => api.hardJob(scoutJobId!), enabled: !!scoutJobId, refetchInterval: q => q.state.data?.status === 'running' ? 1000 : false })
  const adjudicationJob = useQuery({ queryKey: ['hard-job', adjudicationJobId], queryFn: () => api.hardJob(adjudicationJobId!), enabled: !!adjudicationJobId, refetchInterval: q => q.state.data?.status === 'running' ? 1000 : false })
  function refresh() { void client.invalidateQueries({ queryKey: ['hard'] }); onChanged() }
  useEffect(() => { if (scoutJob.data?.status === 'completed') refresh() }, [scoutJob.data?.status, scoutJobId]) // Stage 1 never invokes Stage 2.
  useEffect(() => { if (adjudicationJob.data?.status === 'completed') refresh() }, [adjudicationJob.data?.status, adjudicationJobId])
  useEffect(() => { setSelected([]); setScoutJobId(null); setAdjudicationJobId(null) }, [problemId, episodeId])
  const runScout = useMutation({ mutationFn: ({ ids, rerun }: { ids: string[] | null; rerun: boolean }) => actions.scout(episodeId!, scout, ids, rerun), onSuccess: j => setScoutJobId(j.job_id) })
  const runAdjudication = useMutation({ mutationFn: (ids: string[] | null) => actions.adjudicate(episodeId, adjudicator, ids, budget), onSuccess: j => setAdjudicationJobId(j.job_id) })
  const human = useMutation({ mutationFn: ({ id, action, rationale, relation, target }: { id: string; action: string; rationale: string; relation?: string; target?: string }) => actions.humanRelation(id, action, rationale, relation || null, target || null), onSuccess: refresh })
  const savePolicy = useMutation({ mutationFn: (value: RelationPolicy) => actions.setPolicy(value), onSuccess: refresh })
  const enroll = useMutation({ mutationFn: () => actions.enroll(episodeId!), onSuccess: refresh })
  const ids = selectedCandidateIds.filter(id => rows.some(r => r.candidate.candidate_id === id && r.candidate.kind !== 'relation'))
  const visibleSelected = selected.filter(id => pool.data?.some(p => p.proposal_id === id))
  useEffect(() => { setConfirmation(null) }, [scout, adjudicator, budget, selectedCandidateIds, selected, episodeId, problemId])
  const scoutBusy = runScout.isPending || scoutJob.data?.status === 'running'
  const adjudicatorBusy = runAdjudication.isPending || adjudicationJob.data?.status === 'running'
  const errors = [defaults.error, policy.error, pool.error, scoutRuns.error, adjudicationRuns.error, history.error, runScout.error, runAdjudication.error, human.error, savePolicy.error, enroll.error, scoutJob.error, adjudicationJob.error]
  function confirm(title: string, settings: RelationModelSettings, selection: string, run: () => void, role: 'Relation Scout' | 'Relation Judge' | null = null) {
    setConfirmation({ title, details: { ...(role ? llmDetails(role, 'selected proposals and explicit mathematical context') : { 'Uses LLM': 'No' }),
      'Selected Proposals / Proposals': selection, Episode: episodeId,
      ...(role ? { Provider: settings.provider, Model: settings.model, Reasoning: settings.reasoning_effort } : {}), Policy: policy.data?.mode || 'not loaded' }, run })
  }
  return <section id="logical-relations" className="task-card" aria-label="Two-stage Logical Relations">
    <h2 id="logical-relations-heading" className="review-section-heading">Logical Relations</h2><p>Relation Scout → Persistent Relation Proposal Pool → optional Human / Model Relation Review。两个阶段可跨会话独立运行。</p>
    <h3>Relation Scout</h3><ModelFields name="Scout" settings={scout} onChange={setScout} />
    <p>调用模型只产生 validator-qualified scout candidate；主题、方法和参数相似属于 soft relevance。</p>
    <button disabled={!episodeId || !scout.model.trim() || !ids.length || scoutBusy} onClick={() => confirm('运行 Relation Scout', scout, ids.join(', '), () => runScout.mutate({ ids, rerun: false }), 'Relation Scout')}>Scout selected</button>
    <button disabled={!episodeId || !scout.model.trim() || scoutBusy || !rows.some(r => r.candidate.kind !== 'relation')} onClick={() => confirm('运行 Relation Scout', scout, 'All unresolved', () => runScout.mutate({ ids: null, rerun: false }), 'Relation Scout')}>Scout all unresolved</button>
    <button disabled={!episodeId || !scout.model.trim() || !ids.length || scoutBusy} onClick={() => confirm('重跑 Relation Scout', scout, ids.join(', '), () => runScout.mutate({ ids, rerun: true }), 'Relation Scout')}>Rerun selected</button>
    {scoutJob.data && <p>Scout task: {scoutJob.data.status} {scoutJob.data.error}</p>}
    <details><summary>Scout run audit · No logical relation / Uncertain / Added to Relation Proposal Pool</summary>{(scoutRuns.data || []).map(run => <details key={run.run_id}><summary>{run.run_id} · {run.status} · {run.elapsed_seconds.toFixed(1)}s · usage {JSON.stringify(run.usage)}</summary><pre>{JSON.stringify(run, null, 2)}</pre></details>)}</details>
    <h3>Relation Proposal Pool</h3>
    <label className="field">Pool status<select aria-label="Pool status" value={filter} onChange={e => setFilter(e.target.value)}><option value="">All</option>{['pending_adjudication', 'MODEL_CONFIRMED', 'HUMAN_CONFIRMED', 'REJECTED', 'UNCERTAIN', 'confirmed_pending_source', 'confirmed_pending_target', 'model_confirmed_pending_human', 'confirmed_stale_input', 'confirmed_inactive'].map(s => <option key={s}>{s}</option>)}</select></label>
    <button disabled={!episodeId || enroll.isPending} onClick={() => confirm('登记已解析的显式局部关系', scout, episodeId || '', () => enroll.mutate())}>Enroll explicit local relations</button>
    {(pool.data || []).map(item => <div className="proposal" key={item.proposal_id}>
      <label><input type="checkbox" aria-label={`Select ${item.proposal_id}`} checked={selected.includes(item.proposal_id)} onChange={e => setSelected(current => e.target.checked ? [...current, item.proposal_id] : current.filter(id => id !== item.proposal_id))} /> {item.source_candidate_id} {item.proposed_relation} {item.target_id}</label>
      <p>{item.current_status} · {item.confirmation} · {item.active ? 'active' : 'inactive'} · origin {item.origin} · Scout {item.scout_model || 'explicit'} · confidence {item.confidence}</p>
      <p>{item.rationale}</p>{item.latest_decision && <p>confirmed/decided: {item.latest_decision.confirmed_by} · {item.latest_decision.model} · {item.latest_decision.reasoning_effort} · {item.latest_decision.rationale}</p>}
      {item.effective_relation && <p>Effective: {item.source_id || 'pending source acceptance'} {item.effective_relation} {item.effective_target_id}</p>}{item.inactive_reason && <p>{item.inactive_reason}</p>}
      <HumanControls item={item} disabled={human.isPending} decide={(id, action, rationale, relation, target) => confirm(`Human ${action}`, adjudicator, id, () => human.mutate({ id, action, rationale, relation, target }))} />
      <details><summary>Decision history · {item.proposal_id}</summary><pre>{JSON.stringify((history.data || []).filter(d => d.proposal_id === item.proposal_id), null, 2)}</pre><p>Scout runs: {item.scout_run_ids.join(', ')}</p></details>
    </div>)}
    <h3>Adjudication</h3>
    <ModelFields name="Adjudicator" settings={adjudicator} onChange={setAdjudicator} />
    <p>推荐 Scout: gpt-6-luna / medium；Adjudicator: gpt-6.1-sol / medium。复杂、UNCERTAIN 或高影响关系可选择 high。</p>
    <label className="field">Adjudication token budget<input type="number" aria-label="Adjudication token budget" min={128} max={200000} value={budget} onChange={e => setBudget(Number(e.target.value))} /></label>
    {policy.data && <><label className="field">Adjudication policy<select aria-label="Adjudication policy" value={policy.data.mode} disabled={savePolicy.isPending} onChange={e => { const value = { ...policy.data!, mode: e.target.value as 'HUMAN_ONLY' | 'MODEL_OR_HUMAN' }; confirm('修改 Logical Relation policy', adjudicator, value.mode, () => savePolicy.mutate(value)) }}><option value="HUMAN_ONLY">Human only</option><option value="MODEL_OR_HUMAN">Model or Human</option></select></label>
      <label><input type="checkbox" checked={policy.data.require_human_for_state_changing} disabled={savePolicy.isPending} onChange={e => { const value = { ...policy.data!, require_human_for_state_changing: e.target.checked }; confirm('修改 state-changing policy', adjudicator, String(value.require_human_for_state_changing), () => savePolicy.mutate(value)) }} /> Require Human for state-changing relations (REFUTES / INVALIDATES / SUPERSEDES)</label></>}
    <button disabled={policy.data?.mode !== 'MODEL_OR_HUMAN' || !visibleSelected.length || !adjudicator.model.trim() || adjudicatorBusy || !Number.isInteger(budget) || budget < 128 || budget > 200000} onClick={() => confirm('运行 Relation Review', adjudicator, visibleSelected.join(', '), () => runAdjudication.mutate(visibleSelected), 'Relation Judge')}>Adjudicate selected</button>
    <button disabled={policy.data?.mode !== 'MODEL_OR_HUMAN' || !pool.data?.some(p => ['pending_adjudication', 'UNCERTAIN', 'confirmed_stale_input'].includes(p.current_status)) || !adjudicator.model.trim() || adjudicatorBusy || !Number.isInteger(budget) || budget < 128 || budget > 200000} onClick={() => confirm('运行 Relation Review', adjudicator, 'All pending', () => runAdjudication.mutate(null), 'Relation Judge')}>Adjudicate all pending</button>
    {adjudicationJob.data && <p>Adjudication task: {adjudicationJob.data.status} {adjudicationJob.data.error}</p>}
    <p>MODEL_CONFIRMED ≠ HUMAN_CONFIRMED。source 仍必须 Human Accept；关系确认不等于 theorem verification。完整正文超过 budget 时拒绝调用，不静默截断。</p>
    <details><summary>Adjudication run audit / full input / actual usage</summary>{(adjudicationRuns.data || []).map(run => <details key={run.run_id}><summary>{run.run_id} · {run.status} · {run.elapsed_seconds.toFixed(1)}s · usage {JSON.stringify(run.usage)}</summary><pre>{JSON.stringify(run, null, 2)}</pre></details>)}</details>
    <ActionConfirmation value={confirmation} onClose={() => setConfirmation(null)} />
    {errors.filter(Boolean).map((error, i) => <p role="alert" key={i}>{String(error)}</p>)}
  </section>
}
