import { useId } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { normalizeLatexMarkdown, remarkLatexReferences } from './latexRendering'

/** Shared read-only renderer for Episode, objects, proposals and original resources. */
export function Markdown({ text }: { text: string }) {
  const prefix = `reader-math-${useId().replace(/[^A-Za-z0-9_-]/g, '')}`
  return <div className="markdown"><ReactMarkdown skipHtml
    remarkPlugins={[remarkMath, [remarkLatexReferences, { prefix }]]}
    rehypePlugins={[[rehypeKatex, { trust: false }]]}
  >{normalizeLatexMarkdown(text)}</ReactMarkdown></div>
}
