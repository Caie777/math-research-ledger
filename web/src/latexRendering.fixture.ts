/** Synthetic Reader fixture: no private mathematical research. */
export const syntheticEquationExcerpt = String.raw`
由等式 \eqref{eq:sum}，在固定 $r$ 时可写成下式。

\begin{equation}
\label{eq:sum}
a+b=c.
\end{equation}

\begin{equation}
\label{eq:ratio}
\frac{x}{n}=f(y)+O(n^{-1}).
\end{equation}

式 \eqref{eq:ratio} 与 \ref{eq:sum} 只作当前文档内引用。

$$
\begin{aligned}
a&=b+c,\\
d&=e+f.
\end{aligned}
$$
`
