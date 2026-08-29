"use client";

import React from "react";

/**
 * Minimal Markdown renderer for Gemini's replies.
 *
 * Deliberately not a library. The agent emits a narrow, predictable subset -
 * headings, bullets, numbered lists, bold and inline code - and pulling in
 * react-markdown would add a package for roughly sixty lines of work.
 */

const BOLD_OR_CODE = /(\*\*[^*]+\*\*|`[^`]+`)/g;

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split(BOLD_OR_CODE).filter(Boolean).map((chunk, index) => {
    const key = `${keyPrefix}-${index}`;
    if (chunk.startsWith("**") && chunk.endsWith("**")) {
      return (
        <strong key={key} className="font-semibold text-slate-900">
          {chunk.slice(2, -2)}
        </strong>
      );
    }
    if (chunk.startsWith("`") && chunk.endsWith("`")) {
      return (
        <code
          key={key}
          className="rounded bg-slate-200 px-1 py-0.5 font-mono text-[0.8em] text-slate-800"
        >
          {chunk.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={key}>{chunk}</React.Fragment>;
  });
}

interface Block {
  kind: "heading" | "bullets" | "numbers" | "paragraph" | "rule";
  level?: number;
  lines: string[];
}

function parse(markdown: string): Block[] {
  const blocks: Block[] = [];
  let buffer: string[] = [];
  let mode: Block["kind"] | null = null;

  const flush = () => {
    if (mode && buffer.length) blocks.push({ kind: mode, lines: buffer });
    buffer = [];
    mode = null;
  };

  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();

    if (!line.trim()) {
      flush();
      continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      flush();
      blocks.push({ kind: "rule", lines: [] });
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flush();
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        lines: [heading[2]],
      });
      continue;
    }

    const bullet = line.match(/^\s*[*-]\s+(.*)$/);
    if (bullet) {
      if (mode !== "bullets") flush();
      mode = "bullets";
      buffer.push(bullet[1]);
      continue;
    }

    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numbered) {
      if (mode !== "numbers") flush();
      mode = "numbers";
      buffer.push(numbered[1]);
      continue;
    }

    if (mode !== "paragraph") flush();
    mode = "paragraph";
    buffer.push(line);
  }
  flush();
  return blocks;
}

export default function Markdown({ text }: { text: string }) {
  const blocks = parse(text);

  return (
    <div className="space-y-2 text-[13px] leading-relaxed text-slate-700">
      {blocks.map((block, index) => {
        const key = `b${index}`;

        if (block.kind === "rule") {
          return <hr key={key} className="my-3 border-slate-200" />;
        }

        if (block.kind === "heading") {
          const size =
            block.level === 1
              ? "text-base"
              : block.level === 2
                ? "text-sm"
                : "text-[13px]";
          return (
            <h3
              key={key}
              className={`${size} mt-3 font-semibold text-slate-900 first:mt-0`}
            >
              {inline(block.lines[0], key)}
            </h3>
          );
        }

        if (block.kind === "bullets") {
          return (
            <ul key={key} className="ml-4 list-disc space-y-1 marker:text-blue-700">
              {block.lines.map((line, i) => (
                <li key={`${key}-${i}`}>{inline(line, `${key}-${i}`)}</li>
              ))}
            </ul>
          );
        }

        if (block.kind === "numbers") {
          return (
            <ol key={key} className="ml-4 list-decimal space-y-1 marker:font-semibold marker:text-blue-700">
              {block.lines.map((line, i) => (
                <li key={`${key}-${i}`}>{inline(line, `${key}-${i}`)}</li>
              ))}
            </ol>
          );
        }

        return <p key={key}>{inline(block.lines.join(" "), key)}</p>;
      })}
    </div>
  );
}
