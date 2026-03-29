import { contextBridge, ipcRenderer } from "electron";

import type { TemplatePreview } from "./templateParser";

type Unsubscribe = () => void;

type AgentChatStreamEvent =
  | { chatId: string; type: "delta"; delta: string }
  | { chatId: string; type: "status"; status: string }
  | { chatId: string; type: "done"; response: unknown }
  | { chatId: string; type: "error"; error: string };

const api = {
  openTemplate: async (): Promise<string | null> => ipcRenderer.invoke("template:open"),
  getPredefinedTemplate: async (type: string): Promise<string> => ipcRenderer.invoke("template:exportPredefined", type),
  saveAs: async (sourcePath: string): Promise<string | null> => ipcRenderer.invoke("template:saveAs", sourcePath),
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
  startAgentChatStream: async (
    message: string,
    payload?: unknown
  ): Promise<{ chatId: string }> => ipcRenderer.invoke("agent:chat:start", { message, payload }),
  stopAgentChatStream: async (chatId: string): Promise<void> => ipcRenderer.invoke("agent:chat:stop", chatId),
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
