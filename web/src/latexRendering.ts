/** Render-only normalization. Never returns content to the archive or memory parser. */
import type { Root, RootContent, Text, Link } from 'mdast'
import type { ElementContent } from 'hast'

export const DISPLAY_ENVIRONMENTS = ['equation', 'equation*', 'align', 'align*', 'aligned', 'gather', 'gather*', 'multline', 'multline*'] as const
const environments = new Set<string>(DISPLAY_ENVIRONMENTS)
const marker = 'reader-latex:'

function escaped(text: string, at: number): boolean {
  let slashes = 0
  while (at > 0 && text[--at] === '\\') slashes++
  return slashes % 2 === 1
}

function closing(text: string, token: string, start: number): number {
  let at = text.indexOf(token, start)
  while (at >= 0 && escaped(text, at)) at = text.indexOf(token, at + token.length)
  return at
}

function environmentEnd(text: string, start: number, name: string): number {
  const commands = /\\(begin|end)\{([^{}\r\n]+)\}|%[^\n]*/g
  commands.lastIndex = start
  const stack = [name]
  for (let match; (match = commands.exec(text));) {
    if (match[0][0] === '%') {
      // An escaped percent is math, not a comment hiding the rest of the line.
      if (escaped(text, match.index)) commands.lastIndex = match.index + 1
      continue
    }
    if (escaped(text, match.index)) continue
    if (match[1] === 'begin') stack.push(match[2])
    else if (stack.pop() !== match[2]) return -1
    if (!stack.length) return commands.lastIndex
  }
  return -1
}

