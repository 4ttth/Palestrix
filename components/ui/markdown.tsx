import * as React from "react";

/*
 * Minimal Markdown renderer for writeup bodies: headings, paragraphs,
 * fenced code, inline code, bold/italic, links, blockquotes, and flat
 * lists. Everything renders through React elements — no raw HTML ever
 * reaches the DOM, so author input cannot inject markup.
 */

function inline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // code | bold | italic | link
  const token =
    /(`([^`]+)`)|(\*\*([^*]+)\*\*)|(\*([^*]+)\*)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = token.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const key = `${keyBase}-${i++}`;
    if (m[2] !== undefined) {
      out.push(
        <code key={key} className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.85em]">
          {m[2]}
        </code>
      );
    } else if (m[4] !== undefined) {
      out.push(<strong key={key}>{m[4]}</strong>);
    } else if (m[6] !== undefined) {
      out.push(<em key={key}>{m[6]}</em>);
    } else if (m[8] !== undefined) {
      out.push(
        <a
          key={key}
          href={m[9]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent underline underline-offset-2"
        >
          {m[8]}
        </a>
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    // Fenced code
    if (line.trimStart().startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++; // closing fence
      blocks.push(
        <pre
          key={key++}
          className="overflow-x-auto rounded-(--radius-input) border border-border bg-surface-2/60 p-3.5 font-mono text-[12.5px] leading-relaxed"
        >
          {buf.join("\n")}
        </pre>
      );
      continue;
    }

    // Headings
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const cls = [
        "text-lg font-semibold tracking-tight",
        "text-base font-semibold tracking-tight",
        "text-[15px] font-semibold",
        "text-sm font-semibold",
      ][level - 1];
      blocks.push(
        <p key={key++} className={cls}>
          {inline(heading[2], `h${key}`)}
        </p>
      );
      i++;
      continue;
    }

    // Blockquote
    if (line.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        buf.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={key++}
          className="border-l-2 border-accent/50 pl-3.5 text-muted"
        >
          {inline(buf.join(" "), `q${key}`)}
        </blockquote>
      );
      continue;
    }

    // Lists (flat)
    const isItem = (s: string) => /^\s*([-*]|\d+\.)\s+/.test(s);
    if (isItem(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && isItem(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""));
        i++;
      }
      const children = items.map((it, n) => (
        <li key={n}>{inline(it, `li${key}-${n}`)}</li>
      ));
      blocks.push(
        ordered ? (
          <ol key={key++} className="list-decimal space-y-1 pl-5">
            {children}
          </ol>
        ) : (
          <ul key={key++} className="list-disc space-y-1 pl-5">
            {children}
          </ul>
        )
      );
      continue;
    }

    // Paragraph: run until a blank line or a structural line
    const buf: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].trimStart().startsWith("```") &&
      !/^(#{1,4})\s+/.test(lines[i]) &&
      !lines[i].startsWith(">") &&
      !isItem(lines[i])
    ) {
      buf.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={key++} className="leading-relaxed">
        {inline(buf.join(" "), `p${key}`)}
      </p>
    );
  }

  return <div className="space-y-3.5 text-sm">{blocks}</div>;
}
