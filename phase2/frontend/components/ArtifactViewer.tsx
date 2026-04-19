"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { readArtifact } from "@/lib/api";

type Props = { path: string | null; refreshKey: number };

export function ArtifactViewer({ path, refreshKey }: Props) {
  const [state, setState] = useState<{
    loading: boolean;
    error?: string;
    data?: Awaited<ReturnType<typeof readArtifact>>;
  }>({ loading: false });

  useEffect(() => {
    if (!path) return;
    let aborted = false;
    setState({ loading: true });
    readArtifact(path)
      .then((data) => {
        if (!aborted) setState({ loading: false, data });
      })
      .catch((err: Error) => {
        if (!aborted) setState({ loading: false, error: err.message });
      });
    return () => {
      aborted = true;
    };
  }, [path, refreshKey]);

  if (!path) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-ink-400">
        Select a file on the left to view.
      </div>
    );
  }
  if (state.loading) {
    return <div className="p-6 text-sm text-ink-400">Loading...</div>;
  }
  if (state.error) {
    return <div className="p-6 text-sm text-red-300">{state.error}</div>;
  }
  if (!state.data) return null;
  if (state.data.binary) {
    return (
      <div className="p-6 text-sm text-ink-400">
        Binary file ({state.data.size} bytes) — preview not supported.
      </div>
    );
  }

  if (path.endsWith(".md")) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="prose-agent mx-auto max-w-3xl">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{state.data.content}</ReactMarkdown>
        </div>
      </div>
    );
  }
  if (path.endsWith(".json")) {
    let pretty = state.data.content;
    try {
      pretty = JSON.stringify(JSON.parse(state.data.content), null, 2);
    } catch {
      // keep raw
    }
    return (
      <pre className="h-full overflow-auto p-4 font-mono text-[12px] text-ink-100">{pretty}</pre>
    );
  }
  if (path.endsWith(".csv")) {
    return <CsvTable text={state.data.content} />;
  }
  return (
    <pre className="h-full overflow-auto p-4 font-mono text-[12px] text-ink-100">
      {state.data.content}
    </pre>
  );
}

function CsvTable({ text }: { text: string }) {
  const rows = text
    .split(/\r?\n/)
    .filter((l) => l.length > 0)
    .slice(0, 200)
    .map(parseCsvRow);
  if (rows.length === 0) return <div className="p-4 text-ink-400 text-sm">(empty)</div>;
  const [header, ...body] = rows;
  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead className="sticky top-0 bg-ink-800">
          <tr>
            {header.map((h, i) => (
              <th
                key={i}
                className="border-b border-ink-700 px-2 py-1.5 text-left font-semibold text-ink-100"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i} className="odd:bg-ink-900 even:bg-ink-800/40">
              {r.map((c, j) => (
                <td key={j} className="border-b border-ink-800 px-2 py-1 text-ink-200">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parseCsvRow(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        cur += ch;
      }
    } else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else if (ch === '"' && cur.length === 0) {
      inQuotes = true;
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}
