import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";

export type TraceOperation =
  | "write_file"
  | "update_excel_cell"
  | "update_excel_range"
  | "append_excel_rows"
  | "trim_excel_sheet";

type SnapshotKind = "text" | "binary" | "missing";

type FileSnapshot = {
  kind: SnapshotKind;
  size: number;
  truncated: boolean;
  hash: string;
  content?: string;
};

type LineChange = {
  line: number;
  before: string;
  after: string;
};

type DiffSummary = {
  added: number;
  removed: number;
  changed: number;
  snippets: LineChange[];
};

export type EditTraceEvent = {
  id: string;
  timestamp: string;
  operation: TraceOperation;
  targetPath: string;
  status: "ok" | "failed";
  error?: string;
  meta?: Record<string, unknown>;
  before: Omit<FileSnapshot, "content">;
  after: Omit<FileSnapshot, "content">;
  diff?: DiffSummary;
  replayText?: string;
};

export type EditTraceEventDetail = EditTraceEvent & {
  beforeContent?: string;
  afterContent?: string;
};

export type EditTraceQuery = {
  targetPath?: string;
  operations?: TraceOperation[];
  status?: "ok" | "failed";
};

export type EditTraceSummary = {
  total: number;
  ok: number;
  failed: number;
  byOperation: Record<TraceOperation, number>;
};

const MAX_TRACE_EVENTS = 600;
const MAX_TEXT_CAPTURE_BYTES = 256 * 1024;
const SNIPPET_LIMIT = 10;

function isTextLike(filePath: string, buffer: Buffer): boolean {
  const ext = path.extname(filePath).toLowerCase();
  if ([".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".txt", ".py", ".cjs", ".mjs", ".css", ".html", ".yml", ".yaml"].includes(ext)) {
    return true;
  }
  return !buffer.includes(0);
}

function sha256OfBuffer(buffer: Buffer): string {
  return createHash("sha256").update(buffer).digest("hex");
}

function readSnapshot(filePath: string): FileSnapshot {
  if (!filePath || !fs.existsSync(filePath)) {
    return { kind: "missing", size: 0, truncated: false, hash: "" };
  }
  const stat = fs.statSync(filePath);
  if (!stat.isFile()) {
    return { kind: "missing", size: 0, truncated: false, hash: "" };
  }
  const full = fs.readFileSync(filePath);
  const hash = sha256OfBuffer(full);
  const slice = full.subarray(0, Math.min(full.length, MAX_TEXT_CAPTURE_BYTES));
  const truncated = full.length > MAX_TEXT_CAPTURE_BYTES;
  if (!isTextLike(filePath, slice)) {
    return {
      kind: "binary",
      size: full.length,
      truncated,
      hash,
    };
  }
  return {
    kind: "text",
    size: full.length,
    truncated,
    hash,
    content: slice.toString("utf-8"),
  };
}

function summarizeTextDiff(beforeText: string, afterText: string): DiffSummary {
  const beforeLines = beforeText.split(/\r?\n/);
  const afterLines = afterText.split(/\r?\n/);
  const total = Math.max(beforeLines.length, afterLines.length);

  let added = 0;
  let removed = 0;
  let changed = 0;
  const snippets: LineChange[] = [];

  for (let i = 0; i < total; i += 1) {
    const beforeLine = beforeLines[i];
    const afterLine = afterLines[i];
    if (beforeLine === undefined && afterLine !== undefined) {
      added += 1;
      if (snippets.length < SNIPPET_LIMIT) {
        snippets.push({ line: i + 1, before: "", after: afterLine });
      }
      continue;
    }
    if (beforeLine !== undefined && afterLine === undefined) {
      removed += 1;
      if (snippets.length < SNIPPET_LIMIT) {
        snippets.push({ line: i + 1, before: beforeLine, after: "" });
      }
      continue;
    }
    if (beforeLine !== afterLine) {
      changed += 1;
      if (snippets.length < SNIPPET_LIMIT) {
        snippets.push({ line: i + 1, before: beforeLine ?? "", after: afterLine ?? "" });
      }
    }
  }

  return { added, removed, changed, snippets };
}

export class EditTraceStore {
  private readonly events: EditTraceEventDetail[] = [];

  async recordMutation<T>(input: {
    operation: TraceOperation;
    targetPath: string;
    meta?: Record<string, unknown>;
    run: () => Promise<T> | T;
  }): Promise<T> {
    const beforeSnapshot = readSnapshot(input.targetPath);
    let result: T;
    let failed: unknown = null;
    try {
      result = await input.run();
    } catch (error) {
      failed = error;
      throw error;
    } finally {
      const afterSnapshot = readSnapshot(input.targetPath);
      const diff =
        beforeSnapshot.kind === "text" &&
        afterSnapshot.kind === "text" &&
        typeof beforeSnapshot.content === "string" &&
        typeof afterSnapshot.content === "string"
          ? summarizeTextDiff(beforeSnapshot.content, afterSnapshot.content)
          : undefined;
      const event: EditTraceEventDetail = {
        id: randomUUID(),
        timestamp: new Date().toISOString(),
        operation: input.operation,
        targetPath: input.targetPath,
        status: failed ? "failed" : "ok",
        error: failed ? (failed instanceof Error ? failed.message : String(failed)) : undefined,
        meta: input.meta,
        before: {
          kind: beforeSnapshot.kind,
          size: beforeSnapshot.size,
          truncated: beforeSnapshot.truncated,
          hash: beforeSnapshot.hash,
        },
        after: {
          kind: afterSnapshot.kind,
          size: afterSnapshot.size,
          truncated: afterSnapshot.truncated,
          hash: afterSnapshot.hash,
        },
        diff,
        replayText: afterSnapshot.kind === "text" ? afterSnapshot.content : undefined,
        beforeContent: beforeSnapshot.content,
        afterContent: afterSnapshot.content,
      };
      this.events.unshift(event);
      if (this.events.length > MAX_TRACE_EVENTS) {
        this.events.length = MAX_TRACE_EVENTS;
      }
    }
    return result!;
  }

  list(query?: EditTraceQuery): EditTraceEvent[] {
    const targetPath = String(query?.targetPath ?? "").trim();
    const status = query?.status;
    const operations = Array.isArray(query?.operations) ? query?.operations : [];

    return this.events
      .filter((event) => (targetPath ? event.targetPath.includes(targetPath) : true))
      .filter((event) => (status ? event.status === status : true))
      .filter((event) => (operations.length > 0 ? operations.includes(event.operation) : true))
      .map(({ beforeContent: _beforeContent, afterContent: _afterContent, ...rest }) => rest);
  }

  get(eventId: string): EditTraceEventDetail | null {
    return this.events.find((event) => event.id === eventId) ?? null;
  }

  clear(): void {
    this.events.length = 0;
  }

  summary(query?: EditTraceQuery): EditTraceSummary {
    const selected = this.list(query);
    const byOperation: Record<TraceOperation, number> = {
      write_file: 0,
      update_excel_cell: 0,
      update_excel_range: 0,
      append_excel_rows: 0,
      trim_excel_sheet: 0,
    };
    let ok = 0;
    let failed = 0;
    for (const event of selected) {
      byOperation[event.operation] += 1;
      if (event.status === "ok") {
        ok += 1;
      } else {
        failed += 1;
      }
    }
    return {
      total: selected.length,
      ok,
      failed,
      byOperation,
    };
  }
}
