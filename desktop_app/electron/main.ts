import path from "node:path";
import { spawn } from "node:child_process";
import fs from "node:fs";
import { randomUUID } from "node:crypto";

import chokidar, { type FSWatcher } from "chokidar";
import dotenv from "dotenv";
import { app, BrowserWindow, dialog, ipcMain } from "electron";

import { parseTemplate } from "./templateParser";

dotenv.config({ path: path.join(process.cwd(), ".env") });

let mainWindow: BrowserWindow | null = null;
let watcher: FSWatcher | null = null;
let currentFilePath: string | null = null;
const activeChatProcesses = new Map<string, ReturnType<typeof spawn>>();

const isDev = !app.isPackaged;

function resolvePythonExecutable(): string {
  if (process.env.PYTHON_EXECUTABLE) {
    return process.env.PYTHON_EXECUTABLE;
  }
  
  // Try to find local virtual environment relative to the desktop_app folder
  const projectRoot = isDev ? path.join(app.getAppPath(), "..") : path.join(app.getAppPath(), "..", "..");
  
  const venvWin = path.join(projectRoot, ".venv", "Scripts", "python.exe");
  const venvUnix = path.join(projectRoot, ".venv", "bin", "python");
  
  if (fs.existsSync(venvWin)) return venvWin;
  if (fs.existsSync(venvUnix)) return venvUnix;

  return "python";
}

function resolveChatBridgeScript(): string {
  return path.join(app.getAppPath(), "agent_bridge", "agent_chat_service.py");
}

function invokePythonChat(request: { message: string; payload?: unknown }): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const python = resolvePythonExecutable();
    const scriptPath = resolveChatBridgeScript();

    const child = spawn(python, ["-X", "utf8", scriptPath], {
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });

    child.on("error", (err) => {
      reject(err);
    });

    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Python 进程退出码: ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout || "{}"));
      } catch (err) {
        reject(err);
      }
    });

    child.stdin.write(JSON.stringify(request));
    child.stdin.end();
  });
}

type StreamEvent =
  | { type: "delta"; delta: string }
  | { type: "status"; status: string }
  | { type: "done"; response: unknown }
  | { type: "error"; error: string };

function emitChatStreamEvent(chatId: string, event: StreamEvent): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send("agent:chat:event", { chatId, ...event });
}

function invokePythonChatStream(chatId: string, request: { message: string; payload?: unknown }): void {
  const python = resolvePythonExecutable();
  const scriptPath = resolveChatBridgeScript();

  const child = spawn(python, ["-X", "utf8", scriptPath], {
    windowsHide: true,
    stdio: ["pipe", "pipe", "pipe"],
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    },
  });

  activeChatProcesses.set(chatId, child);

  let stdoutBuffer = "";
  let stderr = "";
  let finalized = false;

  const cleanup = () => {
    activeChatProcesses.delete(chatId);
  };

  const handleStreamLine = (line: string) => {
    if (!line.trim()) {
      return;
    }

    try {
      const parsed = JSON.parse(line) as StreamEvent;
      if (parsed.type === "delta") {
        emitChatStreamEvent(chatId, { type: "delta", delta: String(parsed.delta ?? "") });
        return;
      }
      if (parsed.type === "status") {
        emitChatStreamEvent(chatId, { type: "status", status: String((parsed as any).status ?? "") });
        return;
      }
      if (parsed.type === "done") {
        finalized = true;
        emitChatStreamEvent(chatId, { type: "done", response: parsed.response });
        return;
      }
      if (parsed.type === "error") {
        finalized = true;
        emitChatStreamEvent(chatId, { type: "error", error: String(parsed.error ?? "未知错误") });
        return;
      }
    } catch {
      // ignore malformed line and continue parsing subsequent lines
    }
  };

  child.stdout.on("data", (chunk: Buffer) => {
    stdoutBuffer += chunk.toString("utf-8");
    const lines = stdoutBuffer.split(/\r?\n/);
    stdoutBuffer = lines.pop() ?? "";
    for (const line of lines) {
      handleStreamLine(line);
    }
  });

  child.stderr.on("data", (chunk: Buffer) => {
    stderr += chunk.toString("utf-8");
  });

  child.on("error", (err) => {
    if (finalized) {
      cleanup();
      return;
    }
    finalized = true;
    emitChatStreamEvent(chatId, { type: "error", error: err.message });
    cleanup();
  });

  child.on("close", (code) => {
    if (stdoutBuffer.trim()) {
      handleStreamLine(stdoutBuffer.trim());
    }
    if (!finalized) {
      if (code === 0) {
        emitChatStreamEvent(chatId, {
          type: "error",
          error: "流式响应提前结束，未收到完成事件。",
        });
      } else {
        emitChatStreamEvent(chatId, {
          type: "error",
          error: stderr || `Python 进程退出码: ${code}`,
        });
      }
    }
    cleanup();
  });

  child.stdin.write(JSON.stringify({ ...request, stream: true }));
  child.stdin.end();
}

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 760,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.setMenu(null);

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

