"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ArtifactTree } from "./ArtifactTree";
import { ArtifactViewer } from "./ArtifactViewer";
import { CommitHistory } from "./CommitHistory";
import type { ArtifactFile, CommitSummary, UploadedFile } from "@/lib/types";
import { Loader2, X } from "lucide-react";
import { applyHandshakeMapper, listArtifacts, listCommits } from "@/lib/api";

type Tab = "files" | "handshake" | "commits" | "uploads";

type Props = {
  sessionId: string;
  uploads: UploadedFile[];
  onRemoveUpload: (clientPath: string) => void | Promise<void>;
  changeToken: number;
  commitToken: number;
  /** Bump when handshake preview files change so the workspace refreshes. */
  onArtifactsChanged?: () => void;
};

const RECENT_MS = 10_000;

export function WorkspacePanel({
  sessionId,
  uploads,
  onRemoveUpload,
  changeToken,
  commitToken,
  onArtifactsChanged,
}: Props) {
  const [tab, setTab] = useState<Tab>("files");
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [commits, setCommits] = useState<CommitSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [recent, setRecent] = useState<Set<string>>(new Set());
  const [viewerKey, setViewerKey] = useState(0);
  const [applyBusy, setApplyBusy] = useState(false);
  /** Client path ``uploads/...`` for uploads-tab preview. */
  const [uploadSelected, setUploadSelected] = useState<string | null>(null);
  const [uploadViewerKey, setUploadViewerKey] = useState(0);
  const eventsAbortRef = useRef<AbortController | null>(null);

  const handshakeFiles = files.filter((f) => f.path.startsWith("handshake/"));

  const handshakeViewPath =
    handshakeFiles.length === 0
      ? null
      : handshakeFiles.some((f) => f.path === selected)
        ? selected
        : handshakeFiles[0].path;

  const refreshFiles = useCallback(async () => {
    try {
      setFiles(await listArtifacts());
    } catch (err) {
      console.error(err);
    }
  }, []);

  const refreshCommits = useCallback(async () => {
    try {
      setCommits(await listCommits(50));
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    refreshFiles();
    refreshCommits();
  }, [refreshFiles, refreshCommits]);

  useEffect(() => {
    refreshFiles();
    setViewerKey((k) => k + 1);
  }, [changeToken, refreshFiles]);

  useEffect(() => {
    if (uploads.length === 0) {
      setUploadSelected(null);
      return;
    }
    setUploadSelected((prev) => {
      if (prev && uploads.some((u) => u.path === prev)) return prev;
      return uploads[0].path;
    });
    setUploadViewerKey((k) => k + 1);
  }, [uploads]);

  useEffect(() => {
    refreshCommits();
  }, [commitToken, refreshCommits]);

  // SSE subscription for filesystem changes.
  useEffect(() => {
    const ac = new AbortController();
    eventsAbortRef.current = ac;
    (async () => {
      try {
        const res = await fetch("/api/events", { signal: ac.signal });
        if (!res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!ac.signal.aborted) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const data = raw
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trim())
              .join("\n");
            if (!data) continue;
            try {
              const evt = JSON.parse(data);
              if (evt.type === "file_changed") {
                const p: string = evt.path;
                setRecent((prev) => {
                  const next = new Set(prev);
                  next.add(p);
                  return next;
                });
                setTimeout(() => {
                  setRecent((prev) => {
                    const next = new Set(prev);
                    next.delete(p);
                    return next;
                  });
                }, RECENT_MS);
                refreshFiles();
                if (selected && p === selected) setViewerKey((k) => k + 1);
              }
            } catch {
              // ignore
            }
          }
        }
      } catch {
        // aborted or network error
      }
    })();
    return () => ac.abort();
  }, [refreshFiles, selected]);

  const runApplyMapper = useCallback(async () => {
    if (applyBusy) return;
    setApplyBusy(true);
    try {
      const r = await applyHandshakeMapper(sessionId);
      await refreshFiles();
      onArtifactsChanged?.();
      setViewerKey((k) => k + 1);
      if (r.outputs.length > 0) {
        setSelected(r.outputs[r.outputs.length - 1]);
      }
      if (!r.ok) {
        const bad = r.steps.find((s) => !s.ok);
        const err = bad?.stderr?.slice(0, 3000) ?? "";
        alert(
          `Mapper finished with errors.\n\n${bad ? `${bad.table} (exit ${bad.returncode})\n${err}` : "No table ran successfully."}`,
        );
      } else if (r.skipped.length > 0) {
        const lines = r.skipped.map((s) => `• ${s.table}: ${s.reason}`).join("\n");
        alert(`Preview written for ${r.outputs.length} table(s).\n\nSkipped:\n${lines}`);
      }
    } catch (e) {
      alert("Apply mapper failed: " + (e as Error).message);
    } finally {
      setApplyBusy(false);
    }
  }, [applyBusy, sessionId, refreshFiles, onArtifactsChanged]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-ink-700 px-2">
        {(["files", "handshake", "commits", "uploads"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={clsx(
              "px-3 py-2 text-xs font-medium uppercase tracking-wider",
              tab === t
                ? "border-b-2 border-brand text-ink-50"
                : "text-ink-400 hover:text-ink-200",
            )}
          >
            {t === "handshake" ? "handshake" : t}
            {t === "files" && files.length > 0 && (
              <span className="ml-1.5 rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-200">
                {files.length}
              </span>
            )}
            {t === "handshake" && handshakeFiles.length > 0 && (
              <span className="ml-1.5 rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-200">
                {handshakeFiles.length}
              </span>
            )}
            {t === "commits" && commits.length > 0 && (
              <span className="ml-1.5 rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-200">
                {commits.length}
              </span>
            )}
            {t === "uploads" && uploads.length > 0 && (
              <span className="ml-1.5 rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-200">
                {uploads.length}
              </span>
            )}
          </button>
        ))}
        <div className="ml-auto px-3 py-2 font-mono text-[10px] text-ink-500">
          session {sessionId.slice(0, 8)}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {tab === "files" && (
          <div className="grid h-full grid-cols-[minmax(180px,280px)_1fr] min-h-0">
            <div className="border-r border-ink-700 min-h-0 overflow-hidden">
              <ArtifactTree
                files={files}
                selected={selected}
                recent={recent}
                onSelect={setSelected}
              />
            </div>
            <div className="min-h-0 overflow-hidden">
              <ArtifactViewer path={selected} refreshKey={viewerKey} />
            </div>
          </div>
        )}
        {tab === "handshake" && (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-ink-800 px-3 py-2">
              <button
                type="button"
                onClick={() => void runApplyMapper()}
                disabled={applyBusy}
                title="Run handshake_run_mapper.py for each table: uses session uploads (e.g. contacts.csv) or output/tables/&lt;slug&gt;/*.csv, writes mid-layer CSVs under handshake/preview/"
                className="inline-flex items-center gap-1.5 rounded-md bg-ink-700 px-3 py-1.5 text-xs font-medium text-ink-50 hover:bg-ink-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {applyBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : null}
                {applyBusy ? "Applying mapper…" : "Apply mapper & preview"}
              </button>
              <span className="text-[11px] leading-snug text-ink-500">
                Converts uploads to internal (mid-layer) CSVs in{" "}
                <span className="font-mono text-ink-400">handshake/preview/</span>. Name files like{" "}
                <span className="font-mono">contacts.csv</span>, <span className="font-mono">invoices.csv</span>.
              </span>
            </div>
            <div className="grid min-h-0 flex-1 grid-cols-[minmax(180px,280px)_1fr]">
              <div className="min-h-0 overflow-hidden border-r border-ink-700">
                {handshakeFiles.length === 0 ? (
                  <div className="flex h-full items-center justify-center p-6 text-center text-sm text-ink-400">
                    No Phase 2.5 handshake files yet. Use <strong className="text-ink-200">Run handshake</strong>{" "}
                    in the header (map + codegen). Artifacts appear here as{" "}
                    <span className="font-mono text-ink-300">handshake_mapping.json</span> and{" "}
                    <span className="font-mono text-ink-300">handshake_run_mapper.py</span>.
                  </div>
                ) : (
                  <ArtifactTree
                    files={handshakeFiles}
                    selected={handshakeViewPath}
                    recent={recent}
                    onSelect={setSelected}
                  />
                )}
              </div>
              <div className="min-h-0 overflow-hidden">
                <ArtifactViewer path={handshakeViewPath} refreshKey={viewerKey} />
              </div>
            </div>
          </div>
        )}
        {tab === "commits" && <CommitHistory commits={commits} />}
        {tab === "uploads" && (
          <div className="grid h-full min-h-0 grid-cols-[minmax(180px,280px)_1fr]">
            <div className="min-h-0 overflow-hidden border-r border-ink-700">
              <UploadList
                uploads={uploads}
                selected={uploadSelected}
                onSelect={(path) => {
                  setUploadSelected(path);
                  setUploadViewerKey((k) => k + 1);
                }}
                onRemoveUpload={onRemoveUpload}
              />
            </div>
            <div className="min-h-0 overflow-hidden">
              <ArtifactViewer
                sessionId={sessionId}
                path={uploadSelected}
                refreshKey={uploadViewerKey}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function UploadList({
  uploads,
  selected,
  onSelect,
  onRemoveUpload,
}: {
  uploads: UploadedFile[];
  selected: string | null;
  onSelect: (clientPath: string) => void;
  onRemoveUpload: (clientPath: string) => void | Promise<void>;
}) {
  if (uploads.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-ink-400">
        No uploads in this session yet.
      </div>
    );
  }
  return (
    <ul className="h-full overflow-y-auto p-2">
      {uploads.map((u) => {
        const isSel = selected === u.path;
        return (
          <li key={u.path}>
            <div
              className={clsx(
                "flex items-center gap-1 rounded-md px-2 py-1.5",
                isSel ? "bg-brand/20 text-ink-50" : "text-ink-200 hover:bg-ink-800",
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(u.path)}
                className="min-w-0 flex-1 truncate text-left font-mono text-[12px]"
                title="View file"
              >
                {u.name}
              </button>
              <span className="shrink-0 text-[10px] text-ink-500">{fmtSize(u.size)}</span>
              <button
                type="button"
                onClick={() => onRemoveUpload(u.path)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-400 hover:bg-ink-800 hover:text-ink-100"
                title="Remove"
                aria-label={`Remove ${u.name}`}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
