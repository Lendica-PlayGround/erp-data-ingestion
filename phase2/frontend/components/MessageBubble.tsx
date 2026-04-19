"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CheckCircle2, ChevronRight, GitCommit, Loader2, Terminal, XCircle } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import type { ChatMessage } from "@/lib/types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={clsx("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/20 text-brand-soft">
          AI
        </div>
      )}
      <div
        className={clsx(
          "max-w-[85%] rounded-2xl px-4 py-3 text-[15px]",
          isUser
            ? "bg-brand text-white rounded-br-sm"
            : "bg-ink-800 text-ink-50 rounded-bl-sm border border-ink-700",
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap leading-relaxed">{message.content}</div>
        ) : (
          <AssistantBody message={message} />
        )}
      </div>
      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700 text-ink-100">
          You
        </div>
      )}
    </div>
  );
}

function AssistantBody({ message }: { message: ChatMessage }) {
  return (
    <div className="space-y-3">
      {message.toolCalls?.map((tc) => <ToolCallCard key={tc.id} call={tc} />)}
      {message.content && (
        <div className="prose-agent">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      )}
      {message.pending && !message.content && !message.toolCalls?.length && (
        <div className="flex items-center gap-2 text-ink-300 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> thinking...
        </div>
      )}
      {message.commits?.map((c) => (
        <div
          key={c.sha}
          className="flex items-start gap-2 rounded-lg border border-ink-700 bg-ink-900/50 px-3 py-2 text-xs text-ink-200"
        >
          <GitCommit className="mt-0.5 h-3.5 w-3.5 text-brand-soft" />
          <div>
            <div className="font-mono text-[11px] text-ink-300">{c.sha.slice(0, 7)}</div>
            <div>{c.message}</div>
            {c.files.length > 0 && (
              <div className="mt-0.5 text-ink-400">
                {c.files.slice(0, 4).join(", ")}
                {c.files.length > 4 && ` +${c.files.length - 4} more`}
              </div>
            )}
          </div>
        </div>
      ))}
      {message.error && (
        <div className="rounded-lg border border-red-700/50 bg-red-900/20 px-3 py-2 text-xs text-red-200">
          {message.error}
        </div>
      )}
    </div>
  );
}

function ToolCallCard({ call }: { call: NonNullable<ChatMessage["toolCalls"]>[number] }) {
  const [open, setOpen] = useState(false);
  const Icon =
    call.status === "running" ? Loader2 : call.status === "ok" ? CheckCircle2 : XCircle;
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/50 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-ink-800/50"
      >
        <ChevronRight className={clsx("h-3 w-3 transition-transform", open && "rotate-90")} />
        <Terminal className="h-3.5 w-3.5 text-brand-soft" />
        <span className="font-mono font-semibold text-ink-100">{call.name}</span>
        <span className="ml-auto flex items-center gap-1 text-[11px] text-ink-300">
          <Icon
            className={clsx(
              "h-3.5 w-3.5",
              call.status === "running" && "animate-spin",
              call.status === "ok" && "text-emerald-400",
              call.status === "error" && "text-red-400",
            )}
          />
          {call.status}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-ink-700 px-3 py-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ink-400">arguments</div>
            <pre className="mt-1 overflow-x-auto rounded bg-ink-900 p-2 font-mono text-[11px] text-ink-100">
              {JSON.stringify(call.arguments, null, 2)}
            </pre>
          </div>
          {call.result !== undefined && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-400">result</div>
              <pre className="mt-1 max-h-64 overflow-auto rounded bg-ink-900 p-2 font-mono text-[11px] text-ink-100">
                {call.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
