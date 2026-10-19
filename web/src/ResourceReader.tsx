import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Markdown } from './Markdown'
import { api, type RecallFile, type ResearchIntent, type SourceLocator } from './api'
import { SourceDigestReader, locatorLabel } from './SourceDigest'
import { taskAction } from './researchActions'

export function ResourceReader({ problemId, file, digestView = false, digestId = null, onDigestView, onDigestSelect, onTask }: {
  problemId: string; file: RecallFile; digestView?: boolean; digestId?: string | null
  onDigestView?: (value: boolean) => void; onDigestSelect?: (id: string) => void; onTask?: (intent: ResearchIntent) => void
}) {
  const query = useQuery({ queryKey: ['original-resource', problemId, file.problem_id, file.kind, file.artifact_id], queryFn: () => api.readOriginalFile(problemId, file) })
  const [text, setText] = useState('')
  const [pdf, setPdf] = useState('')
  const [locator, setLocator] = useState<SourceLocator | null>(null)
  const digestAvailable = !!onTask && file.problem_id === problemId && file.artifact_id.startsWith('PAPER-') && /\.(pdf|md|txt)$/i.test(file.path || '')
  useEffect(() => {
    let active = true
    setText(''); setPdf('')
    if (!query.data) return
    if (file.path?.toLowerCase().endsWith('.pdf')) {
      const url = URL.createObjectURL(new Blob([query.data], { type: 'application/pdf' })); setPdf(url)
      return () => URL.revokeObjectURL(url)
    }
    void query.data.text().then(value => { if (active) setText(value) })
    return () => { active = false }
  }, [query.data, file.path])
  return <section aria-label="Original Resource Reader"><h1>{file.title}</h1>
    <p className="meta">{file.artifact_id} · {file.path} · {file.authority} · {file.state.research_state}</p>
    <p className="meta">Provenance: {file.provenance.join('; ')}</p>
    {digestAvailable && <div className="action-row"><button aria-pressed={!digestView} onClick={() => onDigestView?.(false)}>Source</button><button aria-pressed={digestView} onClick={() => onTask!(taskAction('OPEN_SOURCE_DIGEST', file.artifact_id))}>Digest</button><button onClick={() => onTask!(taskAction('DIGEST_SOURCE', file.artifact_id))}>Digest Source</button></div>}
    {digestAvailable && digestView ? <SourceDigestReader problemId={problemId} sourceId={file.artifact_id} digestId={digestId} onSelect={id => onDigestSelect?.(id)} onTask={onTask!} onLocate={value => { setLocator(value); onDigestView?.(false) }} /> : <>
    {locator && <p role="status">Source location: {locatorLabel(locator)}</p>}
    <a href={api.originalFileUrl(problemId, file)} download>Download original {file.artifact_id}</a>
    {query.error && <p className="error" role="alert">{String(query.error)}</p>}
    {pdf ? <iframe className="pdf-reader" src={`${pdf}${locator?.page ? `#page=${locator.page}` : ''}`} title={file.title} /> : file.path?.toLowerCase().endsWith('.txt') ? <pre className="raw-source">{text}</pre>
      : <Markdown text={text} />}
    </>}
  </section>
}
