import { useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type CoordinatorAction, type CoordinatorRequest, type CoordinatorResponse, type CoordinatorRefs, type ResearchIntent } from './api'
import { taskAction, type ActionOrigin } from './researchActions'
import { RunProgress } from './RunProgress'

export const QUICK_TASKS = [
  ['CREATE_PROBLEM', '新建研究问题'], ['CONTINUE_RESEARCH', '继续研究'],
  ['IMPORT_DECOMPOSE_EPISODE', 'Import Research Episode'], ['HUMAN_REVIEW', '人工审核'],
  ['FIND_RELATED_RESEARCH', '查找相关资料'], ['LOGICAL_RELATIONS', 'Logical Relations'], ['RESEARCH_STATUS', '研究状态'],
] as const
const COORDINATOR_QUICK: [CoordinatorAction['name'], string][] = [
  ['get_recent_research', '最近研究进展'], ['get_research_portfolio', '全部问题概览'],
  ['get_unresolved_targets', '未解决问题'], ['list_research_runs', '当前运行任务'], ['start_research', '开始研究'],
]
const MAINTENANCE_TASKS = [
  ['ADD_SOURCE', '添加资料'], ['SYSTEM_HEALTH', 'System Health'],
  ['EXPORT_WORKSPACE_SNAPSHOT', 'Export Workspace Snapshot'], ['VERIFY_SNAPSHOT', 'Verify Snapshot'],
  ['EXPORT_RESEARCH_HANDOFF', 'Export Research Handoff'],
] as const
type ChatMessage = { role: 'User'; text: string } | { role: 'Coordinator'; result: CoordinatorResponse; request: CoordinatorRequest }

