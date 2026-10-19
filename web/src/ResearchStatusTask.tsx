import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type EpisodeSummary, type ResearchObject } from './api'
import { useActiveRun } from './RunProgress'

export function ResearchStatusTask({ problemId, targetId, targets, episodes, onOpenEpisode }: {
  problemId: string; targetId: string | null; targets: ResearchObject[]; episodes: EpisodeSummary[]; onOpenEpisode: (id: string) => void
}) {
  const [target, setTarget] = useState(targetId || '')
  useEffect(() => setTarget(targetId || ''), [targetId])
  const state = useQuery({ queryKey: ['agent-state', problemId, target, true], queryFn: () => api.researchState(problemId, target, true), enabled: targets.some(t => t.id === target) })
  const { run } = useActiveRun(problemId)
  return <section className="task-card" aria-label="Research Status"><h2>研究状态</h2>
    <label className="field">Target Claim / Gap<select aria-label="Status target" value={target} onChange={e => setTarget(e.target.value)}><option value="">Choose a target</option>{targets.map(t => <option key={t.id} value={t.id}>{t.id} · {t.title}</option>)}</select></label>
    {state.data && <><p>Resolver / Current Research State: {state.data.research_status}</p><pre>{state.data.markdown}</pre>
      {state.data.latest_handoff_episode_id && <button onClick={() => onOpenEpisode(state.data!.latest_handoff_episode_id!)}>Latest Research Handoff {state.data.latest_handoff_episode_id}</button>}</>}
    {state.error && <p className="error" role="alert">{String(state.error)}</p>}
    <p>{episodes.reduce((total, episode) => total + episode.pending, 0)} pending Proposals</p>
    {episodes[0] && <button onClick={() => onOpenEpisode(episodes[0].episode.episode_id)}>Latest Episode {episodes[0].episode.source_filename}</button>}
    {run && <p>Agent {run.run_id} · {run.status} · {run.stop_reason || run.current_action}</p>}
  </section>
}
