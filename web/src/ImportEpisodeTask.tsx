import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import type { EpisodePreflight, UploadResult } from './api'
import { useResearchActions } from './researchActions'

type ImportState = 'WAIT_FILE' | 'PREFLIGHT' | 'INVALID' | 'PREVIEW' | 'IMPORTING' | 'IMPORTED'
const summaryLabels: Record<string, string> = {
  episode_id: 'Episode ID', problem_id: 'Problem', primary_target: 'Primary target',
  records_created: 'Candidate records created', episode_records_created: 'Episodes created',
  canonical_records_created: 'Canonical records created', candidate_relations: 'Candidate relations',
  new_gaps: 'New gaps', new_results: 'New results', revisions: 'Revisions', failed_attempts: 'Failed attempts', authority: 'Review status',
}

export function ImportEpisodeTask({ problemId, onImported, onScout, onUnstructured }: {
  problemId: string; onImported: (result: UploadResult) => void; onScout: () => void
  onUnstructured?: (file: File) => void
}) {
  const actions = useResearchActions(problemId)
  const [state, setState] = useState<ImportState>('WAIT_FILE')
  const [file, setFile] = useState<File | null>(null)
  const [markdown, setMarkdown] = useState('')
  const [preview, setPreview] = useState<EpisodePreflight | null>(null)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const committing = useRef(false)
  useEffect(() => () => { generation.current++ }, [])
  const commit = useMutation({ mutationFn: () => actions.importEpisode(file!, preview!.content_sha256),
    onSuccess: result => { setState('IMPORTED'); onImported(result) },
    onError: error => { setState('PREVIEW'); setError(error.message) },
    onSettled: () => { committing.current = false },
  })
  async function chooseFile(chosen: File) {
    const token = ++generation.current
    setFile(chosen); setPreview(null); setError(''); setState('PREFLIGHT')
    try {
      const result = await actions.preflight(chosen)
      if (token === generation.current) { setPreview(result); setState('PREVIEW') }
    } catch (error) {
      if (token === generation.current) {
        setError(String(error)); setState('INVALID')
        if (/No nonempty supported Episode sections|Numbered Episode|Upload one .md|must be UTF-8 Markdown|front matter/i.test(String(error))) onUnstructured?.(chosen)
      }
    }
  }
  function cancel() { generation.current++; setFile(null); setPreview(null); setError(''); setState('WAIT_FILE') }
  return <section className="task-card" aria-label="Import / Decompose Episode">
    <h2>Import Research Episode</h2><p className="meta">{state} · deterministic parser · Uses LLM: No</p>
    {state !== 'IMPORTED' && <>
      <label className="field">Paste Markdown<textarea aria-label="Episode Markdown" value={markdown} disabled={commit.isPending} onChange={e => { setMarkdown(e.target.value); generation.current++; setPreview(null); setState('WAIT_FILE') }} /></label>
      <button disabled={!markdown.trim() || commit.isPending} onClick={() => void chooseFile(new File([markdown], 'pasted-episode.md', { type: 'text/markdown' }))}>Preview Markdown</button>
    </>}
    {state !== 'IMPORTED' && <label className="upload-target" onDragOver={e => e.preventDefault()} onDrop={e => {
      e.preventDefault(); if (!commit.isPending && e.dataTransfer.files[0]) void chooseFile(e.dataTransfer.files[0])
    }}>选择标准 Research Episode (.md / .txt)
      <input aria-label="Research Episode file" type="file" accept=".md,.txt,text/markdown,text/plain" disabled={commit.isPending}
        onChange={e => { if (e.target.files?.[0]) void chooseFile(e.target.files[0]) }} />
    </label>}
    {state === 'INVALID' && <p>无法可靠识别为支持的 Research Episode。未 Archive、未生成 Proposal、未写 Problem Record。</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {preview && state !== 'IMPORTED' && <>
      <h3>已识别 Research Episode · {preview.filename}</h3>
      <p>Primary Target: {preview.target_id || '未提供；使用已解析对象各自的 Target'}</p>
      <p>{Object.entries(preview.parse_summary).map(([kind, count]) => `${count} ${kind}`).join(' · ')}</p>
      <p>Explicit Relations: {preview.parse_summary.relation || 0}</p>
      <details><summary>Preview source</summary><pre>{preview.body}</pre></details>
      <button disabled={state !== 'PREVIEW' || commit.isPending} onClick={() => { if (committing.current) return; committing.current = true; setState('IMPORTING'); commit.mutate() }}>确认导入并拆解</button>
    </>}
    {state !== 'IMPORTED' && <button disabled={commit.isPending} onClick={cancel}>取消</button>}
    {state === 'IMPORTED' && <>
      <p>已归档 {commit.data?.episode.episode_id}；{commit.data?.candidate_count} 个 Proposals（导入不自动审核）。</p>
      {commit.data?.duplicate && <p>已有相同内容，已复用 Episode；未重复创建候选。</p>}
      {commit.data?.summary && <dl className="import-summary">{Object.entries(commit.data.summary).map(([key, value]) => <div key={key}><dt>{summaryLabels[key] || key}</dt><dd>{value ?? 'not declared'}</dd></div>)}</dl>}
      <p>是否独立运行 Relation Scout 检查与历史对象的可能 Logical Relations？</p>
      <button onClick={onScout}>运行 Scout</button><button onClick={cancel}>稍后 / 导入下一份</button>
    </>}
  </section>
}
