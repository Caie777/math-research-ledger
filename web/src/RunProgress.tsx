import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AgentRun, type ResearchRunProgress } from './api'

export function useRunProgress(problemId: string, runId: string | null | undefined) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['agent-progress', problemId, runId],
    queryFn: () => api.agentProgress(problemId, runId!), enabled: !!problemId && !!runId,
    refetchInterval: query => {
      const metadata = queryClient.getQueryData<AgentRun>(['agent-run', problemId, runId])
      const attached = metadata?.status === 'running' && metadata.executor_attached === true
      return query.state.data?.status === 'finished' && !attached ? false : 1000
    },
    retry: false })
  useEffect(() => {
    if (query.data?.status !== 'finished') return
    // Fetch the final Episode/output metadata once, then stop all run polling.
    void queryClient.invalidateQueries({ queryKey: ['agent-run', problemId, runId] })
    void queryClient.invalidateQueries({ queryKey: ['research-runs', problemId] })
  }, [problemId, runId, query.data?.status, query.data?.updated_at, queryClient])
  const metadata = queryClient.getQueryData<AgentRun>(['agent-run', problemId, runId])
  useEffect(() => {
    // Resume can be accepted while its old terminal snapshot is still visible.
    // Read the final projection once metadata commits a newer completion.
    if (metadata?.status === 'finished' && metadata.ended_at && query.data?.finished_at &&
      Date.parse(metadata.ended_at) !== Date.parse(query.data.finished_at)) {
      void queryClient.invalidateQueries({ queryKey: ['agent-progress', problemId, runId] })
    }
  }, [problemId, runId, metadata?.status, metadata?.ended_at, query.data?.finished_at, queryClient])
  return query
}

export function useActiveRun(problemId: string, requestedRunId?: string) {
  const runs = useQuery({ queryKey: ['research-runs', problemId], queryFn: () => api.agentRuns(problemId), enabled: !!problemId && !requestedRunId,
    refetchInterval: query => {
      const selected = query.state.data?.find(run => run.executor_attached) || query.state.data?.[0]
      return selected?.status === 'running' ? 4000 : false
    } })
  const id = requestedRunId || runs.data?.find(run => run.executor_attached)?.run_id || runs.data?.[0]?.run_id
  const progress = useRunProgress(problemId, id)
  const run = useQuery({ queryKey: ['agent-run', problemId, id], queryFn: () => api.agentRun(problemId, id!), enabled: !!id,
    refetchInterval: query => (query.state.data?.status === 'running' && query.state.data.executor_attached === true || (progress.data?.status || query.state.data?.status) === 'running') ? 1000 : false })
  return { run: run.data || runs.data?.find(run => run.run_id === id), progress: progress.data,
    progressError: progress.error, error: run.error || runs.error }
}

