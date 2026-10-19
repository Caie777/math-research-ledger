import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ResearchDefaults, type RelationModelSettings, type CritiqueSettings } from './api'
import { ModelSettings } from './ModelSettings'

export function ResearchSettings() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['research-settings'], queryFn: api.researchSettings })
  const [draft, setDraft] = useState<ResearchDefaults | null>(null)
  useEffect(() => { if (query.data) setDraft(structuredClone(query.data)) }, [query.data])
  const save = useMutation({ mutationFn: () => api.saveResearchSettings(draft!), onSuccess: value => client.setQueryData(['research-settings'], value) })
  function research(key: string, value: unknown) {
    setDraft(current => current ? { ...current, research: { ...current.research, [key]: value } } : null)
  }
  return <details id="research-settings" className="research-settings"><summary>⚙ Research Settings</summary>
    <ModelSettings />
    <p className="meta">以下是现有 Codex/operator 与高级工作流设置。Codex 使用本人已登录的 CLI，不需要 API key。</p>
    {draft && <>
      <h3>Research Agent defaults</h3>
      <section><h3>Coordinator model</h3><p className="meta">未配置时确定性命令仍可用。语义理解与总结使用此独立角色。</p>
        <label><input type="checkbox" aria-label="Configure Coordinator model" checked={!!draft.coordinator} onChange={e => setDraft({ ...draft, coordinator: e.target.checked ? { provider: draft.research.provider, model: '', reasoning_effort: null } : null })} /> 配置 Coordinator</label>
        {draft.coordinator && <>
          <label className="field">Coordinator Provider<select aria-label="Coordinator provider" value={draft.coordinator.provider} onChange={e => setDraft({ ...draft, coordinator: { ...draft.coordinator!, provider: e.target.value } })}>{['codex', 'openai', 'anthropic', 'ollama', 'mistral'].map(p => <option key={p}>{p}</option>)}</select></label>
          <label className="field">Coordinator Model<input aria-label="Coordinator model" value={draft.coordinator.model} onChange={e => setDraft({ ...draft, coordinator: { ...draft.coordinator!, model: e.target.value } })} /></label>
          <label className="field">Coordinator Reasoning<select aria-label="Coordinator effort" value={draft.coordinator.reasoning_effort || ''} onChange={e => setDraft({ ...draft, coordinator: { ...draft.coordinator!, reasoning_effort: e.target.value || null } })}><option value="">default</option>{['low', 'medium', 'high', 'xhigh', 'max'].map(e => <option key={e}>{e}</option>)}</select></label>
        </>}
      </section>
      <label className="field">Research Provider<select value={draft.research.provider} onChange={e => research('provider', e.target.value)}>{['codex', 'openai', 'anthropic', 'ollama', 'mistral'].map(p => <option key={p}>{p}</option>)}</select></label>
      <label className="field">Research Model<input aria-label="Default Research Model" value={draft.research.model || ''} onChange={e => research('model', e.target.value)} /></label>
      <label className="field">Research Reasoning<select aria-label="Default Research Reasoning" value={draft.research.effort || ''} onChange={e => research('effort', e.target.value || null)}><option value="">default</option>{['low', 'medium', 'high', 'xhigh', 'max'].map(e => <option key={e}>{e}</option>)}</select></label>
      <label><input type="checkbox" checked={draft.research.include_provisional} onChange={e => research('include_provisional', e.target.checked)} /> Include provisional by default</label>
      <label className="field">Context tokens<input type="number" value={draft.research.context_tokens} onChange={e => research('context_tokens', Number(e.target.value))} /></label>
      <label className="field">Checkpoint every effective steps<input type="number" value={draft.research.checkpoint_every_effective_steps} onChange={e => research('checkpoint_every_effective_steps', Number(e.target.value))} /></label>
      {Object.entries(draft.research.budget).map(([key, value]) => <label className="field" key={key}>{key}<input type="number" value={value} onChange={e => research('budget', { ...draft.research.budget, [key]: Number(e.target.value) })} /></label>)}
      <p className="meta">Reflection interval: {draft.reflection_every_research_decisions} research decisions（既有运行策略）</p>
      {(['scout', 'adjudicator', 'recall'] as const).map(key => <section key={key}><h3>{key === 'recall' ? 'Smart Recall rerank' : key === 'scout' ? 'Relation Scout' : 'Hard Adjudicator'} defaults</h3>
        {(['provider', 'model', 'reasoning_effort'] as const).map(field => <label className="field" key={field}>{field}<input aria-label={`Default ${key} ${field}`} value={draft[key][field] || ''} onChange={e => setDraft({ ...draft, [key]: { ...draft[key], [field]: e.target.value || null } as RelationModelSettings })} /></label>)}
      </section>)}
      <label className="field">Adjudication tokens<input type="number" value={draft.adjudication_tokens} onChange={e => setDraft({ ...draft, adjudication_tokens: Number(e.target.value) })} /></label>
      {draft.critique && <section><h3>Independent Critique defaults</h3><p>Fresh context · advisory only</p>
        {(['provider', 'model', 'reasoning_effort'] as const).map(field => <label className="field" key={field}>{field}<input aria-label={`Default critique ${field}`} value={draft.critique![field] || ''} onChange={e => setDraft({ ...draft, critique: { ...draft.critique!, [field]: e.target.value || null } as CritiqueSettings })} /></label>)}
      </section>}
      <p>保存到已有 workspace 配置，仅影响新任务；Resume 使用原 run 的 request。</p>
      <button disabled={save.isPending || !!draft.coordinator && !draft.coordinator.model.trim()} onClick={() => save.mutate()}>确认保存默认设置</button>
      {save.isSuccess && <p role="status">默认设置已保存。</p>}
    </>}
    {(query.error || save.error) && <p role="alert" className="error">{String(query.error || save.error)}</p>}
  </details>
}
