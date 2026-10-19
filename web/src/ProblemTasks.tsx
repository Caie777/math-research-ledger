import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, type CreatedProblem, type ResearchIntent, type ProblemInput, type ProblemPreview, type ResearchObject, type UploadResult } from './api'
import { taskAction, useResearchActions } from './researchActions'
import { ImportEpisodeTask } from './ImportEpisodeTask'

export function NewProblemTask({ problemId, onCreated, onOpen, onAddSource, onResearch }: {
  problemId: string; onCreated: (result: CreatedProblem) => void; onOpen: (result: CreatedProblem) => void
  onAddSource: (result: CreatedProblem) => void; onResearch: (result: CreatedProblem) => void
}) {
  const actions = useResearchActions(problemId)
  const [step, setStep] = useState<'ENTER_METADATA' | 'OPTIONAL_SOURCE' | 'PREVIEW' | 'CONFIRM' | 'CREATED'>('ENTER_METADATA')
  const [metadata, setMetadata] = useState<ProblemInput>({ title: '', statement: '', target_type: 'Claim', description: '' })
  const [files, setFiles] = useState<File[]>([])
  const [preview, setPreview] = useState<ProblemPreview | null>(null)
  const preflight = useMutation({ mutationFn: () => actions.previewProblem(metadata, files), onSuccess: result => { setPreview(result); setStep('PREVIEW') } })
  const create = useMutation({ mutationFn: () => actions.createProblem(metadata, files, preview!.digest), onSuccess: result => { setStep('CREATED'); onCreated(result) } })
  const update = (patch: Partial<ProblemInput>) => { setMetadata(current => ({ ...current, ...patch })); setPreview(null) }
  return <section className="task-card" aria-label="New Problem Onboarding"><h2>新建研究问题</h2>
    <p className="meta">{create.isPending ? 'CREATING' : step}</p>
    {step === 'ENTER_METADATA' && <form onSubmit={event => { event.preventDefault(); setStep('OPTIONAL_SOURCE') }}>
      <label className="field">Problem title<input aria-label="Problem title" required maxLength={300} value={metadata.title} onChange={e => update({ title: e.target.value })} /></label>
      <label className="field">Primary target statement<textarea aria-label="Primary target statement" required maxLength={20000} value={metadata.statement} onChange={e => update({ statement: e.target.value })} /></label>
      <label className="field">Target type<select aria-label="Target type" value={metadata.target_type} onChange={e => update({ target_type: e.target.value as 'Claim' | 'Gap' })}><option>Claim</option><option>Gap</option></select></label>
      <label className="field">Short description (optional)<textarea aria-label="Short description" maxLength={2000} value={metadata.description} onChange={e => update({ description: e.target.value })} /></label>
      <button disabled={!metadata.title.trim() || !metadata.statement.trim()}>下一步：资料</button>
    </form>}
    {step === 'OPTIONAL_SOURCE' && <>
      <label className="field">Optional source files<input aria-label="Optional source files" type="file" accept=".md,.txt,.pdf" multiple onChange={e => { setFiles(Array.from(e.target.files || [])); setPreview(null) }} /></label>
      <p className="meta">原始资料单独保存，不自动提取 Claim 或拆解 Episode。最多 10 文件，每个 10 MiB。</p>
      <button onClick={() => setStep('ENTER_METADATA')}>返回</button><button disabled={preflight.isPending} onClick={() => preflight.mutate()}>预览创建</button>
    </>}
    {(step === 'PREVIEW' || step === 'CONFIRM') && preview && <>
      <h3>准备创建研究问题</h3><dl><dt>Title</dt><dd>{preview.title}</dd><dt>Primary Target</dt><dd className="preserve-lines">{preview.statement}</dd>
        <dt>Type</dt><dd>{preview.target_type}</dd><dt>Description</dt><dd>{preview.description || '—'}</dd><dt>Sources</dt><dd>{preview.source_count} files</dd></dl>
      {preview.sources.map((source, index) => <p className="meta" key={index}>{source.filename} · {source.size} bytes</p>)}
      <p>初始目标未验证 / open。确认创建后才写入。</p>
      <button disabled={create.isPending} onClick={() => { setPreview(null); setStep('ENTER_METADATA') }}>取消</button>
      <button disabled={create.isPending} onClick={() => { setStep('CONFIRM'); create.mutate() }}>确认创建</button>
    </>}
    {step === 'CREATED' && create.data && <><p role="status">问题已创建。{create.data.problem_id} · {create.data.target_id} · {create.data.status}</p>
      <button onClick={() => onOpen(create.data!)}>打开目标</button><button onClick={() => onAddSource(create.data!)}>添加资料</button><button onClick={() => onResearch(create.data!)}>开始自动研究</button>
    </>}
    {(preflight.error || create.error) && <p className="error" role="alert">{(preflight.error || create.error)?.message}</p>}
  </section>
}