function setupWatcher(filePath: string): void {
  if (watcher) {
    watcher.close();
  }

  watcher = chokidar.watch(filePath, {
    ignoreInitial: true,
    awaitWriteFinish: {
      stabilityThreshold: 300,
      pollInterval: 100,
    },
  });

  watcher.on("change", async () => {
    if (!mainWindow || !currentFilePath) {
      return;
    }
    try {
      const preview = await parseTemplate(currentFilePath);
      mainWindow.webContents.send("template:update", preview);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      mainWindow.webContents.send("template:update", {
        filePath: currentFilePath,
        fileType: "unknown",
        updatedAt: new Date().toISOString(),
        textSections: [],
        sheets: [],
        warnings: ["文件更新后解析失败: " + message],
      });
    }
  });
}

ipcMain.handle("template:open", async () => {
  const result = await dialog.showOpenDialog({
    title: "选择模板文件",
    properties: ["openFile"],
    filters: [
      { name: "模板文件", extensions: ["xlsx", "xls", "docx"] },
      { name: "All Files", extensions: ["*"] },
    ],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  currentFilePath = result.filePaths[0];
  setupWatcher(currentFilePath);
  return currentFilePath;
});
ipcMain.handle("template:getProjectDir", () => {
  return isDev ? path.join(app.getAppPath(), "..") : path.join(app.getAppPath(), "..", "..");
});

ipcMain.handle("template:exportPredefined", async (_event, type: string) => {
  const root = isDev ? path.join(app.getAppPath(), "..") : path.join(app.getAppPath(), "..", "..");
  const templatesDir = path.join(root, "data", "templates");
  if (!fs.existsSync(templatesDir)) {
    fs.mkdirSync(templatesDir, { recursive: true });
  }
  let filename = "template.xlsx";
  if (type === "budget") filename = "预算表.xlsx";
  else if (type === "final") filename = "决算表.xlsx";
  else if (type === "compare") filename = "核对报告.docx";
  
  const targetPath = path.join(templatesDir, filename);
  if (!fs.existsSync(targetPath)) {
    // Generate a dummy file if not exists just to avoid crash
    // Because it's an excel/docx, creating empty file might be invalid, but we'll try to just write empty string or let user do it.
    // For now we touch the file so the watcher doesn't fail, but templateParser might fail on empty xlsx.
    // templateParser currently returns unknown if failed, which is fine.
    fs.writeFileSync(targetPath, "");
  }
  return targetPath;
});
ipcMain.handle("template:saveAs", async (_event, sourcePath: string) => {
  if (!fs.existsSync(sourcePath)) return null;

  const ext = path.extname(sourcePath);
  const defaultPath = `下载-${path.basename(sourcePath)}`;

  const result = await dialog.showSaveDialog({
    title: "保存文件",
    defaultPath,
    filters: [
      { name: "Documents", extensions: [ext.replace(".", "")] },
      { name: "All Files", extensions: ["*"] }
    ],
  });

  if (!result.canceled && result.filePath) {
    fs.copyFileSync(sourcePath, result.filePath);
    return result.filePath;
  }
  return null;
});

ipcMain.handle("template:preview", async (_event, filePath: string) => {
  currentFilePath = filePath;
  setupWatcher(filePath);
  return parseTemplate(filePath);
});

ipcMain.handle("template:unwatch", async () => {
  if (watcher) {
    await watcher.close();
    watcher = null;
  }
  currentFilePath = null;
});

ipcMain.handle("agent:chat", async (_event, request: { message: string; payload?: unknown }) => {
  return invokePythonChat(request);
});

ipcMain.handle("agent:chat:start", async (_event, request: { message: string; payload?: unknown }) => {
  const chatId = randomUUID();
  invokePythonChatStream(chatId, request);
  return { chatId };
});

ipcMain.handle("agent:chat:stop", async (_event, chatId: string) => {
  const process = activeChatProcesses.get(chatId);
  if (!process) {
    return;
  }
  process.kill();
  activeChatProcesses.delete(chatId);
});

app.whenReady().then(() => {
  createMainWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  if (watcher) {
    await watcher.close();
  }
  for (const child of activeChatProcesses.values()) {
    child.kill();
  }
  activeChatProcesses.clear();
});
