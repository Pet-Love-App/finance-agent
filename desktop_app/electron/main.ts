import path from "node:path";
import { spawn } from "node:child_process";
import fs from "node:fs";
import { randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";

import chokidar, { type FSWatcher } from "chokidar";
import dotenv from "dotenv";
import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";

import { parseTemplate } from "./templateParser";

dotenv.config({ path: path.join(process.cwd(), ".env") });

let mainWindow: BrowserWindow | null = null;
let petWindow: BrowserWindow | null = null;
let petChatWindow: BrowserWindow | null = null;
let watcher: FSWatcher | null = null;
let currentFilePath: string | null = null;
const activeChatProcesses = new Map<string, ReturnType<typeof spawn>>();
let isQuitting = false;
let petWorkspaceDir: string | null = null;
let petDragState: { startMouseX: number; startMouseY: number; startWindowX: number; startWindowY: number } | null = null;

const isDev = !app.isPackaged;

function resolveLottiePlayerCode(): string {
  const candidates = new Set<string>();

  try {
    candidates.add(require.resolve("lottie-web/build/player/lottie.min.js"));
  } catch {
    // ignore resolve failure and fallback to known paths
  }

  candidates.add(
    path.join(app.getAppPath(), "node_modules", "lottie-web", "build", "player", "lottie.min.js")
  );
  candidates.add(
    path.join(process.resourcesPath, "app.asar.unpacked", "node_modules", "lottie-web", "build", "player", "lottie.min.js")
  );

  for (const candidate of candidates) {
    try {
      if (!candidate || !fs.existsSync(candidate)) {
        continue;
      }
      return fs.readFileSync(candidate, "utf-8").replace(/<\/script/gi, "<\\/script");
    } catch {
      // try next candidate
    }
  }

  return "";
}

function normalizeLottieAssets(data: unknown, sourceFile: string): unknown {
  if (!data || typeof data !== "object") {
    return data;
  }

  const sourceDir = path.dirname(sourceFile);
  const parsed = data as { assets?: Array<Record<string, unknown>> };
  if (!Array.isArray(parsed.assets)) {
    return data;
  }

  parsed.assets = parsed.assets.map((asset) => {
    if (!asset || typeof asset !== "object") {
      return asset;
    }

    if (asset.e) {
      return asset;
    }

    const rawP = typeof asset.p === "string" ? asset.p.trim() : "";
    if (!rawP) {
      return asset;
    }

    if (/^(?:https?:|data:|blob:|file:)/i.test(rawP) || rawP.startsWith("//")) {
      return asset;
    }

    const rawU = typeof asset.u === "string" ? asset.u : "";
    const absolute = path.resolve(sourceDir, rawU, rawP);
    const absoluteFileUrl = pathToFileURL(absolute).toString();

    return {
      ...asset,
      u: "",
      p: absoluteFileUrl,
    };
  });

  return parsed;
}

function resolvePetLottieDataLiteral(): string {
  const lottieDir = path.join(app.getAppPath(), "assets", "lottie");
  const preferredRaw = String(process.env.PET_LOTTIE_FILE ?? "").trim();
  const preferredFile = preferredRaw
    ? path.isAbsolute(preferredRaw)
      ? preferredRaw
      : path.join(lottieDir, preferredRaw)
    : "";

  const candidates = new Set<string>();
  if (preferredFile) {
    candidates.add(preferredFile);
  }
  candidates.add(path.join(lottieDir, "pet-animation.json"));
  candidates.add(path.join(lottieDir, "pet.json"));
  candidates.add(path.join(lottieDir, "loader-cat.json"));

  if (fs.existsSync(lottieDir)) {
    try {
      const jsonFiles = fs
        .readdirSync(lottieDir, { withFileTypes: true })
        .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".json"))
        .map((entry) => path.join(lottieDir, entry.name))
        .sort((a, b) => a.localeCompare(b));
      for (const file of jsonFiles) {
        candidates.add(file);
      }
    } catch {
      // ignore directory read errors and fallback to emoji
    }
  }

  for (const candidate of candidates) {
    if (!candidate || !fs.existsSync(candidate)) {
      continue;
    }
    try {
      const raw = fs.readFileSync(candidate, "utf-8");
      const parsed = JSON.parse(raw);
      const normalized = normalizeLottieAssets(parsed, candidate);
      return JSON.stringify(normalized);
    } catch {
      // try next candidate
    }
  }

  return "null";
}

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
    show: false,
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

  mainWindow.on("close", (event) => {
    if (isQuitting) {
      return;
    }
    event.preventDefault();
    mainWindow?.hide();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function loadPetWindowContent(): void {
  if (!petWindow || petWindow.isDestroyed()) {
    return;
  }

  const petWindowHtmlPath = isDev 
    ? path.join(app.getAppPath(), "electron", "pet-window.html")
    : path.join(__dirname, "pet-window.html");
  
  petWindow.loadFile(petWindowHtmlPath);
}

function loadPetChatWindowContent(): void {
  if (!petChatWindow || petChatWindow.isDestroyed()) {
    return;
  }

  const html = `
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <style>
      :root {
        --bg: #0f172a;
        --surface: #111827;
        --surface-2: #1f2937;
        --text: #e5e7eb;
        --muted: #94a3b8;
        --accent: #818cf8;
      }
      * { box-sizing: border-box; }
      html, body {
        margin: 0;
        width: 100%;
        height: 100%;
        background: transparent;
        color: var(--text);
        font-family: "Segoe UI", "PingFang SC", sans-serif;
      }
      .root {
        height: 100%;
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 12px;
        background: linear-gradient(180deg, rgba(17,24,39,0.95), rgba(15,23,42,0.95));
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .header {
        padding: 10px 14px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.2);
        font-size: 13px;
        font-weight: 600;
        -webkit-app-region: drag;
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(255, 255, 255, 0.03);
      }
      .header-info {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 0;
        gap: 2px;
      }
      .close-btn {
        -webkit-app-region: no-drag;
        background: transparent;
        border: none;
        color: var(--muted);
        font-size: 20px;
        line-height: 1;
        cursor: pointer;
        padding: 4px 8px;
        margin-left: 8px;
        border-radius: 6px;
        transition: all 0.2s ease;
      }
      .close-btn:hover {
        background: rgba(239, 68, 68, 0.8);
        color: white;
      }
      .dir {
        color: var(--muted);
        font-size: 11px;
        font-weight: normal;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .chat {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
        padding: 14px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .chat::-webkit-scrollbar {
        width: 6px;
      }
      .chat::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.3);
        border-radius: 3px;
      }
      .msg {
        font-size: 13px;
        line-height: 1.5;
        border-radius: 12px;
        padding: 10px 14px;
        white-space: pre-wrap;
        word-wrap: break-word;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      }
      .msg.user { 
        background: rgba(99,102,241,0.25);
        border: 1px solid rgba(99,102,241,0.4);
        align-self: flex-end;
        max-width: 85%;
        border-bottom-right-radius: 4px;
      }
      .msg.agent { 
        background: rgba(30,41,59,0.8);
        border: 1px solid rgba(148,163,184,0.15);
        align-self: flex-start;
        max-width: 85%;
        border-bottom-left-radius: 4px;
      }
      .input {
        border-top: 1px solid rgba(148, 163, 184, 0.2);
        padding: 12px;
        display: grid;
        gap: 10px;
        background: rgba(15,23,42,0.9);
      }
      textarea {
        width: 100%;
        min-height: 64px;
        max-height: 120px;
        resize: vertical;
        border-radius: 10px;
        border: 1px solid rgba(148,163,184,0.3);
        background: rgba(30,41,59,0.5);
        color: var(--text);
        padding: 10px 12px;
        font-size: 13px;
        font-family: inherit;
        outline: none;
        transition: border-color 0.2s, background 0.2s;
      }
      textarea:focus {
        border-color: var(--accent);
        background: rgba(30,41,59,0.8);
      }
      textarea::-webkit-scrollbar {
        width: 6px;
      }
      textarea::-webkit-scrollbar-thumb {
        background: rgba(148, 163, 184, 0.3);
        border-radius: 3px;
      }
      .row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 8px;
        margin-top: 4px;
      }
      button {
        border: 1px solid rgba(148,163,184,0.25);
        background: rgba(30,41,59,0.7);
        color: var(--text);
        border-radius: 8px;
        font-size: 12px;
        font-weight: 500;
        padding: 8px 12px;
        cursor: pointer;
        transition: all 0.2s;
      }
      button:hover {
        background: rgba(51,65,85,0.9);
        border-color: rgba(148,163,184,0.4);
      }
      button.primary {
        border-color: rgba(99,102,241,0.5);
        background: rgba(99,102,241,0.2);
        color: #c7d2fe;
      }
      button.primary:hover {
        background: rgba(99,102,241,0.35);
        border-color: rgba(99,102,241,0.7);
        box-shadow: 0 0 10px rgba(99,102,241,0.2);
      }
    </style>
  </head>
  <body>
    <div class="root">
      <div class="header">
        <div class="header-info">
          <div><span style="margin-right: 6px;">🤖</span>桌宠对话框</div>
          <div class="dir" id="dir">目录：未绑定</div>
        </div>
        <button class="close-btn" id="closeBtn">&times;</button>
      </div>
      <div class="chat" id="chat"></div>
      <div class="input">
        <textarea id="text" placeholder="例如：把 src/main.ts 中标题改为 智能报销助手"></textarea>
        <div class="row">
          <button id="bind">选择目录</button>
          <button id="openPanel">打开功能面板</button>
          <button class="primary" id="send">发送</button>
        </div>
      </div>
    </div>
    <script>
      const state = { history: [] };
      const chatEl = document.getElementById('chat');
      const dirEl = document.getElementById('dir');
      const textEl = document.getElementById('text');

      function append(role, content) {
        const node = document.createElement('div');
        node.className = 'msg ' + role;
        node.textContent = content;
        chatEl.appendChild(node);
        chatEl.scrollTop = chatEl.scrollHeight;
        state.history.push({ role, content });
      }

      async function refreshDir() {
        if (!window.petChatApi) return;
        const dir = await window.petChatApi.getWorkspaceDir();
        dirEl.textContent = '目录：' + (dir || '未绑定');
      }

      async function sendMessage() {
        const text = (textEl.value || '').trim();
        if (!text || !window.petChatApi) return;
        append('user', text);
        textEl.value = '';
        const resp = await window.petChatApi.chat(text, state.history);
        if (!resp || !resp.ok) {
          append('agent', '失败：' + ((resp && resp.error) || '未知错误'));
          return;
        }
        append('agent', resp.reply || '已处理');
      }

      document.getElementById('send').addEventListener('click', () => { void sendMessage(); });
      textEl.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          event.preventDefault();
          void sendMessage();
        }
      });

      document.getElementById('openPanel').addEventListener('click', async () => {
        if (window.petChatApi && typeof window.petChatApi.openMainWindow === 'function') {
          await window.petChatApi.openMainWindow();
        }
      });

      document.getElementById('closeBtn').addEventListener('click', async () => {
        if (window.petChatApi && typeof window.petChatApi.closePetChat === 'function') {
          await window.petChatApi.closePetChat();
        }
      });

      document.getElementById('bind').addEventListener('click', async () => {
        if (!window.petChatApi || typeof window.petChatApi.pickWorkspaceDir !== 'function') return;
        await window.petChatApi.pickWorkspaceDir();
      });

      if (window.petChatApi && typeof window.petChatApi.subscribeWorkspaceUpdate === 'function') {
        window.petChatApi.subscribeWorkspaceUpdate(() => { void refreshDir(); });
      }

      void refreshDir();
      append('agent', '可让我在绑定目录内读取/修改文件。建议描述：文件路径 + 修改目标。');
    </script>
  </body>
</html>`;

  petChatWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
}

function createPetChatWindow(): void {
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    if (!petChatWindow.isVisible()) {
      petChatWindow.show();
    }
    petChatWindow.focus();
    return;
  }

  petChatWindow = new BrowserWindow({
    width: 420,
    height: 520,
    show: true,
    frame: false,
    resizable: true,
    minimizable: false,
    maximizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    transparent: true,
    webPreferences: {
      preload: path.join(__dirname, "petChatPreload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  loadPetChatWindowContent();

  petChatWindow.on("closed", () => {
    petChatWindow = null;
  });
}

function emitWorkspaceUpdated(): void {
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("pet:workspace-updated", petWorkspaceDir);
  }
}

function normalizeWorkspaceDir(candidatePath: string): string | null {
  if (!candidatePath) {
    return null;
  }
  try {
    const normalized = path.resolve(candidatePath);
    const stat = fs.statSync(normalized);
    if (stat.isDirectory()) {
      return normalized;
    }
    if (stat.isFile()) {
      return path.dirname(normalized);
    }
    return null;
  } catch {
    return null;
  }
}

function showOrCreateMainWindow(): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createMainWindow();
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  if (!mainWindow.isVisible()) {
    mainWindow.show();
  }
  mainWindow.focus();
}

function createPetWindow(): void {
  if (petWindow && !petWindow.isDestroyed()) {
    return;
  }

  petWindow = new BrowserWindow({
    width: 96,
    height: 96,
    x: 40,
    y: 80,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: "#00000001",
    focusable: true,
    resizable: false,
    minimizable: false,
    maximizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "petPreload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  const displayArea = screen.getPrimaryDisplay().workArea;
  const safeX = Math.max(displayArea.x, Math.min(displayArea.x + displayArea.width - 96, 40));
  const safeY = Math.max(displayArea.y, Math.min(displayArea.y + displayArea.height - 96, 80));
  petWindow.setPosition(safeX, safeY);

  petWindow.setAlwaysOnTop(true, "screen-saver");
  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  petWindow.once("ready-to-show", () => {
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.show();
    }
  });
  loadPetWindowContent();

  petWindow.on("closed", () => {
    petWindow = null;
  });
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

ipcMain.handle("template:openPath", async (_event, targetPath: string) => {
  if (!targetPath || !fs.existsSync(targetPath)) {
    return { ok: false, message: "文件不存在" };
  }
  const openErr = await shell.openPath(targetPath);
  if (openErr) {
    return { ok: false, message: openErr };
  }
  return { ok: true };
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

ipcMain.handle(
  "agent:task",
  async (_event, request: { taskType: string; taskPayload?: unknown }) => {
    return invokePythonChat({
      message: "执行任务",
      payload: {
        task_type: request.taskType,
        task_payload: request.taskPayload,
      },
    });
  }
);

ipcMain.handle("agent:chat:start", async (_event, request: { message: string; payload?: unknown }) => {
  const chatId = randomUUID();
  invokePythonChatStream(chatId, request);
  return { chatId };
});

ipcMain.handle(
  "agent:task:start",
  async (_event, request: { taskType: string; taskPayload?: unknown }) => {
    const chatId = randomUUID();
    invokePythonChatStream(chatId, {
      message: "执行任务",
      payload: {
        task_type: request.taskType,
        task_payload: request.taskPayload,
      },
    });
    return { chatId };
  }
);

ipcMain.handle("agent:chat:stop", async (_event, chatId: string) => {
  const process = activeChatProcesses.get(chatId);
  if (!process) {
    return;
  }
  process.kill();
  activeChatProcesses.delete(chatId);
});

ipcMain.handle("pet:openMain", async () => {
  showOrCreateMainWindow();
});

ipcMain.handle("pet:closeChat", async () => {
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.hide();
  }
});

ipcMain.handle("pet:openChat", async () => {
  createPetChatWindow();
});

ipcMain.handle("pet:getWorkspaceDir", async () => petWorkspaceDir);

ipcMain.handle("pet:setWorkspaceDir", async (_event, droppedPath: string) => {
  const dir = normalizeWorkspaceDir(droppedPath);
  if (!dir) {
    return { ok: false, message: "未识别到有效目录" };
  }
  petWorkspaceDir = dir;
  emitWorkspaceUpdated();
  return { ok: true, dir };
});

ipcMain.handle("pet:pickWorkspaceDir", async () => {
  const result = await dialog.showOpenDialog({
    title: "选择目录",
    properties: ["openDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "已取消" };
  }
  const dir = normalizeWorkspaceDir(result.filePaths[0]);
  if (!dir) {
    return { ok: false, message: "目录无效" };
  }
  petWorkspaceDir = dir;
  emitWorkspaceUpdated();
  return { ok: true, dir };
});

ipcMain.handle("pet:move:begin", async (_event, payload: { screenX: number; screenY: number }) => {
  if (!petWindow || petWindow.isDestroyed()) {
    return;
  }
  const [winX, winY] = petWindow.getPosition();
  petDragState = {
    startMouseX: Number(payload?.screenX ?? 0),
    startMouseY: Number(payload?.screenY ?? 0),
    startWindowX: winX,
    startWindowY: winY,
  };
});

ipcMain.handle("pet:move:update", async (_event, payload: { screenX: number; screenY: number }) => {
  if (!petWindow || petWindow.isDestroyed() || !petDragState) {
    return;
  }
  const currentMouseX = Number(payload?.screenX ?? petDragState.startMouseX);
  const currentMouseY = Number(payload?.screenY ?? petDragState.startMouseY);
  const nextX = Math.round(petDragState.startWindowX + (currentMouseX - petDragState.startMouseX));
  const nextY = Math.round(petDragState.startWindowY + (currentMouseY - petDragState.startMouseY));
  petWindow.setPosition(nextX, nextY);
});

ipcMain.on("pet:move:update", (_event, payload: { screenX: number; screenY: number }) => {
  if (!petWindow || petWindow.isDestroyed() || !petDragState) {
    return;
  }
  const currentMouseX = Number(payload?.screenX ?? petDragState.startMouseX);
  const currentMouseY = Number(payload?.screenY ?? petDragState.startMouseY);
  const nextX = Math.round(petDragState.startWindowX + (currentMouseX - petDragState.startMouseX));
  const nextY = Math.round(petDragState.startWindowY + (currentMouseY - petDragState.startMouseY));
  petWindow.setPosition(nextX, nextY);
});

ipcMain.handle("pet:move:end", async () => {
  petDragState = null;
});

ipcMain.handle("pet:chat", async (_event, req: { message: string; history?: Array<{ role: string; content: string }> }) => {
  const message = String(req?.message ?? "").trim();
  const history = Array.isArray(req?.history) ? req.history : [];
  if (!message) {
    return { ok: false, error: "消息不能为空" };
  }
  if (!petWorkspaceDir) {
    return { ok: false, error: "请先拖拽文件夹到桌宠，或在对话框中选择目录" };
  }

  const response = (await invokePythonChat({
    message,
    payload: {
      history,
      workspace_dir: petWorkspaceDir,
      workspace_mode: true,
    },
  })) as { ok?: boolean; reply?: string; error?: string };

  return {
    ok: Boolean(response?.ok),
    reply: response?.reply,
    error: response?.error,
  };
});

app.whenReady().then(() => {
  createMainWindow();
  createPetWindow();

  app.on("activate", () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      createMainWindow();
    }
    createPetWindow();
  });
});

app.on("window-all-closed", () => {
  if (petWindow && !petWindow.isDestroyed()) {
    return;
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  isQuitting = true;
  if (watcher) {
    await watcher.close();
  }
  for (const child of activeChatProcesses.values()) {
    child.kill();
  }
  activeChatProcesses.clear();
});
