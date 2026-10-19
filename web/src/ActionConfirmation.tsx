import { useRef } from 'react'

export interface Confirmation {
  title: string
  details: Record<string, string | number | boolean | null>
  run: () => void
}

export function llmDetails(role: string, context: string) {
  return { 'Uses LLM': 'Yes', Role: role, Context: context }
}
export function ActionConfirmation({ value, onClose }: { value: Confirmation | null; onClose: () => void }) {
  const executed = useRef<Confirmation | null>(null)
  if (!value) return null
  return <section className="confirmation-card" role="dialog" aria-label={value.title}>
    <h3>{value.title}</h3>
    <dl>{Object.entries(value.details).map(([key, data]) => <div key={key}><dt>{key}</dt><dd>{String(data ?? 'default')}</dd></div>)}</dl>
    <button onClick={() => {
      if (executed.current === value) return
      executed.current = value
      onClose(); value.run()
    }}>确认执行</button><button onClick={onClose}>取消</button>
  </section>
}