/** Keep code, existing dollar math, escapes and link destinations byte-for-byte. */
export function normalizeLatexMarkdown(source: string): string {
  let result = '', at = 0
  while (at < source.length) {
    const rest = source.slice(at)
    if (at === 0 || source[at - 1] === '\n') {
      const fence = /^(?: {0,3}> ?)* {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)/.exec(rest)
      if (fence) {
        const endFence = new RegExp('^(?: {0,3}> ?)* {0,3}' + fence[1][0] + '{' + fence[1].length + ',}[ \\t]*\\r?$', 'gm')
        endFence.lastIndex = at + fence[0].length
        const end = endFence.exec(source)
        const until = end ? end.index + end[0].length : source.length
        result += source.slice(at, until); at = until; continue
      }
      if (/^(?: {4}|\t)/.test(rest)) {
        const end = source.indexOf('\n', at)
        const until = end < 0 ? source.length : end + 1
        result += source.slice(at, until); at = until; continue
      }
    }
    if (source[at] === '`') {
      const run = /^`+/.exec(rest)![0]
      let end = source.indexOf(run, at + run.length)
      while (end >= 0 && (source[end - 1] === '`' || source[end + run.length] === '`')) end = source.indexOf(run, end + run.length)
      const until = end < 0 ? at + run.length : end + run.length
      result += source.slice(at, until); at = until; continue
    }
    if (rest.startsWith('](')) {
      let depth = 1, until = at + 2
      for (; until < source.length && depth; until++) {
        if (escaped(source, until)) continue
        if (source[until] === '(') depth++
        if (source[until] === ')') depth--
      }
      result += source.slice(at, until); at = until; continue
    }
    if (source[at] === '$' && !escaped(source, at)) {
      const run = /^\$+/.exec(rest)![0]
      const end = closing(source, run, at + run.length)
      const until = end < 0 ? at + run.length : end + run.length
      result += source.slice(at, until); at = until; continue
    }
    if (rest.startsWith('\\\\')) { result += '\\\\'; at += 2; continue }
    if (rest.startsWith('\\[') || rest.startsWith('\\(')) {
      const display = rest[1] === '['
      const end = closing(source, display ? '\\]' : '\\)', at + 2)
      if (end >= 0) {
        const body = source.slice(at + 2, end)
        result += display ? `\n\n$$\n${body}\n$$\n\n` : `$${body}$`
        at = end + 2; continue
      }
    }
    const begin = /^\\begin\{([^{}\r\n]+)\}/.exec(rest)
    if (begin && environments.has(begin[1])) {
      const end = environmentEnd(source, at + begin[0].length, begin[1])
      if (end >= 0) {
        result += `\n\n$$ ${marker}${begin[1]}\n${source.slice(at, end)}\n$$\n\n`
        at = end; continue
      }
    }
    result += source[at++]
  }
  return result
}

type MathNode = Extract<RootContent, { type: 'math' | 'inlineMath' }>
type Equation = { node: MathNode; body: string; anchor: string; labels: string[]; number: string | null; automatic: boolean; tagged: boolean }
type Reference = { equation: Equation; occurrences: number }

/** Ignore TeX comments when collecting commands, without changing escaped percent. */
function mathBody(value: string): string {
  let body = ''
  for (let at = 0; at < value.length; at++) {
    if (value[at] === '%' && !escaped(value, at)) {
      const end = value.indexOf('\n', at)
      if (end < 0) break
      at = end
    }
    body += value[at]
  }
  return body.replace(/\\(begin|end)\{(equation\*?|align\*?|gather\*?|multline\*?)\}/g, (all, kind: string, name: string, at: number) => {
      if (escaped(body, at)) return all
      if (name.startsWith('equation')) return ''
      return `\\${kind}{${name.startsWith('align') ? 'aligned' : 'gathered'}}`
    })
}

/** AST references are text/link nodes, never interpolated raw HTML or Markdown. */
export function remarkLatexReferences({ prefix }: { prefix: string }) {
  return (tree: Root) => {
    const equations: Equation[] = []
    const references = new Map<string, Reference>()
    function collect(node: Root | RootContent) {
      if (node.type === 'math' || node.type === 'inlineMath') {
        const labels: string[] = []
        const original = node.value
        const clean = mathBody(original)
        const body = clean.replace(/\\label\{([^{}\r\n]+)\}/g, (all, label: string, at: number) => {
          if (escaped(clean, at)) return all
          labels.push(label); return ''
        })
        const env = node.type === 'math' && node.meta?.startsWith(marker) ? node.meta.slice(marker.length) : /^\s*\\begin\{([^}]+)\}/.exec(original)?.[1]
        const tag = /\\tag(\*)?\{([^{}]*)\}/.exec(body)
        const numbered = node.type === 'math' && !env?.endsWith('*') && (labels.length > 0 || ['equation', 'align', 'gather', 'multline'].includes(env || ''))
        const equation: Equation = { node, body, labels, anchor: `${prefix}-${equations.length + 1}`,
          number: tag && /^[\p{L}\p{N} .:,*+−-]+$/u.test(tag[2]) ? tag[2] : null,
          automatic: numbered && !/\\tag\*?\s*\{/.test(body), tagged: /\\tag\*?\s*\{/.test(body) }
        equations.push(equation)
        for (const label of labels) {
          const previous = references.get(label)
          references.set(label, { equation: previous?.equation || equation, occurrences: (previous?.occurrences || 0) + 1 })
        }
      } else if ('children' in node && !['code', 'link', 'linkReference'].includes(node.type)) node.children.forEach(collect)
    }
    collect(tree)
    const used = new Set(equations.flatMap(e => e.number ? [e.number] : []))
    let next = 1
    for (const equation of equations) {
      if (equation.automatic) {
        while (used.has(String(next))) next++
        equation.number = String(next++); used.add(equation.number)
      }
    }
    function resolve(label: string, parens: boolean) {
      const entry = references.get(label)
      if (!entry || entry.occurrences > 1 || !entry.equation.number) {
        const reason = !entry ? 'unresolved' : entry.occurrences > 1 ? 'duplicate label' : 'unnumbered'
        return { text: `[${reason} reference: ${label}]`, anchor: null }
      }
      return { text: parens ? `(${entry.equation.number})` : entry.equation.number, anchor: entry.equation.anchor }
    }
    const refPattern = /\\(eqref|ref)\{([^{}\r\n]+)\}/g
    for (const equation of equations) {
      const { node } = equation
      let value = equation.body.replace(refPattern, (_all, kind: string, label: string) => {
        const ref = resolve(label, kind === 'eqref')
        // Math-internal references stay in math; trust remains false (no HTML/href macros).
        const safe = ref.anchor ? ref.text : 'unresolved reference'
        return `\\text{${safe}}`
      })
      if (equation.automatic) value += `\n\\tag{${equation.number}}`
      const display = node.type === 'math'
      const content: ElementContent = { type: 'element', tagName: 'code', properties: { className: ['language-math', display ? 'math-display' : 'math-inline'] }, children: [{ type: 'text', value }] }
      node.value = value
      node.data = { ...node.data, hName: display ? 'div' : 'span', hProperties: { id: equation.anchor, className: display ? ['reader-equation'] : [] }, hChildren: [content] }
    }
    function rewrite(node: Root | RootContent) {
      if (!('children' in node) || ['link', 'linkReference'].includes(node.type)) return
      const children: RootContent[] = []
      for (const child of node.children) {
        if (child.type !== 'text') { rewrite(child); children.push(child); continue }
        let from = 0
        for (const match of child.value.matchAll(refPattern)) {
          if (match.index > from) children.push({ type: 'text', value: child.value.slice(from, match.index) })
          const ref = resolve(match[2], match[1] === 'eqref')
          children.push(ref.anchor ? { type: 'link', url: `#${ref.anchor}`, children: [{ type: 'text', value: ref.text }] } satisfies Link : { type: 'text', value: ref.text } satisfies Text)
          from = match.index + match[0].length
        }
        if (from < child.value.length) children.push({ type: 'text', value: child.value.slice(from) })
      }
      // The replacements preserve the parent's existing phrasing/block structure.
      node.children = children as typeof node.children
    }
    rewrite(tree)
    for (const [label, ref] of references) if (ref.occurrences > 1) {
      tree.children.push({ type: 'paragraph', data: { hProperties: { className: ['math-reference-warning'] } }, children: [{ type: 'text', value: `Duplicate equation label: ${label}. References are unresolved.` }] })
    }
  }
}
