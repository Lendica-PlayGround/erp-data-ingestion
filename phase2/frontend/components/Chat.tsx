"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import type { AgentEvent, ChatMessage, UploadedFile } from "@/lib/types";
import { parseSSE } from "@/lib/sse";

type Props = {
  sessionId: string;
  uploads: UploadedFile[];
  onUploadsChanged: (files: UploadedFile[]) => void;
  onRemoveUpload: (clientPath: string) => void | Promise<void>;
  onCommit: () => void;
  onFileWritten: () => void;
};

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function Chat({
  sessionId,
  uploads,
  onUploadsChanged,
  onRemoveUpload,
  onCommit,
  onFileWritten,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi — I'm the Phase 2 Exploration Agent.\n\nUpload a CSV or JSON, paste an API endpoint + key, or drop in a documentation URL, and I'll produce a structured table description and column info under `phase2/output/`. I'll commit each table as I go so you can track progress.",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = { id: uid(), role: "user", content: text };
      const assistantId = uid();
      const assistantStub: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        toolCalls: [],
        commits: [],
        pending: true,
      };
      const nextHistory = [...messages, userMsg];
      setMessages([...nextHistory, assistantStub]);
      setBusy(true);

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            messages: nextHistory.map((m) => ({ role: m.role, content: m.content })),
          }),
          signal: ac.signal,
        });
        if (!res.ok) throw new Error(`chat ${res.status}`);

        for await (const evt of parseSSE<AgentEvent>(res, ac.signal)) {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? applyEvent(m, evt) : m)),
          );
          if (evt.type === "commit") onCommit();
          if (evt.type === "tool_result" && evt.name === "write_file" && evt.ok) onFileWritten();
          if (evt.type === "end" || evt.type === "done" || evt.type === "error") {
            // Stream end is also signalled via the SSE iterator returning.
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, pending: false, error: (err as Error).message }
                : m,
            ),
          );
        }
      } finally {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, pending: false } : m)),
        );
        setBusy(false);
        abortRef.current = null;
      }
    },
    [messages, sessionId, onCommit, onFileWritten],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </div>
      </div>
      <Composer
        sessionId={sessionId}
        busy={busy}
        uploads={uploads}
        onUploaded={(fs) => onUploadsChanged([...uploads, ...fs])}
        onRemoveUpload={onRemoveUpload}
        onSend={send}
        onCancel={cancel}
      />
    </div>
  );
}

function applyEvent(msg: ChatMessage, evt: AgentEvent): ChatMessage {
  switch (evt.type) {
    case "token":
      return { ...msg, content: (msg.content ?? "") + evt.text, pending: true };
    case "tool_start": {
      const calls = [...(msg.toolCalls ?? [])];
      calls.push({
        id: evt.id,
        name: evt.name,
        arguments: evt.arguments,
        status: "running",
      });
      return { ...msg, toolCalls: calls };
    }
    case "tool_result": {
      const calls = (msg.toolCalls ?? []).map((c) =>
        c.id === evt.id
          ? { ...c, status: evt.ok ? ("ok" as const) : ("error" as const), result: evt.result }
          : c,
      );
      return { ...msg, toolCalls: calls };
    }
    case "commit": {
      const commits = [
        ...(msg.commits ?? []),
        {
          sha: evt.sha,
          short_sha: evt.sha,
          message: evt.message,
          timestamp: Date.now() / 1000,
          author: "agent",
          files: evt.files,
        },
      ];
      return { ...msg, commits };
    }
    case "error":
      return { ...msg, error: evt.message, pending: false };
    case "done":
    case "end":
      return { ...msg, pending: false };
    default:
      return msg;
  }
}
