"use client";

import { Paperclip, Send, X } from "lucide-react";
import { useRef, useState } from "react";
import clsx from "clsx";
import type { UploadedFile } from "@/lib/types";
import { uploadFiles } from "@/lib/api";
import { ArtifactViewer } from "./ArtifactViewer";

type Props = {
  sessionId: string;
  busy: boolean;
  uploads: UploadedFile[];
  onUploaded: (files: UploadedFile[]) => void;
  onRemoveUpload: (clientPath: string) => void | Promise<void>;
  onSend: (text: string) => void;
  onCancel: () => void;
};

export function Composer({
  sessionId,
  busy,
  uploads,
  onUploaded,
  onRemoveUpload,
  onSend,
  onCancel,
}: Props) {
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  /** Client path ``uploads/...`` — preview in composer when set. */
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const canSend = text.trim().length > 0 && !busy;

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const uploaded = await uploadFiles(sessionId, Array.from(files));
      onUploaded(uploaded);
      if (uploaded[0]?.path) {
        setPreviewPath(uploaded[0].path);
        setPreviewKey((k) => k + 1);
      }
    } catch (err) {
      console.error(err);
      alert("Upload failed: " + (err as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  function submit() {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }

  return (
    <div className="border-t border-ink-700 bg-ink-900/60 backdrop-blur">
      <p className="px-4 pt-2 text-[11px] text-ink-300">
        Use <span className="font-medium text-ink-200">Upload</span> or drag files onto this bar — then type a message and send.
      </p>
      {uploads.length > 0 && (
        <div className="border-b border-ink-800 px-4 py-2">
          <div className="flex flex-wrap gap-2">
            {uploads.map((u) => {
              const open = previewPath === u.path;
              return (
                <span
                  key={u.path}
                  className={clsx(
                    "flex items-center gap-1.5 rounded-full border py-1 pl-3 pr-1 text-xs text-ink-100",
                    open
                      ? "border-brand/60 bg-brand/15 ring-1 ring-brand/30"
                      : "border-ink-700 bg-ink-800",
                  )}
                >
                  <button
                    type="button"
                    disabled={uploading || busy}
                    onClick={() => {
                      setPreviewPath((p) => (p === u.path ? null : u.path));
                      setPreviewKey((k) => k + 1);
                    }}
                    className="flex min-w-0 items-center gap-1.5 rounded-l-full text-left hover:text-ink-50 disabled:opacity-40"
                    title="View file"
                  >
                    <Paperclip className="h-3 w-3 shrink-0 text-brand-soft" />
                    <span className="max-w-[200px] truncate font-mono text-[11px] sm:max-w-[280px]">{u.name}</span>
                    <span className="shrink-0 text-ink-400">{fmtSize(u.size)}</span>
                  </button>
                  <button
                    type="button"
                    disabled={uploading || busy}
                    onClick={() => {
                      onRemoveUpload(u.path);
                      if (previewPath === u.path) setPreviewPath(null);
                    }}
                    className="ml-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-ink-400 hover:bg-ink-700 hover:text-ink-100 disabled:opacity-40"
                    title="Remove attachment"
                    aria-label={`Remove ${u.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
              );
            })}
          </div>
          {previewPath && (
            <div className="mt-3 rounded-lg border border-ink-700 bg-ink-900/80">
              <div className="flex items-center justify-between border-b border-ink-800 px-2 py-1">
                <span className="truncate font-mono text-[10px] text-ink-400">{previewPath}</span>
                <button
                  type="button"
                  onClick={() => setPreviewPath(null)}
                  className="shrink-0 rounded px-2 py-0.5 text-[11px] text-ink-400 hover:bg-ink-800 hover:text-ink-100"
                >
                  Close
                </button>
              </div>
              <div className="max-h-64 min-h-[100px]">
                <ArtifactViewer
                  sessionId={sessionId}
                  path={previewPath}
                  refreshKey={previewKey}
                />
              </div>
            </div>
          )}
        </div>
      )}
      <div
        className="flex items-end gap-2 px-4 py-3"
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (uploading || busy) return;
          handleFiles(e.dataTransfer.files);
        }}
      >
        <button
          type="button"
          disabled={uploading || busy}
          onClick={() => fileInput.current?.click()}
          className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-ink-600 bg-ink-800 px-3 text-sm font-medium text-ink-100 hover:border-brand hover:bg-ink-700 disabled:opacity-50"
          title="Upload CSV, JSON, PDF, TXT, Markdown…"
        >
          <Paperclip className="h-4 w-4 shrink-0 text-brand-soft" />
          <span>Upload</span>
        </button>
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          multiple
          accept=".csv,.json,.md,.txt,.pdf,.tsv,.yaml,.yml,.xlsx,.xlsm"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder={
            busy
              ? "Agent is working..."
              : "Describe the dataset, paste an API endpoint, ask a question..."
          }
          disabled={busy}
          className="max-h-48 min-h-[2.5rem] flex-1 resize-none rounded-lg border border-ink-700 bg-ink-800 px-3 py-2 text-[15px] text-ink-50 outline-none focus:border-brand disabled:opacity-60"
        />
        {busy ? (
          <button
            type="button"
            onClick={onCancel}
            className="flex h-10 items-center gap-1.5 rounded-lg bg-red-600/80 px-3 text-sm font-medium text-white hover:bg-red-600"
          >
            <X className="h-4 w-4" /> stop
          </button>
        ) : (
          <button
            type="button"
            disabled={!canSend}
            onClick={submit}
            className={clsx(
              "flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium",
              canSend
                ? "bg-brand text-white hover:bg-brand-soft"
                : "cursor-not-allowed bg-ink-700 text-ink-400",
            )}
          >
            <Send className="h-4 w-4" /> send
          </button>
        )}
      </div>
    </div>
  );
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
