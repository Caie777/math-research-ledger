import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type ResearchMapNode, type ResearchIntent } from './api'
import { taskAction } from './researchActions'
import { supportsCritique } from './CritiquePanel'

const LABELS = { problem: 'Problem', claim: 'Claim', gap: 'Gap', proof: 'Proof Attempt', counterexample: 'Counterexample', evidence: 'Evidence', failed_attempt: 'Failed Attempt' }
const FILTERS = ['All', 'Open Gaps', 'Active Routes', 'Failed Routes'] as const
type Filter = typeof FILTERS[number]

function matches(node: ResearchMapNode, filter: Filter) {
  if (filter === 'Open Gaps') return node.type === 'gap' && ['OPEN', 'PARTIALLY_RESOLVED'].includes(node.status)
  if (filter === 'Active Routes') return node.type === 'proof' && node.group === 'current'
  if (filter === 'Failed Routes') return node.group === 'failed_routes'
  return true
}

/** Lanes organize record types, not parentage. Only supplied authoritative edges connect nodes. */
export function ResearchMap({ problemId, onOpen, onTask }: {
  problemId: string; onOpen: (node: ResearchMapNode) => void; onTask: (intent: ResearchIntent) => void
}) {
  const [filter, setFilter] = useState<Filter>('All')
  const [history, setHistory] = useState(false)
  const [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['research-map', problemId], queryFn: () => api.researchMap(problemId), enabled: !!problemId })
  const map = query.data
  const visible = (map?.nodes || []).filter(node => node.type !== 'problem' && (node.is_primary || history || node.group !== 'historical') && matches(node, filter) && `${node.id} ${node.title}`.toLowerCase().includes(search.trim().toLowerCase()))
  const positions = new Map<string, { x: number; y: number }>()
  const rows = [0, 0, 0]
  for (const node of visible) {
    const lane = node.is_primary || node.type === 'claim' ? 0 : node.type === 'gap' ? 1 : 2
    positions.set(node.id, { x: lane * 300 + 12, y: rows[lane]++ * 272 + 46 })
  }
  const edges = (map?.edges || []).filter(edge => positions.has(edge.source) && positions.has(edge.target))
  const height = Math.max(1, ...rows) * 272 + 56
  if (!problemId) return <p>Select a Problem to view its Research Map.</p>
  return <section className="research-map" aria-label="Research Map">
    <header><h2>Research Map</h2><p className="meta">Research Map · Uses LLM: No</p><p>Current records and confirmed relations. Research resolution and Human acceptance are separate from theorem verification.</p>
      {map?.nodes.find(node => node.type === 'problem') && <p className="map-problem">Problem · {map.problem_id} · {map.nodes.find(node => node.type === 'problem')!.title} · {map.nodes.find(node => node.type === 'problem')!.status} · {map.nodes.find(node => node.type === 'problem')!.authority}</p>}
      <button onClick={() => void query.refetch()} disabled={query.isFetching}>Refresh map</button>
    </header>
    {query.isPending && <p role="status">Loading Research Map…</p>}
    {query.error && <p role="alert">Could not load Research Map: {query.error instanceof Error ? query.error.message : String(query.error)}</p>}
    {map && <>
      {map.warnings.map(warning => <p className="map-warning" key={warning}>{warning}</p>)}
      <div className="map-controls" role="group" aria-label="Research Map filters">
        {FILTERS.map(name => <button key={name} aria-pressed={filter === name} onClick={() => setFilter(name)}>{name}</button>)}
        <label><input type="checkbox" checked={history} onChange={e => setHistory(e.target.checked)} />Show Historical</label>
        <label>Find node<input aria-label="Find map node" value={search} onChange={e => setSearch(e.target.value)} /></label>
      </div>
      {visible.length === 0 ? <p>{(map.nodes.length <= 1) ? 'No structured research map yet. Review or add research records to populate it.' : 'No nodes match these filters. Historical records remain available through Show Historical and the Reader.'}</p> : <>
        <p className="map-legend">Type lanes are navigation groups, not inferred parent-child relations. Solid arrows show recorded relations/dependencies only. Failed routes stay visible; Historical is collapsed by default.</p>
        <div className="map-viewport" tabIndex={0} aria-label="Research structure diagram">
          <div className="map-canvas" style={{ height, width: 912 }}>
            {['Primary Target / Claims', 'Gaps', 'Routes / Findings'].map((title, lane) => <h3 className="map-lane" style={{ left: lane * 300 + 12 }} key={title}>{title}</h3>)}
            <svg className="map-connections" width="912" height={height} aria-hidden="true">
              <defs><marker id={`map-arrow-${problemId}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
              {edges.map(edge => {
                const from = positions.get(edge.source)!, to = positions.get(edge.target)!
                const same = from.x === to.x, right = from.x <= to.x
                const x1 = from.x + (right ? 264 : 0), x2 = to.x + (same || !right ? 264 : 0)
                const bend = same ? 40 : (right ? 28 : -28)
                return <path key={`${edge.source}-${edge.relation_type}-${edge.target}`} d={`M ${x1} ${from.y + 40} C ${x1 + bend} ${from.y + 40}, ${x2 + (same ? bend : -bend)} ${to.y + 40}, ${x2} ${to.y + 40}`} markerEnd={`url(#map-arrow-${problemId})`}><title>{edge.source} {edge.relation_type} {edge.target} · {edge.authority}</title></path>
              })}
            </svg>
            {visible.map(node => <article key={node.id} className={`map-node map-${node.type} ${node.is_primary ? 'map-primary' : ''} map-${node.group}`} style={{ left: positions.get(node.id)!.x, top: positions.get(node.id)!.y }} aria-label={`${LABELS[node.type]} ${node.id}`}>
              <div className="map-node-kind">{node.is_primary && <strong>Primary Target · </strong>}{LABELS[node.type]} · {node.group === 'failed_routes' ? 'Failed Route' : node.group === 'historical' ? 'Historical' : 'Current'}</div>
              <button className="map-open" title={node.title} onClick={() => onOpen(node)}><span>{node.id}</span><strong>{node.title}</strong></button>
              <p className="map-state">{node.status} · {node.review} · {node.authority}<br />Verification: {node.verification}</p>
              {node.warnings.length > 0 && <span className="map-node-warning" title={node.warnings.join('\n')}>⚠ {node.warnings.length} state warning{node.warnings.length === 1 ? '' : 's'} · inspect Reader</span>}
              <div className="map-node-actions">
                {node.research_target_id && <button title={`Prepare research on ${node.research_target_id}; explicit confirmation still required`} onClick={() => onTask(taskAction('CONTINUE_RESEARCH', node.research_target_id))}>Continue from here</button>}
                <button onClick={() => onTask(taskAction('FIND_RELATED_RESEARCH', node.id))}>Find Related</button>
                {node.authority === 'CANONICAL' && !node.episode_id && supportsCritique(node.type) && <button aria-label="Critique this result" onClick={() => onTask(taskAction('CRITIQUE_RESEARCH_RESULT', node.id))}>Critique</button>}
                {!!node.critique_count && <button onClick={() => onTask(taskAction('CRITIQUE_RESEARCH_RESULT', node.id))}>{node.critique_count} critique{node.critique_count === 1 ? '' : 's'}</button>}
              </div>
              {node.type === 'proof' && node.research_target_id && <small>Target: {node.research_target_id}</small>}
            </article>)}
          </div>
        </div>
        <details className="map-edge-list" open><summary>Recorded connections ({edges.length})</summary>
          {edges.length === 0 && <p>No recorded connections among the visible nodes.</p>}
          <ul>{edges.map(edge => <li key={`${edge.source}-${edge.relation_type}-${edge.target}`}>
            <button onClick={() => onOpen(map.nodes.find(n => n.id === edge.source)!)}>{edge.source}</button>
            <span> → {edge.relation_type} → </span><button onClick={() => onOpen(map.nodes.find(n => n.id === edge.target)!)}>{edge.target}</button>
            <small> · {edge.authority}</small>
          </li>)}</ul>
        </details>
      </>}
    </>}
  </section>
}
