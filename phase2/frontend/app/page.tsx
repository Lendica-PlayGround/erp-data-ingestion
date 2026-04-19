"use client";

import { useCallback, useEffect, useState } from "react";
import { Chat } from "@/components/Chat";
import { WorkspacePanel } from "@/components/WorkspacePanel";
import type { UploadedFile } from "@/lib/types";
import { deleteSessionUpload, listSessionUploads, runHandshakePipeline } from "@/lib/api";
import { Loader2 } from "lucide-react";

function makeSessionId(): string {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export default function Page() {
  const [sessionId, setSessionId] = useState<string>("");
  const [uploads, setUploads] = useState<UploadedFile[]>([]);
  const [changeToken, setChangeToken] = useState(0);
  const [commitToken, setCommitToken] = useState(0);
  const [handshakeBusy, setHandshakeBusy] = useState(false);

  // Hydrate / persist session id on client only.
  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("phase2.sid") : null;
    const sid = stored && stored.length > 2 ? stored : makeSessionId();
    if (!stored) window.localStorage.setItem("phase2.sid", sid);
    setSessionId(sid);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    listSessionUploads(sessionId).then(setUploads).catch(console.error);
  }, [sessionId]);

  const onCommit = useCallback(() => setCommitToken((t) => t + 1), []);
  const onFileWritten = useCallback(() => setChangeToken((t) => t + 1), []);

  const runHandshake = useCallback(async () => {
    if (handshakeBusy || !sessionId) return;
    setHandshakeBusy(true);
    try {
      const r = await runHandshakePipeline(sessionId);
      setChangeToken((t) => t + 1);
      if (r.ok) {
        alert(
          `Handshake complete.\n\nArtifacts in workspace:\n${r.artifacts.length ? r.artifacts.join("\n") : "(none)"}`,
        );
      } else {
        const failed = r.steps.find((s) => !s.ok);
        const stderr = failed?.stderr?.slice(0, 4000) ?? "";
        const hint = failed
          ? `${failed.step} failed (exit ${failed.returncode}).\n\nstderr:\n${stderr}`
          : "Unknown failure.";
        const partial =
          r.map_ok && r.codegen_ok === false
            ? "\n\nNote: Column mapping (map) succeeded — handshake_mapping.json was written. Codegen (Python script) failed; fix stderr below or run: cd phase2.5 && python -m handshake_mapping codegen …"
            : "";
        alert(`Handshake did not finish successfully.${partial}\n\n${hint}`);
      }
    } catch (e) {
      alert("Handshake failed: " + (e as Error).message);
    } finally {
      setHandshakeBusy(false);
    }
  }, [handshakeBusy, sessionId]);

  const removeUpload = useCallback(
    async (clientPath: string) => {
      try {
        await deleteSessionUpload(sessionId, clientPath);
        setUploads((prev) => prev.filter((u) => u.path !== clientPath));
      } catch (e) {
        console.error(e);
        alert("Remove failed: " + (e as Error).message);
      }
    },
    [sessionId],
  );

  if (!sessionId) {
    return <div className="flex h-screen items-center justify-center text-ink-300">Loading...</div>;
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-ink-700 bg-ink-900 px-4 py-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand/20 text-brand-soft font-bold">
            P2
          </div>
          <div>
            <div className="text-sm font-semibold text-ink-50">Phase 2 Exploration Agent</div>
            <div className="text-[11px] text-ink-400">
              ERP data ingestion — structured table + column discovery
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-ink-400">
          <button
            type="button"
            onClick={() => void runHandshake()}
            disabled={handshakeBusy}
            title="Run Phase 2.5: AI column handshake (map) then generate Python mapper (codegen). Uses this session’s uploaded source files (csv/tsv/txt/json, any filenames) for codegen previews."
            className="inline-flex items-center gap-1.5 rounded-md border border-white/20 bg-brand px-3 py-1.5 text-xs font-semibold text-white shadow-md shadow-black/30 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {handshakeBusy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : null}
            {handshakeBusy ? "Running handshake…" : "Run handshake"}
          </button>
          <span className="hidden font-mono sm:inline">{sessionId}</span>
          <button
            type="button"
            onClick={() => {
              const next = makeSessionId();
              window.localStorage.setItem("phase2.sid", next);
              window.location.reload();
            }}
            className="rounded border border-ink-700 px-2 py-1 text-ink-200 hover:bg-ink-800"
          >
            new session
          </button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section className="flex min-h-0 min-h-[45vh] flex-1 flex-col border-b border-ink-700 lg:min-h-0 lg:border-b-0 lg:border-r">
          <Chat
            sessionId={sessionId}
            uploads={uploads}
            onUploadsChanged={setUploads}
            onRemoveUpload={removeUpload}
            onCommit={onCommit}
            onFileWritten={onFileWritten}
          />
        </section>
        <section className="flex min-h-0 min-h-[35vh] flex-1 flex-col lg:min-h-0">
          <WorkspacePanel
            sessionId={sessionId}
            uploads={uploads}
            onRemoveUpload={removeUpload}
            changeToken={changeToken}
            commitToken={commitToken}
            onArtifactsChanged={() => setChangeToken((t) => t + 1)}
          />
        </section>
      </main>
    </div>
  );
}
