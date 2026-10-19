import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { Markdown } from './Markdown'
import { normalizeLatexMarkdown } from './latexRendering'
import { syntheticEquationExcerpt } from './latexRendering.fixture'

afterEach(cleanup)
const equation = (label: string, body = 'a+b=c', env = 'equation') => `\\begin{${env}}\n\\label{${label}}\n${body}\n\\end{${env}}`
function view(text: string) { return render(<Markdown text={text} />) }
function noKatexError(container: HTMLElement) { expect(container.querySelector('.katex-error')).toBeNull() }
// KaTeX intentionally retains valid TeX in an invisible MathML annotation.
function visibleText(container: HTMLElement) {
  const copy = container.cloneNode(true) as HTMLElement
  copy.querySelectorAll('.katex-mathml').forEach(node => node.remove())
  return copy.textContent || ''
}

it('renders equation as display math, removes label and makes eqref a real internal link', () => {
  const { container } = view(equation('eq:foo') + String.raw`式 \eqref{eq:foo}。`)
  expect(container.querySelectorAll('.katex-display')).toHaveLength(1)
  const link = screen.getByRole('link', { name: '(1)' })
  expect(container.querySelector(link.getAttribute('href')!)).not.toBeNull()
  expect(container.innerHTML).not.toContain('eq:foo')
  expect(container.textContent).not.toContain('\\label')
  noKatexError(container)
})
it('renders equation* without inventing an equation number', () => {
  const { container } = view(String.raw`\begin{equation*}a+b=c\end{equation*}`)
  expect(container.querySelector('.katex-display')).not.toBeNull()
  expect(container.querySelector('.tag')).toBeNull()
  noKatexError(container)
})
it('renders ref without parentheses and resolves forward references', () => {
  const { container } = view(String.raw`见 \ref{eq:foo}。` + '\n\n' + equation('eq:foo'))
  expect(screen.getByRole('link', { name: '1' })).toBeTruthy()
  noKatexError(container)
})
it('unknown labels are explicit and never point at fabricated equations', () => {
  const { container } = view(String.raw`\eqref{eq:missing} 和 \ref{eq:other}`)
  expect(container.textContent).toContain('[unresolved reference: eq:missing]')
  expect(container.textContent).toContain('[unresolved reference: eq:other]')
  expect(container.querySelector('a')).toBeNull()
})
it('numbers multiple equations deterministically, with stable links across rerender', () => {
  const text = equation('eq:a') + '\n\n' + equation('eq:b') + String.raw`\eqref{eq:b} \eqref{eq:a}`
  const { container, rerender } = view(text)
  const anchors = [...container.querySelectorAll('a')].map(a => a.getAttribute('href'))
  expect(screen.getByRole('link', { name: '(2)' })).toBeTruthy()
  expect(screen.getByRole('link', { name: '(1)' })).toBeTruthy()
  rerender(<Markdown text={text} />)
  expect([...container.querySelectorAll('a')].map(a => a.getAttribute('href'))).toEqual(anchors)
})
it('duplicate labels are explicitly ambiguous and do not pick an arbitrary target', () => {
  const { container } = view(equation('eq:duplicate') + '\n\n' + equation('eq:duplicate', 'x=y') + String.raw`\eqref{eq:duplicate}`)
  expect(container.textContent).toContain('[duplicate label reference: eq:duplicate]')
  expect(screen.getByText(/Duplicate equation label:/)).toBeTruthy()
  expect(container.querySelectorAll('a')).toHaveLength(0)
  const ids = [...container.querySelectorAll('.reader-equation')].map(e => e.id)
  expect(new Set(ids).size).toBe(2)
})
it('ordinary dollar inline math is unchanged and does not consume a number', () => {
  const { container } = view('$x^2+1$\n\n' + equation('eq:a') + String.raw`\eqref{eq:a}`)
  expect(container.querySelectorAll('.katex')).toHaveLength(2)
  expect(container.querySelectorAll('.katex-display')).toHaveLength(1)
  expect(screen.getByRole('link', { name: '(1)' })).toBeTruthy()
  noKatexError(container)
})
it('existing dollar display math and explicit tags retain their rendering', () => {
  const text = String.raw`$$
\frac{a}{b}=c\tag{A.1}
$$`
  expect(normalizeLatexMarkdown(text)).toBe(text)
  const { container } = view(text)
  expect(container.querySelector('.katex-display')).not.toBeNull()
  expect(container.querySelector('.tag')?.textContent).toContain('A.1')
  noKatexError(container)
})
it('mixes Chinese prose and display equations without swallowing surrounding text', () => {
  const { container } = view('前文说明。' + equation('eq:cn') + '后文解释。')
  expect(container.textContent).toContain('前文说明。')
  expect(container.textContent).toContain('后文解释。')
  expect(container.querySelector('.katex-display')).not.toBeNull()
})
it('renders the synthetic labelled-equation regression excerpt', () => {
  const { container } = view(syntheticEquationExcerpt)
  expect(container.querySelectorAll('.katex-display')).toHaveLength(3)
  expect(screen.getAllByRole('link', { name: '(1)' })).toHaveLength(1)
  expect(screen.getByRole('link', { name: '(2)' })).toBeTruthy()
  expect(screen.getByRole('link', { name: '1' })).toBeTruthy()
  expect(visibleText(container)).not.toMatch(/\\(?:begin|end|label|eqref|ref)\{/)
  noKatexError(container)
})
it.each(['align', 'align*', 'aligned', 'gather', 'gather*', 'multline', 'multline*'])('renders standalone %s using the existing KaTeX engine', env => {
  const body = env.startsWith('align') ? String.raw`a&=b\\ c&=d` : String.raw`a=b\\ c=d`
  const { container } = view(`\\begin{${env}}\n${body}\n\\end{${env}}`)
  expect(container.querySelector('.katex-display')).not.toBeNull()
  expect(visibleText(container)).not.toContain('\\begin')
  noKatexError(container)
})
it('handles nested aligned/cases without normalizing the existing dollar delimiters', () => {
  const text = String.raw`$$
\begin{aligned} f(x)&=\begin{cases}1&x>0\\0&x=0\end{cases}\end{aligned}
$$`
  expect(normalizeLatexMarkdown(text)).toBe(text)
  const { container } = view(text)
  noKatexError(container)
})
it('labels in existing display math use the same mapping and preserve explicit tags', () => {
  const { container } = view(String.raw`$$
x=y\label{eq:tag}\tag{A.1}
$$
见 \eqref{eq:tag}。`)
  expect(screen.getByRole('link', { name: '(A.1)' })).toBeTruthy()
  expect(container.textContent).not.toContain('\\label')
  noKatexError(container)
})
it('label on an unnumbered equation stays unnumbered and has an explicit fallback', () => {
  const { container } = view(equation('eq:star', 'x=y', 'equation*') + String.raw`\eqref{eq:star}`)
  expect(container.textContent).toContain('[unnumbered reference: eq:star]')
  expect(container.querySelector('.tag')).toBeNull()
})
it('preserves fenced, indented and inline code, including reference examples', () => {
  const code = equation('eq:code') + String.raw`\eqref{eq:code} \[x\]`
  const text = '```latex\n' + code + '\n```\n\n`' + code.replaceAll('\n', ' ') + '`\n\n    \\begin{equation}x=y\\end{equation}\n'
  expect(normalizeLatexMarkdown(text)).toBe(text)
  const { container } = view(text)
  expect(container.querySelector('.katex')).toBeNull()
  expect(container.querySelectorAll('code')).toHaveLength(3)
})
it('protects tilde fences and multi-backtick code spans', () => {
  const text = '~~~~latex\n' + equation('eq:a') + '\n~~~~\n\n``\\[x\\] ` \\eqref{eq:a}``'
  expect(normalizeLatexMarkdown(text)).toBe(text)
})
it('unclosed or mismatched environments remain visible without dropping content', () => {
  for (const text of [String.raw`\begin{equation}x=y`, String.raw`\begin{equation}x=y\end{align}`]) {
    expect(normalizeLatexMarkdown(text)).toBe(text)
    const { container, unmount } = view(text)
    expect(container.textContent).toContain('x=y'); unmount()
  }
})
it.each([String.raw`a\%=b`, 'a=b % \\end{equation}\nc=d'])('handles escaped percent and commented environment endings: %s', body => {
  const { container } = view(equation('eq:percent', body) + String.raw`\eqref{eq:percent}`)
  expect(container.querySelector('.katex-display')).not.toBeNull()
  expect(screen.getByRole('link', { name: '(1)' })).toBeTruthy()
  noKatexError(container)
})
it('ignores labels hidden in TeX comments, including after an escaped percent', () => {
  const { container } = view(String.raw`\begin{equation}
a\% % \label{eq:comment}
\label{eq:real} = b
\end{equation}
\eqref{eq:real} \eqref{eq:comment}`)
  expect(screen.getByRole('link', { name: '(1)' })).toBeTruthy()
  expect(container.textContent).toContain('[unresolved reference: eq:comment]')
  noKatexError(container)
})
it('keeps legacy bracket/parenthesis delimiters working', () => {
  const { container } = view(String.raw`内联 \(x^2\)，展示：\[a=b\]结束。`)
  expect(container.querySelectorAll('.katex')).toHaveLength(2)
  expect(container.querySelector('.katex-display')).not.toBeNull()
  noKatexError(container)
})
it('rejects raw HTML/script and untrusted KaTeX HTML/URL commands', () => {
  const { container } = view(String.raw`<script>alert('bad')</script><img src=x onerror="alert(1)">

$$\href{javascript:alert(1)}{bad}\htmlClass{evil}{x}$$

\ref{<script>alert(1)</script>}`)
  expect(container.querySelector('script, img, .evil, [onclick], [onerror]')).toBeNull()
  expect([...container.querySelectorAll('a')].some(a => a.href.startsWith('javascript:'))).toBe(false)
})
it('math-internal references render as safe text without enabling trusted href macros', () => {
  const { container } = view(equation('eq:a') + '\n\n' + String.raw`$x=\eqref{eq:a}$ 和 $\ref{eq:missing}$`)
  expect(container.querySelectorAll('.katex')).toHaveLength(3)
  expect(container.textContent).toContain('unresolved reference')
  noKatexError(container)
})
it('separate Reader instances never collide or resolve labels from other documents', () => {
  const { container } = render(<><Markdown text={equation('eq:a') + String.raw`\eqref{eq:a}`} /><Markdown text={String.raw`\eqref{eq:a}`} /></>)
  expect(container.querySelectorAll('a')).toHaveLength(1)
  expect(container.textContent).toContain('[unresolved reference: eq:a]')
})
