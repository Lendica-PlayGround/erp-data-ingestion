"use client";

import { useState } from "react";
import clsx from "clsx";
import { ChevronRight, GitCommit } from "lucide-react";
import type { CommitSummary } from "@/lib/types";
import { commitDiff } from "@/lib/api";

export function CommitHistory({ commits }: { commits: CommitSummary[] }) {
  const [openSha, setOpenSha] = useState<string | null>(null);
  const [diff, setDiff] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function toggle(sha: string) {
    if (openSha === sha) {
      setOpenSha(null);
      setDiff("");
      return;
    }
    setOpenSha(sha);
    setLoading(true);
    try {
      setDiff(await commitDiff(sha));
    } catch (err) {
      setDiff(`error: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  if (commits.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-ink-400">
        No commits yet. The agent commits automatically after writing artifacts.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <ul className="divide-y divide-ink-800">
        {commits.map((c) => (
          <li key={c.sha}>
            <button
              type="button"
              onClick={() => toggle(c.sha)}
              className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-ink-800"
            >
              <ChevronRight
                className={clsx(
                  "mt-1 h-3 w-3 transition-transform",
                  openSha === c.sha && "rotate-90",
                )}
              />
              <GitCommit className="mt-0.5 h-3.5 w-3.5 text-brand-soft" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-ink-300">{c.short_sha}</span>
                  <span className="text-[11px] text-ink-400">{relTime(c.timestamp)}</span>
                  <span className="truncate text-[11px] text-ink-400">{c.author}</span>
                </div>
                <div className="truncate text-ink-100">{c.message}</div>
                {c.files.length > 0 && (
                  <div className="mt-0.5 truncate text-[11px] text-ink-400">
                    {c.files.slice(0, 5).join(", ")}
                    {c.files.length > 5 && ` +${c.files.length - 5}`}
                  </div>
                )}
              </div>
            </button>
            {openSha === c.sha && (
              <pre className="max-h-96 overflow-auto bg-ink-900 px-3 py-2 font-mono text-[11px] text-ink-100">
                {loading ? "loading diff..." : diff}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function relTime(epochSeconds: number): string {
  const delta = Date.now() / 1000 - epochSeconds;
  if (delta < 60) return `${Math.max(1, Math.round(delta))}s ago`;
  if (delta < 3600) return `${Math.round(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.round(delta / 3600)}h ago`;
  return `${Math.round(delta / 86400)}d ago`;
}
