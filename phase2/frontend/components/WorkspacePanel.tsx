"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { ArtifactTree } from "./ArtifactTree";
import { ArtifactViewer } from "./ArtifactViewer";
import { CommitHistory } from "./CommitHistory";
import type { ArtifactFile, CommitSummary, UploadedFile } from "@/lib/types";
import { X } from "lucide-react";
import { listArtifacts, listCommits } from "@/lib/api";

type Tab = "files" | "commits" | "uploads";

type Props = {
  sessionId: string;
  uploads: UploadedFile[];
  onRemoveUpload: (clientPath: string) => void | Promise<void>;
  changeToken: number;
  commitToken: number;
};

const RECENT_MS = 10_000;

export function WorkspacePanel({
  sessionId,
  uploads,
  onRemoveUpload,
  changeToken,
  commitToken,
}: Props) {
  const [tab, setTab] = useState<Tab>("files");
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [commits, setCommits] = useState<CommitSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [recent, setRecent] = useState<Set<string>>(new Set());
  const [viewerKey, setViewerKey] = useState(0);
  const eventsAbortRef = useRef<AbortController | null>(null);

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

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-ink-700 px-2">
        {(["files", "commits", "uploads"] as Tab[]).map((t) => (
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
            {t}
            {t === "files" && files.length > 0 && (
              <span className="ml-1.5 rounded-full bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-200">
                {files.length}
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
        {tab === "commits" && <CommitHistory commits={commits} />}
        {tab === "uploads" && <UploadList uploads={uploads} onRemoveUpload={onRemoveUpload} />}
      </div>
    </div>
  );
}

function UploadList({
  uploads,
  onRemoveUpload,
}: {
  uploads: UploadedFile[];
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
    <ul className="divide-y divide-ink-800">
      {uploads.map((u) => (
        <li key={u.path} className="flex items-center gap-2 px-2 py-2 text-sm">
          <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink-100">{u.name}</span>
          <span className="shrink-0 text-[11px] text-ink-400">{fmtSize(u.size)}</span>
          {u.content_type && (
            <span className="hidden shrink-0 text-[11px] text-ink-500 sm:inline">{u.content_type}</span>
          )}
          <button
            type="button"
            onClick={() => onRemoveUpload(u.path)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-400 hover:bg-ink-800 hover:text-ink-100"
            title="Remove"
            aria-label={`Remove ${u.name}`}
          >
            <X className="h-4 w-4" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
