import { contextBridge, ipcRenderer } from "electron";

type ChatMessage = { role: "user" | "agent"; content: string };

const api = {
  getWorkspaceDir: async (): Promise<string | null> => ipcRenderer.invoke("pet:getWorkspaceDir"),
  chat: async (message: string, history: ChatMessage[]): Promise<{ ok: boolean; reply?: string; error?: string }> =>
    ipcRenderer.invoke("pet:chat", { message, history }),
  openMainWindow: async (): Promise<void> => ipcRenderer.invoke("pet:openMain"),
  closePetChat: async (): Promise<void> => ipcRenderer.invoke("pet:closeChat"),
  pickWorkspaceDir: async (): Promise<{ ok: boolean; dir?: string; message?: string }> =>
    ipcRenderer.invoke("pet:pickWorkspaceDir"),
  subscribeWorkspaceUpdate: (handler: (dir: string | null) => void): (() => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, dir: string | null) => handler(dir);
    ipcRenderer.on("pet:workspace-updated", wrapped);
    return () => ipcRenderer.removeListener("pet:workspace-updated", wrapped);
  },
};

contextBridge.exposeInMainWorld("petChatApi", api);
