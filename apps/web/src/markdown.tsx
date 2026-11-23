import type { ReactNode } from "react";

/**
 * Minimal, SAFE markdown renderer for assistant answers: no dependency, and no HTML injection
 * possible because we never touch innerHTML — input is split into text tokens and rebuilt as
 * React elements. Supported subset (what the agents actually emit): **bold**, *italic*,
 * `inline code`, [n] source citations (rendered as small badges), "- " bullet lists, paragraphs
 * and line breaks. Anything else (including raw HTML) renders as literal text.
 */

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[(\d{1,2})\])/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] !== undefined) nodes.push(<strong key={`${keyPrefix}-b${i}`}>{m[2]}</strong>);
    else if (m[3] !== undefined) nodes.push(<em key={`${keyPrefix}-i${i}`}>{m[3]}</em>);
    else if (m[4] !== undefined)
      nodes.push(
        <code key={`${keyPrefix}-c${i}`} className="rounded bg-ink-100 px-1 font-mono text-[0.85em]">
          {m[4]}
        </code>,
      );
    else if (m[5] !== undefined)
      nodes.push(
        <sup
          key={`${keyPrefix}-s${i}`}
          className="ml-0.5 rounded border border-brand-300 bg-brand-50 px-1 text-[10px] font-semibold text-brand-700"
        >
          [{m[5]}]
        </sup>,
      );
    last = m.index + m[0].length;
    i++;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function renderMarkdown(text: string): ReactNode[] {
  return text.split(/\n{2,}/).map((para, pi) => {
    const lines = para.split("\n");
    if (lines.every((l) => l.trimStart().startsWith("- "))) {
      return (
        <ul key={`p${pi}`} className="mt-1 list-disc pl-4">
          {lines.map((l, li) => (
            <li key={li}>{renderInline(l.trimStart().slice(2), `p${pi}l${li}`)}</li>
          ))}
        </ul>
      );
    }
    return (
      <p key={`p${pi}`} className={pi > 0 ? "mt-2" : undefined}>
        {lines.flatMap((l, li) => {
          const nodes: ReactNode[] = renderInline(l, `p${pi}l${li}`);
          if (li < lines.length - 1) nodes.push(<br key={`p${pi}br${li}`} />);
          return nodes;
        })}
      </p>
    );
  });
}
