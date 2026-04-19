"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  readArtifact,
  readHandshakeContent,
  readSessionUpload,
  type FileContentPayload,
} from "@/lib/api";

type Props = {
  path: string | null;
  refreshKey: number;
  /** When set, ``path`` is a client upload path (e.g. ``uploads/foo.csv``) under this session. */
  sessionId?: string;
  /** When set, ``path`` is relative to ``phase2.5/output/`` (handshake tab). */
  handshake?: boolean;
};

export function ArtifactViewer({ path, refreshKey, sessionId, handshake }: Props) {
  const [state, setState] = useState<{
    loading: boolean;
    error?: string;
    data?: FileContentPayload;
  }>({ loading: false });

  useEffect(() => {
    if (!path) return;
    let aborted = false;
    setState({ loading: true });
    const load = sessionId
      ? readSessionUpload(sessionId, path)
      : handshake
        ? readHandshakeContent(path)
        : readArtifact(path);
    load
      .then((data) => {
        if (!aborted) setState({ loading: false, data });
      })
      .catch((err: Error) => {
        if (!aborted) setState({ loading: false, error: err.message });
      });
    return () => {
      aborted = true;
    };
  }, [path, refreshKey, sessionId, handshake]);

  if (!path) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-ink-400">
        {sessionId
          ? "Select an upload to preview."
          : handshake
            ? "Select a file under phase2.5/output."
            : "Select a file on the left to view."}
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

  const xp = state.data.xlsx_preview;
  if (xp?.sheets?.length) {
    return (
      <XlsxPreview
        maxRows={xp.max_rows_per_sheet}
        sheets={xp.sheets}
      />
    );
  }

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
  if (path.endsWith(".csv") || path.endsWith(".tsv")) {
    return <CsvTable text={state.data.content} delimiter={path.endsWith(".tsv") ? "\t" : ","} />;
  }
  return (
    <pre className="h-full overflow-auto p-4 font-mono text-[12px] text-ink-100">
      {state.data.content}
    </pre>
  );
}

function XlsxPreview({
  maxRows,
  sheets,
}: {
  maxRows: number;
  sheets: { name: string; rows: string[][]; truncated: boolean }[];
}) {
  return (
    <div className="h-full overflow-y-auto p-4">
      <p className="mb-4 text-[11px] text-ink-500">
        Spreadsheet preview — first {maxRows} rows per sheet (large files are not fully loaded).
      </p>
      <div className="space-y-6">
        {sheets.map((sheet) => (
          <div key={sheet.name}>
            <h3 className="mb-2 border-b border-ink-700 pb-1 text-xs font-semibold text-ink-200">
              {sheet.name}
              {sheet.truncated ? (
                <span className="ml-2 font-normal text-ink-500">(may have more rows)</span>
              ) : null}
            </h3>
            {sheet.rows.length === 0 ? (
              <p className="text-sm text-ink-400">(empty sheet)</p>
            ) : (
              <RowsTable rows={sheet.rows} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function RowsTable({ rows }: { rows: string[][] }) {
  if (rows.length === 0) return null;
  const header = rows[0] ?? [];
  const body = rows.slice(1);
  return (
    <div className="overflow-auto rounded border border-ink-800">
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
        {body.length > 0 ? (
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
        ) : null}
      </table>
    </div>
  );
}

function CsvTable({ text, delimiter = "," }: { text: string; delimiter?: string }) {
  const rows = text
    .split(/\r?\n/)
    .filter((l) => l.length > 0)
    .slice(0, 200)
    .map((line) => parseDelimitedRow(line, delimiter));
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

function parseDelimitedRow(line: string, delimiter: string): string[] {
  if (delimiter !== ",") {
    return line.split(delimiter);
  }
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
