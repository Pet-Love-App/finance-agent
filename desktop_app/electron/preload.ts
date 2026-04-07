import { contextBridge, ipcRenderer } from "electron";

import type { TemplatePreview } from "./templateParser";

type Unsubscribe = () => void;

type AgentChatStreamEvent =
  | { chatId: string; type: "delta"; delta: string }
  | { chatId: string; type: "status"; status: string }
  | { chatId: string; type: "done"; response: unknown }
  | { chatId: string; type: "error"; error: string };

type ChatSessionMeta = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};

type ChatSessionsState = {
  activeSessionId: string | null;
  sessions: ChatSessionMeta[];
};

type LlmProvider = "openai" | "glm" | "deepseek" | "qwen" | "anthropic" | "custom";
type LlmConfig = {
  provider: LlmProvider;
  apiKey: string;
  baseUrl: string;
  model: string;
};

type TraceOperation =
  | "write_file"
  | "update_excel_cell"
  | "update_excel_range"
  | "append_excel_rows"
  | "trim_excel_sheet";

type TraceSnapshotMeta = {
  kind: "text" | "binary" | "missing";
  size: number;
  truncated: boolean;
  hash: string;
};

type TraceDiffSummary = {
  added: number;
  removed: number;
  changed: number;
  snippets: Array<{
    line: number;
    before: string;
    after: string;
  }>;
};

