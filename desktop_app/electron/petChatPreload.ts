import { contextBridge, ipcRenderer } from "electron";

type ChatMessage = { role: "user" | "agent"; content: string };

type ChatStreamEvent =
  | { chatId: string; type: "delta"; delta: string }
  | { chatId: string; type: "status"; status: string }
  | { chatId: string; type: "done"; response: unknown }
  | { chatId: string; type: "error"; error: string };

const api = {
  getWorkspaceDir: async (): Promise<string | null> => ipcRenderer.invoke("pet:getWorkspaceDir"),
  chat: async (message: string, history: ChatMessage[]): Promise<{ ok: boolean; reply?: string; error?: string }> =>
    ipcRenderer.invoke("pet:chat", { message, history }),
  startChatStream: async (
    message: string,
    history: ChatMessage[]
  ): Promise<{ ok: boolean; chatId?: string; error?: string }> =>
    ipcRenderer.invoke("pet:chat:start", { message, history }),
  stopChatStream: async (chatId: string): Promise<void> => ipcRenderer.invoke("pet:chat:stop", chatId),
  getChatHistory: async (): Promise<unknown> => ipcRenderer.invoke("chat:history:get"),
  setChatHistory: async (history: unknown): Promise<{ ok: boolean }> =>
    ipcRenderer.invoke("chat:history:set", history),
  openMainWindow: async (): Promise<void> => ipcRenderer.invoke("pet:openMain"),
  closePetChat: async (): Promise<void> => ipcRenderer.invoke("pet:closeChat"),
  pickWorkspaceDir: async (): Promise<{ ok: boolean; dir?: string; message?: string }> =>
    ipcRenderer.invoke("pet:pickWorkspaceDir"),
  subscribeWorkspaceUpdate: (handler: (dir: string | null) => void): (() => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, dir: string | null) => handler(dir);
    ipcRenderer.on("pet:workspace-updated", wrapped);
    return () => ipcRenderer.removeListener("pet:workspace-updated", wrapped);
  },
  subscribeChatEvent: (handler: (event: ChatStreamEvent) => void): (() => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: ChatStreamEvent) => handler(payload);
    ipcRenderer.on("pet:chat:event", wrapped);
    return () => ipcRenderer.removeListener("pet:chat:event", wrapped);
  },
  subscribeChatHistory: (handler: (history: unknown) => void): (() => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: unknown) => handler(payload);
    ipcRenderer.on("chat:history:update", wrapped);
    return () => ipcRenderer.removeListener("chat:history:update", wrapped);
  },
};

export type PetChatApi = typeof api;

contextBridge.exposeInMainWorld("petChatApi", api);
