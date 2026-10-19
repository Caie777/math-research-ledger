import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AgentSettings, type ResearchIntent } from './api'
import { useResearchActions } from './researchActions'
import { ProgressDetails, useRunProgress } from './RunProgress'

export function ResearchAgentPanel({ problemId, selectedTarget, onChanged, intent }: {
  problemId: string; selectedTarget: string | null; onChanged: () => void; intent?: ResearchIntent
}) {
  const [target, setTarget] = useState(selectedTarget || '')
  const [task, setTask] = useState('')
  const [entry, setEntry] = useState<'web' | 'operator'>('web')
  const actions = useResearchActions(problemId)
  const defaults = useQuery({ queryKey: ['research-settings'], queryFn: api.researchSettings })
  const models = useQuery({ queryKey: ['model-settings'], queryFn: api.modelSettings, retry: false })
  const savedRuns = useQuery({ queryKey: ['research-runs', problemId], queryFn: () => api.agentRuns(problemId) })
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [effort, setEffort] = useState('')
  const [provisional, setProvisional] = useState(false)
  const [context, setContext] = useState(0)
  const [checkpointEvery, setCheckpointEvery] = useState(0)
  const queryClient = useQueryClient()
  const [budget, setBudget] = useState<AgentSettings['budget'] | null>(null)
  useEffect(() => {
    const value = defaults.data?.research
    if (value) { setProvider(value.provider); setModel(value.model || ''); setEffort(value.effort || ''); setProvisional(value.include_provisional); setContext(value.context_tokens); setCheckpointEvery(value.checkpoint_every_effective_steps || 0); setBudget(value.budget) }
  }, [defaults.data])
  useEffect(() => {
    const role = models.data?.roles.research
    if (role && entry === 'web') { setProvider(role.provider); setModel(role.model); setEffort(role.reasoning_effort || '') }
    if (entry === 'operator' && defaults.data) { setProvider('codex'); setModel(defaults.data.research.model || ''); setEffort(defaults.data.research.effort || '') }
  }, [models.data, defaults.data, entry])
  const bounds: Record<string, [number, number]> = { max_agent_steps: [1, 1000], max_model_calls: [1, 1000], max_context_tokens: [2048, 200000], max_tool_calls: [0, 1000], max_web_calls: [0, 100], max_python_calls: [0, 1000], max_wall_time: [5, 14400] }
  const [runId, setRunId] = useState<string | null>(null)
  const progress = useRunProgress(problemId, runId)
  const refreshed = useRef<string | null>(null)
  const starting = useRef(false)
  const targets = useQueries({ queries: (['claim', 'gap'] as const).map(kind => ({ queryKey: ['objects', problemId, kind], queryFn: () => api.objects(problemId, kind) })) })
  const options = targets.flatMap(query => query.data || []).filter(object => !['RESOLVED', 'REFUTED'].includes(object.state?.research_state || ''))
  const state = useQuery({ queryKey: ['agent-state', problemId, target, provisional], queryFn: () => api.researchState(problemId, target, provisional), enabled: options.some(o => o.id === target) })
  const resolved = state.data?.research_status === 'RESOLVED' || state.data?.research_status === 'REFUTED'
  useEffect(() => {
    if (savedRuns.data) setRunId(savedRuns.data.find(run => run.executor_attached)?.run_id || savedRuns.data[0]?.run_id || null)
  }, [problemId, savedRuns.data])
  useEffect(() => { setTarget(selectedTarget || '') }, [selectedTarget])
  const run = useQuery({ queryKey: ['agent-run', problemId, runId], queryFn: () => api.agentRun(problemId, runId!), enabled: !!runId, refetchInterval: query => query.state.data?.status === 'running' && query.state.data.executor_attached === true ? 1000 : (progress.data?.status || query.state.data?.status) === 'finished' ? false : 1000 })
  const start = useMutation({ mutationFn: (request: AgentSettings) => actions.startResearch(request, entry),
    onSettled: () => { starting.current = false },
    onSuccess: value => { setRunId(value.run_id); void queryClient.invalidateQueries({ queryKey: ['research-runs', problemId] }) } })
  const stop = useMutation({ mutationFn: (id: string) => actions.stopResearch(id), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['agent-progress', problemId, runId] }) } })
  const resume = useMutation({ mutationFn: (id: string) => actions.resumeResearch(id), onSuccess: value => {
    refreshed.current = null; queryClient.setQueryData(['agent-run', problemId, value.run_id], value)
    void queryClient.invalidateQueries({ queryKey: ['agent-progress', problemId, value.run_id] })
    void queryClient.invalidateQueries({ queryKey: ['agent-run', problemId, value.run_id] })
  } })
  useEffect(() => {
    if (run.data?.status === 'finished' && refreshed.current !== run.data.run_id) {
      refreshed.current = run.data.run_id; onChanged()
      void queryClient.invalidateQueries({ queryKey: ['agent-state', problemId] })
    }
  }, [run.data?.status, run.data?.run_id, onChanged])
  const running = !!run.data && run.data?.status !== 'finished' && run.data?.executor_attached !== false
  function startResearch() {
    if (!budget || !defaults.data || starting.current) return
    const request: AgentSettings = { ...defaults.data.research, target: { kind: 'claim', problem_id: problemId, node_id: target }, task, provider,
      model: model.trim() || null, effort: effort || null, context_tokens: context, include_provisional: provisional,
      budget, checkpoint_every_effective_steps: checkpointEvery }
    starting.current = true; start.mutate(request)
  }

  function resumeResearch() {
    if (run.data?.resume_available) resume.mutate(run.data.run_id)
  }
  const handledIntent = useRef<ResearchIntent | null>(null)
  useEffect(() => {
    if (!intent || handledIntent.current === intent) return
    if (intent.intent === 'RESUME_RESEARCH' && run.data?.resume_available) { handledIntent.current = intent; resumeResearch() }
    if (intent.intent === 'STOP_RESEARCH' && running && runId) { handledIntent.current = intent; stop.mutate(runId) }
  }, [intent, runId, run.data?.resume_available, running])
  const phase = start.isPending ? 'STARTING' : running ? 'RUNNING'
    : run.data?.executor_attached === false && run.data.status === 'running' ? 'INTERRUPTED'
    : run.data?.error ? 'FAILED' : run.data?.status === 'finished' ? 'FINISHED' : target ? 'CONFIRM_SETTINGS' : 'SELECT_TARGET'
  return <section id="research-agent" className="task-card research-agent" aria-labelledby="research-agent-heading"><h2 id="research-agent-heading" className="review-section-heading">Research Agent</h2>
    <p className="meta">{phase} · Long-Horizon Explore</p>
    <p>选择未解决的 Claim / Gap 即可继续探索。预算是安全上限；最终输出 Episode + Research Handoff / pending Proposals，需 Human Review 才能进入 Problem Record。</p>
    <p className="meta">中间 RESULT / PROOF 会保存后继续推进；只有目标实质解决、路线耗尽或继续的边际价值很低时才主动最终交接。</p>
    <label className="field">Research entry<select aria-label="Research entry" value={entry} disabled={running} onChange={e => setEntry(e.target.value as 'web' | 'operator')}><option value="web">Web API · Research role</option><option value="operator">Existing Codex/operator · own CLI login</option></select></label>
    {entry === 'web' && <p>Web 使用 Settings → Models 的 Research Agent role（{models.data?.status.research || 'missing'}）。<a href="#research-settings" onClick={() => { const settings = document.getElementById('research-settings'); if (settings instanceof HTMLDetailsElement) settings.open = true }}>Open Settings</a></p>}
    <label className="field">Target Claim / Gap<select aria-label="Agent target" value={target} disabled={running} onChange={e => setTarget(e.target.value)}><option value="">Choose a target</option>{options.map(item => <option key={item.id} value={item.id}>{item.id} · {item.title}</option>)}</select></label>
    <label className="field">Optional steering instruction<textarea aria-label="Agent steering (optional)" placeholder="可留空；例如：这轮重点注意反例。" value={task} disabled={running} onChange={e => setTask(e.target.value)} /></label>
    <details><summary>Advanced options / safety fuses</summary>
    <label className="field">Agent provider<select aria-label="Agent provider" value={provider} disabled={running} onChange={e => setProvider(e.target.value)}><option value="codex">Codex CLI / ChatGPT quota</option><option>openai</option><option>anthropic</option><option>ollama</option><option>mistral</option></select></label>
    <label className="field">Agent model<input aria-label="Agent model" value={model} disabled={running} onChange={e => setModel(e.target.value)} list="agent-models" /></label>
    <datalist id="agent-models"><option value="gpt-6.1-sol" /><option value="gpt-6-luna" /></datalist>
    <label className="field">Agent reasoning effort<select aria-label="Agent effort" value={effort} disabled={running} onChange={e => setEffort(e.target.value)}><option value="">Provider default</option><option>low</option><option>medium</option><option>high</option>{provider === 'codex' && <><option>xhigh</option><option>max</option></>}</select></label>
    <label className="field">Agent tool policy<select aria-label="Agent tool policy" disabled={running}><option>research_standard</option></select></label>
    <label className="field">Agent context budget<input aria-label="Agent context budget" type="number" min={128} max={200000} value={context} disabled={running} onChange={e => setContext(Number(e.target.value))} /></label>
    <label className="field">Checkpoint every effective steps<input aria-label="Checkpoint every effective steps" type="number" min={1} max={100} value={checkpointEvery} disabled={running} onChange={e => setCheckpointEvery(Number(e.target.value))} /></label>
    {Object.entries(budget || {}).filter(([key]) => key in bounds).map(([key, value]) => <label className="field" key={key}>{key}<input aria-label={`Agent ${key}`} type="number" min={bounds[key][0]} max={bounds[key][1]} value={value} disabled={running} onChange={e => setBudget(current => current ? ({ ...current, [key]: Number(e.target.value) }) : null)} /></label>)}
    <label><input type="checkbox" checked={provisional} disabled={running} onChange={e => setProvisional(e.target.checked)} /> Include provisional Episodes / Proposals / model-confirmed relations</label>
    </details>
    <p className="meta">Provisional ≠ theorem truth。预算内预留一次 checkpoint 调用；Stop 尽可能保存部分 Episode。计算只能写 run work，工具结果按需局部读取。</p>
    <div className="action-row"><button disabled={running || start.isPending || !budget || !defaults.data || !state.data || resolved || !options.some(o => o.id === target)} onClick={startResearch}>Continue Research</button><button disabled={!running || stop.isPending || !runId} onClick={() => stop.mutate(runId!)}>Stop</button><button disabled={running || resume.isPending || !run.data?.resume_available} onClick={resumeResearch}>Resume interrupted run</button></div>
    {intent?.intent === 'STOP_RESEARCH' && !running && <p>没有可停止的附着运行。</p>}
    {intent?.intent === 'RESUME_RESEARCH' && !run.data?.resume_available && <p>当前 run 不可恢复；查看 Resume availability。</p>}
    {defaults.error && <p role="alert">{String(defaults.error)}</p>}
    {resolved && <p>当前 target 已 resolved/refuted；请选择未解决的 Claim / Gap。</p>}
    {state.data && <details><summary>Current Research State</summary><pre>{state.data.markdown}</pre></details>}
    {(start.error || stop.error || resume.error || run.error || state.error) && <p role="alert" className="error">{String(start.error || stop.error || resume.error || run.error || state.error)}</p>}
    {run.data && <div><p>{run.data.run_id} · {run.data.executor_attached === false && run.data.status === 'running' ? 'detached / audit available' : run.data.status}</p>
      <ProgressDetails progress={progress.data} error={progress.error} />
      <pre>{JSON.stringify(run.data.usage, null, 2)}</pre><p>{JSON.stringify(run.data.availability)}</p>
      <p>Last checkpoint step: {run.data.last_checkpoint_step ?? 0} · Uncheckpointed public events: {run.data.uncheckpointed_public_events ?? 0}</p>
      <p>Resume availability: {run.data.resume_available ? 'available (original budgets/settings)' : run.data.resume_unavailable_reason || 'unavailable'}</p>
      {run.data.latest_checkpoint && <p><a href={api.agentArtifactUrl(problemId, run.data.run_id, run.data.latest_checkpoint)} download>Latest checkpoint</a></p>}
      {run.data.artifacts.map(path => <p key={path}><a href={api.agentArtifactUrl(problemId, run.data!.run_id, path)} download>{path}</a></p>)}
      {run.data.checkpoint_path && <p><a href={api.agentArtifactUrl(problemId, run.data.run_id, run.data.checkpoint_path)} download>Research Episode + Handoff</a></p>}
      {run.data.episode_id && <p>Episode output: {run.data.episode_id} · {run.data.candidate_ids.length} pending candidates</p>}
      <a href={api.agentAuditUrl(problemId, run.data.run_id)} download>Run audit</a>
    </div>}
  </section>
}