function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export function ProgressDetails({ progress, error }: { progress?: ResearchRunProgress; error: Error | null }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (progress?.status !== 'running') return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [progress?.status, progress?.run_id])
  const phaseLabels: Record<ResearchRunProgress['current_phase'], string> = {
    initializing: 'Initializing', loading_context: 'Loading context', researching: 'Researching',
    using_tools: 'Using tools', checkpointing: 'Checkpointing', finalizing: 'Finalizing', stopping: 'Stopping', terminal: 'Terminal',
  }
  const idle = progress ? now - Date.parse(progress.last_activity_at) : 0
  return <div aria-label="Durable Research Progress">
    {error && <p className="error" role="alert">Progress stale / API error：{error.message}。保留最后一次成功状态。</p>}
    {!progress && !error && <p className="meta">Loading persisted progress…</p>}
    {progress && <>
      <p>{progress.status.toUpperCase()} · {phaseLabels[progress.current_phase]}{progress.stop_requested ? ' · Stop requested' : ''}</p>
      <p>Elapsed time: {duration((progress.finished_at ? Date.parse(progress.finished_at) : now) - Date.parse(progress.started_at))}</p>
      <p>Step {progress.step_count} · Model {progress.model_call_count} · Tools {progress.tool_call_count}</p>
      <p>Last activity: {progress.last_activity_at} · Last checkpoint: {progress.last_checkpoint_at || '—'}</p>
      <p className="meta">Checkpoints {progress.checkpoint_count} · Public events {progress.public_event_count}</p>
      {progress.status === 'running' && idle > 60000 && <p role="status">No new activity for {duration(idle)}</p>}
      {progress.latest_public_progress && <p aria-label="Latest public progress">Latest public progress: {progress.latest_public_progress.summary}</p>}
      <p className="meta">Budget: {progress.budget.max_agent_steps} steps · {progress.budget.max_model_calls} model calls · {progress.budget.max_tool_calls} tool calls · {progress.budget.max_wall_time}s</p>
      {progress.stop_reason && <p>Stop reason: {progress.stop_reason}</p>}
      {progress.error_type && <p role="alert">Error type: {progress.error_type}</p>}
      {progress.source === 'reconstructed' && <p className="meta">Legacy progress reconstructed (read-only){progress.snapshot_error ? ' · Snapshot unavailable, stale or invalid' : ''}</p>}
    </>}
  </div>
}

export function RunProgress({ problemId, runId, onOpenEpisode, onRunChanged }: {
  problemId: string; runId?: string; onOpenEpisode: (id: string) => void; onRunChanged?: (run: AgentRun) => void
}) {
  const queryClient = useQueryClient()
  const { run, progress, progressError, error } = useActiveRun(problemId, runId)
  const stop = useMutation({ mutationFn: () => api.stopAgent(problemId, run!.run_id), retry: false,
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['agent-progress', problemId, run?.run_id] }) } })
  const episode = useQuery({ queryKey: ['episode', problemId, run?.episode_id], queryFn: () => api.episode(problemId, run!.episode_id!), enabled: !!run?.episode_id })
  useEffect(() => {
    if (!run) return
    onRunChanged?.(run)
    if (run.episode_id || run.status !== 'running') {
      for (const key of ['episodes', 'candidates', 'objects', 'agent-state', 'related-memory']) {
        void queryClient.invalidateQueries({ queryKey: [key, problemId] })
      }
    }
  }, [problemId, run?.run_id, run?.status, run?.episode_id])
  return <section className="active-task" aria-label="Active Task / Progress">
    <h2>Active Task / Progress</h2>
    {error && <p className="error" role="alert">Run metadata stale / API error: {String(error)}</p>}
    {!run && !error && <p className="meta">暂无已保存的研究 run。</p>}
    {run && <>
      <p>{run.run_id}{run.executor_attached === false && run.status === 'running' ? ' · INTERRUPTED / detached' : ''}</p>
      <ProgressDetails progress={progress} error={progressError} />
      {progress && <p className="meta">Problem {progress.problem_id} / Target {progress.target_id}</p>}
      {progress?.status === 'running' && <button disabled={stop.isPending || progress.stop_requested} onClick={() => stop.mutate()}>停止此 run</button>}
      {stop.error && <p className="error" role="alert">停止请求暂时失败，请重试。</p>}
      <p className="meta">Target {run.request?.target.node_id} · {run.request?.model} / {run.request?.effort} · provisional {run.request?.include_provisional ? 'ON' : 'OFF'}</p>
      {run.episode_id && <>
        <button onClick={() => onOpenEpisode(run.episode_id!)}>中栏打开 {run.episode_id}</button>
        <p>{Object.entries(episode.data?.parse_summary || {}).map(([kind, count]) => `${count} ${kind}`).join(' · ')} · {run.candidate_ids.length} 个输出 Proposals</p>
      </>}
      <a href={api.agentAuditUrl(problemId, run.run_id)} download>Run audit</a>
    </>}
  </section>
}