type EditTraceEvent = {
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

type EditTraceEventDetail = EditTraceEvent & {
  beforeContent?: string;
  afterContent?: string;
};

type EditTraceQuery = {
  targetPath?: string;
  operations?: TraceOperation[];
  status?: "ok" | "failed";
};

type EditTraceSummary = {
  total: number;
  ok: number;
  failed: number;
  byOperation: Record<TraceOperation, number>;
};

const api = {
  openTemplate: async (): Promise<string | null> => ipcRenderer.invoke("template:open"),
  getPredefinedTemplate: async (type: string): Promise<string> => ipcRenderer.invoke("template:exportPredefined", type),
  saveAs: async (sourcePath: string): Promise<string | null> => ipcRenderer.invoke("template:saveAs", sourcePath),
  openLocalPath: async (targetPath: string): Promise<{ ok: boolean; message?: string }> =>
    ipcRenderer.invoke("template:openPath", targetPath),
  getProjectDir: async (): Promise<string> => ipcRenderer.invoke("template:getProjectDir"),
  pickProjectDir: async (): Promise<{ ok: boolean; dir?: string; message?: string }> =>
    ipcRenderer.invoke("template:pickDir"),
  listDir: async (
    dirPath: string
  ): Promise<{ ok: boolean; entries?: Array<{ name: string; path: string; isDir: boolean }>; error?: string }> =>
    ipcRenderer.invoke("template:listDir", dirPath),
  readFile: async (targetPath: string): Promise<unknown> => ipcRenderer.invoke("template:readFile", targetPath),
  writeFile: async (
    targetPath: string,
    content: string
  ): Promise<{ ok: boolean; filePath?: string; updatedAt?: string; error?: string }> =>
    ipcRenderer.invoke("template:writeFile", { targetPath, content }),
  updateExcelCell: async (
    targetPath: string,
    sheetName: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ): Promise<{ ok: boolean; updatedAt?: string; error?: string }> =>
    ipcRenderer.invoke("template:updateExcelCell", {
      targetPath,
      sheetName,
      rowIndex,
      colIndex,
      value,
    }),
  updateExcelRange: async (
    targetPath: string,
    sheetName: string,
    startRowIndex: number,
    startColIndex: number,
    values: string[][]
  ): Promise<{ ok: boolean; updatedAt?: string; error?: string }> =>
    ipcRenderer.invoke("template:updateExcelRange", {
      targetPath,
      sheetName,
      startRowIndex,
      startColIndex,
      values,
    }),
  appendExcelRows: async (
    targetPath: string,
    sheetName: string,
    count: number
  ): Promise<{ ok: boolean; updatedAt?: string; error?: string }> =>
    ipcRenderer.invoke("template:appendExcelRows", {
      targetPath,
      sheetName,
      count,
    }),
  trimExcelSheet: async (
    targetPath: string,
    sheetName: string,
    axis: "row" | "col",
    count: number
  ): Promise<{ ok: boolean; updatedAt?: string; error?: string }> =>
    ipcRenderer.invoke("template:trimExcelSheet", {
      targetPath,
      sheetName,
      axis,
      count,
    }),
  listEditTrace: async (query?: string | EditTraceQuery): Promise<EditTraceEvent[]> =>
    ipcRenderer.invoke("trace:list", query),
  getEditTrace: async (eventId: string): Promise<EditTraceEventDetail | null> =>
    ipcRenderer.invoke("trace:get", eventId),
  replayEditTrace: async (
    eventId: string
  ): Promise<{ ok: boolean; targetPath?: string; content?: string; timestamp?: string; error?: string }> =>
    ipcRenderer.invoke("trace:replay", eventId),
  clearEditTrace: async (): Promise<{ ok: boolean }> => ipcRenderer.invoke("trace:clear"),
  getEditTraceSummary: async (query?: string | EditTraceQuery): Promise<EditTraceSummary> =>
    ipcRenderer.invoke("trace:summary", query),
  exportEditTrace: async (
    query?: string | EditTraceQuery
  ): Promise<{ ok: boolean; filePath?: string; count?: number; message?: string }> =>
    ipcRenderer.invoke("trace:export", query),
  getPreview: async (filePath: string): Promise<TemplatePreview> =>
    ipcRenderer.invoke("template:preview", filePath),
  subscribePreviewUpdate: (handler: (payload: TemplatePreview) => void): Unsubscribe => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: TemplatePreview) => {
      handler(payload);
    };
    ipcRenderer.on("template:update", wrapped);
    return () => ipcRenderer.removeListener("template:update", wrapped);
  },
  unwatchTemplate: async (): Promise<void> => ipcRenderer.invoke("template:unwatch"),
  chatWithAgent: async (message: string, payload?: unknown): Promise<unknown> =>
    ipcRenderer.invoke("agent:chat", { message, payload }),
  runAgentTask: async (taskType: string, taskPayload?: unknown): Promise<unknown> =>
    ipcRenderer.invoke("agent:task", { taskType, taskPayload }),
  startAgentChatStream: async (
    message: string,
    payload?: unknown
  ): Promise<{ chatId: string }> => ipcRenderer.invoke("agent:chat:start", { message, payload }),
  startAgentTaskStream: async (
    taskType: string,
    taskPayload?: unknown
  ): Promise<{ chatId: string }> => ipcRenderer.invoke("agent:task:start", { taskType, taskPayload }),
  stopAgentChatStream: async (chatId: string): Promise<void> => ipcRenderer.invoke("agent:chat:stop", chatId),
  getChatHistory: async (): Promise<unknown> => ipcRenderer.invoke("chat:history:get"),
  setChatHistory: async (history: unknown): Promise<{ ok: boolean }> =>
    ipcRenderer.invoke("chat:history:set", history),
  listChatSessions: async (): Promise<ChatSessionsState> => ipcRenderer.invoke("chat:sessions:list"),
  createChatSession: async (title?: string): Promise<unknown> =>
    ipcRenderer.invoke("chat:sessions:create", { title }),
  switchChatSession: async (
    sessionId: string
  ): Promise<{ ok: boolean; activeSessionId?: string; history?: unknown; error?: string }> =>
    ipcRenderer.invoke("chat:sessions:switch", sessionId),
  renameChatSession: async (sessionId: string, title: string): Promise<{ ok: boolean; error?: string }> =>
    ipcRenderer.invoke("chat:sessions:rename", { sessionId, title }),
  deleteChatSession: async (
    sessionId: string
  ): Promise<{ ok: boolean; activeSessionId?: string; history?: unknown; error?: string }> =>
    ipcRenderer.invoke("chat:sessions:delete", sessionId),
  getLlmConfig: async (): Promise<LlmConfig> => ipcRenderer.invoke("llm:config:get"),
  setLlmConfig: async (config: Partial<LlmConfig>): Promise<{ ok: boolean; config: LlmConfig }> =>
    ipcRenderer.invoke("llm:config:set", config),
  subscribeChatHistory: (handler: (history: unknown) => void): Unsubscribe => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: unknown) => {
      handler(payload);
    };
    ipcRenderer.on("chat:history:update", wrapped);
    return () => ipcRenderer.removeListener("chat:history:update", wrapped);
  },
  subscribeChatSessions: (handler: (payload: ChatSessionsState) => void): Unsubscribe => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: ChatSessionsState) => {
      handler(payload);
    };
    ipcRenderer.on("chat:sessions:update", wrapped);
    return () => ipcRenderer.removeListener("chat:sessions:update", wrapped);
  },
  subscribeAgentChatEvent: (handler: (event: AgentChatStreamEvent) => void): Unsubscribe => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: AgentChatStreamEvent) => {
      handler(payload);
    };
    ipcRenderer.on("agent:chat:event", wrapped);
    return () => ipcRenderer.removeListener("agent:chat:event", wrapped);
  },
  subscribeLlmConfig: (handler: (config: LlmConfig) => void): Unsubscribe => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: LlmConfig) => {
      handler(payload);
    };
    ipcRenderer.on("llm:config:updated", wrapped);
    return () => ipcRenderer.removeListener("llm:config:updated", wrapped);
  },
};

contextBridge.exposeInMainWorld("templateApi", api);

export type TemplateApi = typeof api;