export function AddSourceTask({ problemId, onSaved, onImported, onTask }: {
  problemId: string; onSaved: () => void | Promise<void>
  onImported?: (result: UploadResult) => void; onTask?: (intent: ResearchIntent) => void
}) {
  const actions = useResearchActions(problemId)
  const [mode, setMode] = useState('standard')
  const [file, setFile] = useState<File | null>(null)
  const save = useMutation({ mutationFn: (_: { digest: boolean }) => actions.addSource(file!), onSuccess: async (result, request) => {
    await onSaved()
    if (request.digest) onTask?.(taskAction('DIGEST_SOURCE', result.source_id))
  } })
  return <section className="task-card" aria-label="Add Source Material"><h2>Add Source</h2>
    <label className="field">Source type<select aria-label="Source type" value={mode} disabled={save.isPending} onChange={e => { setMode(e.target.value); setFile(null); save.reset() }}>
      <option value="standard">Standardized Research Document [Recommended]</option><option value="pdf">Raw PDF</option><option value="other">Other Source</option>
    </select></label>
    {mode === 'standard' && !file ? <ImportEpisodeTask problemId={problemId} onImported={result => onImported?.(result)} onScout={() => onTask?.(taskAction('LOGICAL_RELATIONS'))} onUnstructured={setFile} /> : <>
    <p className="meta">{problemId} · 不作为 Episode / Proposal / Claim / Proof；不会自动拆解。</p>
    {mode === 'standard' && <p>This source does not match the structured research-document format.</p>}
    {mode !== 'standard' && <label className="field">Source file<input aria-label="Source file" type="file" accept={mode === 'pdf' ? '.pdf' : '.md,.txt,.pdf'} disabled={save.isPending} onChange={e => { setFile(e.target.files?.[0] || null); save.reset() }} /></label>}
    {file && <p>{file.name} · {file.size} bytes</p>}
    <p className="meta">Keep as Source Only · Uses LLM: No</p>
    <button disabled={!file || save.isPending || save.isSuccess} onClick={() => save.mutate({ digest: false })}>Keep as Source Only</button>
    {onTask && <><p className="meta">Use AI Source Digest · Uses LLM: Yes · Role: Source Digest · Context: selected source</p>
      <button disabled={!file || save.isPending} onClick={() => {
        if (save.data) onTask(taskAction('DIGEST_SOURCE', save.data.source_id))
        else save.mutate({ digest: true })
      }}>Use AI Source Digest</button></>}
    {save.data && <p role="status">已保存 {save.data.source_id} · {save.data.filename}，可在 Research Files / Search / Recall 阅读。</p>}
    {save.error && <p role="alert" className="error">{save.error.message}</p>}
    </>}
  </section>
}

export function MaintenanceTask({ intent, problemId, targets }: { intent: ResearchIntent; problemId: string; targets: ResearchObject[] }) {
  const [target, setTarget] = useState(intent.target_id || '')
  const health = useMutation({ mutationFn: api.systemHealth })
  const snapshot = useMutation({ mutationFn: api.downloadSnapshot })
  const handoff = useMutation({ mutationFn: () => api.downloadHandoff(problemId, target) })
  const verify = useMutation({ mutationFn: api.verifySnapshot })
  return <section className="task-card" aria-label="Workspace Maintenance"><h2>{intent.intent === 'SYSTEM_HEALTH' ? 'System Health' : intent.intent === 'EXPORT_RESEARCH_HANDOFF' ? 'Export Research Handoff' : 'Workspace Snapshot'}</h2>
    {intent.intent === 'SYSTEM_HEALTH' ? <>
      <p className="meta">只读诊断；Codex 初始化与临时 Python 沙盒探测不启动模型 turn。Optional 工具缺失显示 warning。</p>
      <button disabled={health.isPending} onClick={() => health.mutate()}>检查系统状态</button>
      {health.data && <><p role="status">{health.data.status} · {health.data.protocol === 'freeze-v1' ? 'frontend/backend compatible' : 'protocol mismatch'}</p>
        <ul>{health.data.checks.map(check => <li key={check.name}><strong>{check.status === 'ok' ? '✓' : check.status === 'warning' ? '○' : '×'} {check.name}</strong> · {check.detail}</li>)}</ul></>}
    </> : intent.intent === 'EXPORT_RESEARCH_HANDOFF' ? <>
      <label className="field">Handoff target<select aria-label="Handoff target" value={target} onChange={e => { setTarget(e.target.value); handoff.reset() }}><option value="">选择 Claim / Gap</option>
        {targets.map(object => <option key={object.id} value={object.id}>{object.id} · {object.title}</option>)}</select></label>
      <p className="meta">按已有 Current State / Handoff / Episode / Resolver / artifacts 组装；缺失文件记录在 manifest，不调用模型。</p>
      <button disabled={!target || handoff.isPending} onClick={() => handoff.mutate()}>下载研究交接包</button>
    </> : <>
      <p className="meta">导出持久 .math-research 状态，认证信息需单独配置。验证不会恢复或覆盖工作区。</p>
      <button disabled={snapshot.isPending} onClick={() => snapshot.mutate()}>下载工作区快照</button>
      <label className="field">Verify Snapshot<input aria-label="Verify Snapshot" type="file" accept=".zip" disabled={verify.isPending} onChange={e => { if (e.target.files?.[0]) verify.mutate(e.target.files[0]) }} /></label>
      {verify.data && <p role="status">SHA256 验证通过 · {verify.data.file_count} files</p>}
    </>}
    {(snapshot.isSuccess || handoff.isSuccess) && <p role="status">下载已准备。</p>}
    {[health.error, snapshot.error, handoff.error, verify.error].filter(Boolean).map((error, index) => <p key={index} role="alert" className="error">{error?.message}</p>)}
  </section>
}