export function ResearchAssistant({ problemId, targetId, onTask, onOpenEpisode, onProblem, children }: {
  problemId: string; targetId: string | null; onTask: (intent: ResearchIntent, origin: ActionOrigin) => void
  onOpenEpisode: (id: string) => void; onProblem?: (id: string) => void; children: ReactNode
}) {
  const client = useQueryClient()
  const portfolio = useQuery({ queryKey: ['research-portfolio'], queryFn: api.researchPortfolio, retry: false })
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [active, setActive] = useState<CoordinatorRefs | null>(null)
  const observedRun = useRef<CoordinatorRefs | null>(null)
  const [lastRequest, setLastRequest] = useState<CoordinatorRequest | null>(null)
  const dispatching = useRef(false)
  const route = useMutation({ mutationFn: (request: CoordinatorRequest) => api.coordinator(request), retry: false,
    onSuccess: (result, request) => {
      if (result.structured_payload.open_task === 'IMPORT_DECOMPOSE_EPISODE') onTask(taskAction('IMPORT_DECOMPOSE_EPISODE'), 'research_chat')
      setMessages(current => [...current.slice(-19), { role: 'Coordinator', result, request }])
      // Cache identity only; progress facts are fetched through the existing unified hook.
      if (result.run_id && result.resolved_refs.problem_id) {
        setActive({ ...result.resolved_refs, run_id: result.run_id })
        const pid = result.resolved_refs.problem_id
        for (const key of ['research-runs', 'agent-run', 'agent-progress', 'agent-state']) {
          void client.invalidateQueries({ queryKey: [key, pid] })
        }
      }
    },
    onSettled: () => { dispatching.current = false },
  })
  function send(text: string, action?: CoordinatorAction, context?: CoordinatorRefs) {
    if (route.isPending || dispatching.current) return
    dispatching.current = true
    const request: CoordinatorRequest = { message: text, action,
      selected_problem_id: context?.problem_id || problemId || null,
      selected_object_id: context?.target_id || targetId,
      active_run_id: context?.run_id || active?.run_id || (observedRun.current?.problem_id === problemId ? observedRun.current.run_id : null) }
    setMessages(current => [...current.slice(-19), { role: 'User', text }])
    setLastRequest(request); setInput(''); route.mutate(request)
  }
  function choose(result: CoordinatorResponse, request: CoordinatorRequest, choice: CoordinatorRefs) {
    const pending = result.pending_action || request.action
    send(`选择 ${choice.problem_id || choice.run_id || choice.target_id}`, pending ? { ...pending,
      problem_ref: choice.problem_id, target_ref: choice.target_id, run_ref: choice.run_id } : undefined, choice)
  }
  return <>
    <section className="quick-actions" aria-label="Quick Actions"><h2>Quick Actions</h2>
      <div className="quick-action-grid">{COORDINATOR_QUICK.map(([name, label]) => <button disabled={route.isPending} key={name} onClick={() => send(label, { name, active_only: name === 'list_research_runs' })}>{label}</button>)}</div>
      <p className="meta">研究工作流 / Advanced controls</p><div className="quick-action-grid">{QUICK_TASKS.map(([intent, label]) => <button key={intent} onClick={() => onTask(taskAction(intent, targetId), 'quick_action')}>{label}</button>)}</div>
    </section>
    <details><summary>Portfolio · current structured state</summary>{portfolio.data?.map(row => <p key={String(row.problem_id)}>{String(row.problem_id)} · {String(row.title)} · {String(row.research_state || 'unknown')} · Episode {String(row.latest_episode || 'none')} · candidates {String(row.candidate_result_count)}</p>)}</details>
    <details className="maintenance-actions"><summary>资料 / Diagnostics / Export</summary><div className="quick-action-grid">
      {MAINTENANCE_TASKS.map(([intent, label]) => <button key={intent} disabled={!problemId && (intent === 'ADD_SOURCE' || intent === 'EXPORT_RESEARCH_HANDOFF')} onClick={() => onTask(taskAction(intent, targetId), 'quick_action')}>{label}</button>)}
    </div></details>
    <section className="research-chat" aria-label="Research Coordinator"><h2>Research Coordinator</h2>
      <p className="meta">查询研究事实、汇总与调度 · 数学状态以 structured memory / Review 为准</p>
      <div className="chat-messages" role="log">{messages.map((entry, index) => <article key={index}>
        <strong>{entry.role}</strong>
        {entry.role === 'User' ? <p>{entry.text}</p> : <>
          <p className="coordinator-message">{entry.result.message}</p>
          <small>{entry.result.kind}{entry.result.model_used ? ' · coordinator model' : ' · deterministic'}</small>
          {entry.result.actions_executed.map((action, i) => <p key={i}>{action.name === 'stop_research' ? '停止请求已提交' : action.name === 'resume_research' ? '恢复请求已提交' : action.reused ? '已关联现有运行' : '启动请求已提交'} · {action.refs.run_id}</p>)}
          {entry.result.kind === 'CONFIG_REQUIRED' && <p><a href="#research-settings" onClick={() => document.getElementById('research-settings')?.setAttribute('open', '')}>打开 Settings 配置 Coordinator</a></p>}
          {entry.result.kind === 'AMBIGUOUS' && entry.result.choices.map((choice, i) => <button disabled={route.isPending} key={i} onClick={() => choose(entry.result, entry.request, choice)}>{[choice.problem_id, choice.target_id, choice.run_id].filter(Boolean).join(' / ') || '选择目标'}</button>)}
          {entry.result.structured_payload.portfolio?.map(row => <button key={String(row.problem_id)} onClick={() => onProblem?.(String(row.problem_id))}>打开 {String(row.problem_id)}</button>)}
          {entry.result.structured_payload.memory?.map(file => <p key={file.id}>{file.id} · {file.title} · {file.authority}</p>)}
          {entry.result.structured_payload.memory && <button onClick={() => onTask(taskAction('FIND_RELATED_RESEARCH', null, entry.result.structured_payload.query || ''), 'research_chat')}>在 Recall 中查看</button>}
          {entry.result.structured_payload.runs?.map(run => <button key={run.run_id} onClick={() => setActive({ problem_id: run.problem_id, target_id: run.target_id, run_id: run.run_id })}>查看 {run.run_id}</button>)}
        </>}
      </article>)}</div>
      <form onSubmit={e => { e.preventDefault(); if (input.trim()) send(input.trim()) }}>
        <label className="field">任务请求<input aria-label="Research task request" value={input} onChange={e => setInput(e.target.value)} placeholder="总结所有问题进展 / 继续 P2 / 停止这个研究" maxLength={2000} /></label>
        <button disabled={!input.trim() || route.isPending}>发送</button>
      </form>
      {route.isPending && <p role="status">正在查询 / 执行请求…</p>}
      {route.error && <p role="alert" className="error">Coordinator API 暂时不可用；保留已有对话与进度。<button onClick={() => lastRequest && route.mutate(lastRequest)}>重试请求</button></p>}
    </section>
    {children}
    <RunProgress problemId={active?.problem_id || problemId} runId={active?.run_id || undefined}
      onRunChanged={run => { if (run.request?.target) observedRun.current = { run_id: run.run_id, problem_id: run.request.target.problem_id, target_id: run.request.target.node_id } }}
      onOpenEpisode={id => { if (active?.problem_id && active.problem_id !== problemId) onProblem?.(active.problem_id); onOpenEpisode(id) }} />
    <div className="action-row"><button disabled={route.isPending} onClick={() => send('停止当前研究', { name: 'stop_research' })}>停止当前研究</button>
      <button disabled={route.isPending} onClick={() => send('恢复中断研究', { name: 'resume_research' })}>恢复中断研究</button></div>
  </>
}
