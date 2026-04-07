export type TraceOperation =
  | "write_file"
  | "update_excel_cell"
  | "update_excel_range"
  | "append_excel_rows"
  | "trim_excel_sheet";

export type TraceSnapshotMeta = {
  kind: "text" | "binary" | "missing";
  size: number;
  truncated: boolean;
  hash: string;
};

export type TraceDiffSummary = {
  added: number;
  removed: number;
  changed: number;
  snippets: Array<{
    line: number;
    before: string;
    after: string;
  }>;
};

export type EditTraceEvent = {
  id: string;
  timestamp: string;
  operation: TraceOperation;
  targetPath: string;
  status: "ok" | "failed";
  error?: string;
  meta?: Record<string, unknown>;
  before: TraceSnapshotMeta;
  after: TraceSnapshotMeta;
  diff?: TraceDiffSummary;
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
