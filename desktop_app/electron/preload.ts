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
};

contextBridge.exposeInMainWorld("templateApi", api);

export type TemplateApi = typeof api;
