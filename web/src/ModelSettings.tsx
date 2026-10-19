import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ModelRoles, type ProductModelSettings } from './api'

export function ModelSettings() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['model-settings'], queryFn: api.modelSettings, retry: false })
  const [roles, setRoles] = useState<ModelRoles | null>(null)
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  useEffect(() => { if (query.data) setRoles(structuredClone(query.data.roles)) }, [query.data])
  const save = useMutation({ mutationFn: () => api.saveModelSettings({ roles: roles!, credentials }),
    onSuccess: (value: ProductModelSettings) => {
      setCredentials({}); client.setQueryData(['model-settings'], value)
      void client.invalidateQueries({ queryKey: ['research-settings'] })
    } })
  return <section aria-label="Models"><h3>Models · Web API</h3>
    <p>使用自己的 API 凭证。保存只做本地校验，不调用模型。Ollama 使用本机服务，无需 API key。</p>
    {roles && <>
      {(['coordinator', 'research', 'cheap_semantic'] as const).map(name => {
        const role = roles[name]
        const label = { coordinator: 'Coordinator', research: 'Research Agent', cheap_semantic: 'Cheap Semantic' }[name]
        const change = (value: Partial<typeof role>) => setRoles({ ...roles, [name]: { ...role, ...value } })
        return <fieldset key={name}><legend>{label} · {query.data?.status[name]}</legend>
          <label><input aria-label={`${label} enabled`} type="checkbox" checked={role.enabled} onChange={e => change({ enabled: e.target.checked })} /> Enabled</label>
          <label className="field">Provider<select aria-label={`${label} API provider`} value={role.provider} onChange={e => change({ provider: e.target.value, reasoning_effort: null })}>{query.data?.providers.map(p => <option key={p}>{p}</option>)}</select></label>
          <label className="field">Model<input aria-label={`${label} API model`} value={role.model} onChange={e => change({ model: e.target.value })} /></label>
          <label className="field">Reasoning effort<select aria-label={`${label} API effort`} disabled={role.provider !== 'openai'} value={role.reasoning_effort || ''} onChange={e => change({ reasoning_effort: e.target.value || null })}><option value="">Provider default</option>{['low', 'medium', 'high'].map(v => <option key={v}>{v}</option>)}</select></label>
        </fieldset>
      })}
      <h4>Provider credentials · write only</h4>
      {query.data?.providers.filter(p => p !== 'ollama').map(p => <label className="field" key={p}>{p} API key · {query.data?.credentials[p]}
        <input aria-label={`${p} API key`} type="password" autoComplete="new-password" value={credentials[p] || ''} placeholder="留空保留现有 key" onChange={e => {
          const value = { ...credentials }; if (e.target.value) value[p] = e.target.value; else delete value[p]; setCredentials(value)
        }} />
        <button type="button" onClick={() => setCredentials({ ...credentials, [p]: '' })}>清除 {p} key</button>
        {credentials[p] === '' && <small>保存后清除；尚未生效。</small>}
      </label>)}
      <p className="meta">Cheap Semantic 为预留角色；deterministic Episode parser 不使用模型。凭证仅存本机 .local，读取接口不可取回。</p>
      <button disabled={save.isPending} onClick={() => save.mutate()}>保存 Models</button>
      {save.isSuccess && <p role="status">Models 已保存；未调用 provider。</p>}
    </>}
    {(query.error || save.error) && <p role="alert">{String(query.error || save.error)}</p>}
  </section>
}
