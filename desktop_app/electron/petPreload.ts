import { contextBridge, ipcRenderer } from "electron";

const api = {
  openMainWindow: async (): Promise<void> => {
    await ipcRenderer.invoke("pet:openMain");
  },
  openChatWindow: async (): Promise<void> => {
    await ipcRenderer.invoke("pet:openChat");
  },
  setWorkspaceDir: async (dirPath: string): Promise<{ ok: boolean; message?: string; dir?: string }> => {
    return ipcRenderer.invoke("pet:setWorkspaceDir", dirPath);
  },
  pickWorkspaceDir: async (): Promise<{ ok: boolean; dir?: string; message?: string }> => {
    return ipcRenderer.invoke("pet:pickWorkspaceDir");
  },
  beginMove: async (screenX: number, screenY: number): Promise<void> => {
    await ipcRenderer.invoke("pet:move:begin", { screenX, screenY });
  },
  moveTo: async (screenX: number, screenY: number): Promise<void> => {
    await ipcRenderer.invoke("pet:move:update", { screenX, screenY });
  },
  endMove: async (): Promise<void> => {
    await ipcRenderer.invoke("pet:move:end");
  },
};

export type PetApi = typeof api;

contextBridge.exposeInMainWorld("petApi", api);
