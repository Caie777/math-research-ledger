import { useState } from 'react'
import type { EpisodeSummary, RecallFile, ObjectKind, ResearchObject } from './api'
import { OBJECT_KINDS, type Selection } from './researchState'

// Display existing Resolver fields only; these colors confer no authority.
export function explorerState(object: ResearchObject) {
  const state = object.state
  if (!state) return { tone: 'unknown', label: object.status }
  const label = `${state.research_state} · ${state.authority} · ${state.verification}`
  const tone = ['REFUTED', 'INVALIDATED', 'HISTORICAL', 'SUPERSEDED'].includes(state.research_state)
    ? 'inactive'
    : state.authority === 'PROVISIONAL' ? 'pending'
    : state.research_state === 'RESOLVED' ? 'resolved'
    : ['OPEN', 'PARTIALLY_RESOLVED', 'CURRENT', 'REVISED'].includes(state.research_state) ? 'active' : 'unknown'
  return { tone, label }
}

const groups = [...OBJECT_KINDS].sort((a, b) =>
  ['claim', 'gap', 'proof', 'counterexample', 'evidence', 'failed_attempt'].indexOf(a.kind)
  - ['claim', 'gap', 'proof', 'counterexample', 'evidence', 'failed_attempt'].indexOf(b.kind))

export function ResearchExplorer({ episodes, sources = [], objects, selection, onEpisode, onObject, onSource }: {
  episodes: EpisodeSummary[]
  objects: Partial<Record<ObjectKind, ResearchObject[]>>
  sources?: RecallFile[]
  onSource?: (file: RecallFile) => void
  selection: Selection | null
  onEpisode: (id: string) => void
  onObject: (kind: ObjectKind, id: string) => void
}) {
  const [filter, setFilter] = useState('')
  const [sections, setSections] = useState({ files: true, objects: true })
  const [expanded, setExpanded] = useState<Partial<Record<ObjectKind, boolean>>>({ claim: true, gap: true })
  const query = filter.trim().toLocaleLowerCase()
  const matches = (...values: string[]) => values.some(value => value.toLocaleLowerCase().includes(query))
  const files = episodes.filter(({ episode }) => matches(episode.episode_id, episode.source_filename))
  const rawSources = sources.filter(source => matches(source.artifact_id, source.title))
  const filteredGroups = groups.map(group => ({ ...group,
    rows: (objects[group.kind] || []).filter(object => matches(object.id, object.title)),
  }))
  const objectCount = filteredGroups.reduce((count, group) => count + group.rows.length, 0)
  const filesOpen = !!query || sections.files
  const objectsOpen = !!query || sections.objects

  return <>
    <label className="field explorer-filter">
      <span className="sr-only">Filter files and objects</span>
      <input aria-label="Filter files and objects" placeholder="Filter files and objects..."
        value={filter} onChange={event => setFilter(event.target.value)} />
    </label>
    <div className="tree-scroll">
      <section className="explorer-section" aria-labelledby="research-files-heading">
        <h2 id="research-files-heading"><button className="explorer-disclosure" aria-expanded={filesOpen}
          aria-controls="research-files-list" onClick={() => setSections(current => ({ ...current, files: !current.files }))}>
          <span aria-hidden="true">{filesOpen ? '▾' : '▸'}</span>Research Files<small>{files.length + rawSources.length}</small>
        </button></h2>
        {filesOpen && <div id="research-files-list">
          {rawSources.map(source => <button key={source.artifact_id} title={`${source.title} · ${source.artifact_id}`}
            aria-label={`${source.artifact_id} · ${source.title}`} aria-pressed={selection?.type === 'resource' && selection.id === source.artifact_id}
            className={`explorer-row explorer-file ${selection?.type === 'resource' && selection.id === source.artifact_id ? 'selected' : ''}`} onClick={() => onSource?.(source)}>
            <span className="explorer-file-icon" aria-hidden="true">▤</span><span className="explorer-title">{source.title}</span>
          </button>)}
          {files.map(({ episode }) => {
            const selected = selection?.type === 'episode' && selection.id === episode.episode_id
            return <button key={episode.episode_id} title={`${episode.source_filename} · ${episode.episode_id}`}
              aria-label={`${episode.episode_id} · ${episode.source_filename}`} aria-pressed={selected}
              className={`explorer-row explorer-file ${selected ? 'selected' : ''}`} onClick={() => onEpisode(episode.episode_id)}>
              <span className="explorer-file-icon" aria-hidden="true">▤</span>
              <span className="explorer-title">{episode.source_filename || episode.episode_id}</span>
            </button>
          })}
          {!files.length && !rawSources.length && <p className="explorer-empty">{query ? 'No matching files.' : 'No research files.'}</p>}
        </div>}
      </section>
      <section className="explorer-section" aria-labelledby="research-objects-heading">
        <h2 id="research-objects-heading"><button className="explorer-disclosure" aria-expanded={objectsOpen}
          aria-controls="research-objects-list" onClick={() => setSections(current => ({ ...current, objects: !current.objects }))}>
          <span aria-hidden="true">{objectsOpen ? '▾' : '▸'}</span>Research Objects<small>{objectCount}</small>
        </button></h2>
        {objectsOpen && <div id="research-objects-list">
          {filteredGroups.filter(group => !query || group.rows.length).map(({ kind, label, rows }) => {
            const open = !!query || !!expanded[kind]
            return <section className="explorer-group" key={kind} aria-labelledby={`explorer-${kind}-heading`}>
              <h3 id={`explorer-${kind}-heading`}><button className="explorer-disclosure" aria-expanded={open}
                aria-controls={`explorer-${kind}-list`} onClick={() => setExpanded(current => ({ ...current, [kind]: !current[kind] }))}>
                <span aria-hidden="true">{open ? '▾' : '▸'}</span>{label}<small>{rows.length}</small>
              </button></h3>
              {open && <div id={`explorer-${kind}-list`}>{rows.map(object => {
                const selected = selection?.type === 'object' && selection.kind === kind && selection.id === object.id
                const state = explorerState(object)
                return <button key={object.id} title={object.title} aria-label={`${object.id} · ${object.title}`}
                  aria-pressed={selected} className={`explorer-row explorer-object ${selected ? 'selected' : ''}`}
                  onClick={() => onObject(kind, object.id)}>
                  <span className={`explorer-state ${state.tone}`} title={state.label} aria-hidden="true" />
                  <span className="explorer-id">{object.id}</span><span className="explorer-title">{object.title}</span>
                </button>
              })}</div>}
            </section>
          })}
          {query && !objectCount && <p className="explorer-empty">No matching objects.</p>}
        </div>}
      </section>
    </div>
  </>
}
