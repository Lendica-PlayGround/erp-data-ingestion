"use client";

import clsx from "clsx";
import { File, FileCode, FileJson, FileText } from "lucide-react";
import type { ArtifactFile } from "@/lib/types";

type Props = {
  files: ArtifactFile[];
  selected: string | null;
  recent: Set<string>;
  onSelect: (path: string) => void;
};

function iconFor(path: string) {
  if (path.endsWith(".md")) return FileText;
  if (path.endsWith(".json")) return FileJson;
  if (path.endsWith(".csv")) return FileCode;
  return File;
}

export function ArtifactTree({ files, selected, recent, onSelect }: Props) {
  if (files.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-ink-400">
        No artifacts yet. Ask the agent to describe a table and watch this tree update live.
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto p-2">
      <ul className="space-y-0.5">
        {files.map((f) => {
          const Icon = iconFor(f.path);
          const isRecent = recent.has(f.path);
          return (
            <li key={f.path}>
              <button
                type="button"
                onClick={() => onSelect(f.path)}
                className={clsx(
                  "group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
                  selected === f.path
                    ? "bg-brand/20 text-ink-50"
                    : "text-ink-200 hover:bg-ink-800",
                  isRecent && "flash-new",
                )}
              >
                <Icon className="h-3.5 w-3.5 shrink-0 text-ink-400" />
                <span className="truncate font-mono text-[12px]">{f.path}</span>
                <span className="ml-auto text-[10px] text-ink-500">{fmtSize(f.size)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K`;
  return `${(bytes / 1024 / 1024).toFixed(1)}M`;
}
