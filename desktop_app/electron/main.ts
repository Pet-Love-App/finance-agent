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
let sharedChatHistory: Array<{ role: string; content: string; status?: string }> = [];
let watcher: FSWatcher | null = null;
let currentFilePath: string | null = null;
const activeChatProcesses = new Map<string, ReturnType<typeof spawn>>();
let isQuitting = false;
let petWorkspaceDir: string | null = null;
let petDragState: { startMouseX: number; startMouseY: number; startWindowX: number; startWindowY: number } | null = null;

const isDev = !app.isPackaged;
const rendererDevServer = "http://localhost:5173";

function normalizeRendererRoute(route: string): string {
  const trimmed = route.trim();
  if (!trimmed) {
    return "/";
  }
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

function loadRendererRoute(target: BrowserWindow, route: string): void {
  const normalized = normalizeRendererRoute(route);

  if (isDev) {
    target.loadURL(`${rendererDevServer}/#${normalized}`);
    return;
  }

  target.loadFile(path.join(__dirname, "../dist/index.html"), { hash: normalized });
}

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

function emitPetChatStreamEvent(chatId: string, event: StreamEvent): void {
  if (!petChatWindow || petChatWindow.isDestroyed()) {
    return;
  }
  petChatWindow.webContents.send("pet:chat:event", { chatId, ...event });
}

function invokePythonChatStream(
  chatId: string,
  request: { message: string; payload?: unknown },
  emitEvent: (chatId: string, event: StreamEvent) => void = emitChatStreamEvent
): void {
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
        emitEvent(chatId, { type: "delta", delta: String(parsed.delta ?? "") });
        return;
      }
      if (parsed.type === "status") {
        emitEvent(chatId, { type: "status", status: String((parsed as any).status ?? "") });
        return;
      }
      if (parsed.type === "done") {
        finalized = true;
        emitEvent(chatId, { type: "done", response: parsed.response });
        return;
      }
      if (parsed.type === "error") {
        finalized = true;
        emitEvent(chatId, { type: "error", error: String(parsed.error ?? "未知错误") });
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
    emitEvent(chatId, { type: "error", error: err.message });
    cleanup();
  });

  child.on("close", (code) => {
    if (stdoutBuffer.trim()) {
      handleStreamLine(stdoutBuffer.trim());
    }
    if (!finalized) {
      if (code === 0) {
        emitEvent(chatId, {
          type: "error",
          error: "流式响应提前结束，未收到完成事件。",
        });
      } else {
        emitEvent(chatId, {
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

  loadRendererRoute(mainWindow, "/");

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
  loadRendererRoute(petWindow, "/pet");
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
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "petChatPreload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  loadRendererRoute(petChatWindow, "/pet-chat");

  petChatWindow.on("closed", () => {
    petChatWindow = null;
  });
}

function emitWorkspaceUpdated(): void {
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("pet:workspace-updated", petWorkspaceDir);
  }
}

function emitChatHistoryUpdate(): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("chat:history:update", sharedChatHistory);
  }
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("chat:history:update", sharedChatHistory);
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

ipcMain.handle("template:pickDir", async () => {
  const result = await dialog.showOpenDialog({
    title: "选择目录",
    properties: ["openDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "已取消" };
  }
  return { ok: true, dir: result.filePaths[0] };
});

ipcMain.handle("template:listDir", async (_event, targetDir: string) => {
  const dirPath = String(targetDir ?? "");
  if (!dirPath) {
    return { ok: false, error: "目录不能为空" };
  }
  try {
    const stat = fs.statSync(dirPath);
    if (!stat.isDirectory()) {
      return { ok: false, error: "目标不是目录" };
    }

    const entries = fs
      .readdirSync(dirPath, { withFileTypes: true })
      .map((entry) => ({
        name: entry.name,
        path: path.join(dirPath, entry.name),
        isDir: entry.isDirectory(),
      }))
      .sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-Hans-CN");
      });

    return { ok: true, entries };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
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

ipcMain.handle("template:readFile", async (_event, targetPath: string) => {
  const filePath = String(targetPath ?? "");
  if (!filePath || !fs.existsSync(filePath)) {
    return { ok: false, error: "文件不存在" };
  }
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) {
      return { ok: false, error: "目标不是文件" };
    }

    const ext = path.extname(filePath).toLowerCase();
    const fileType = ext ? ext.slice(1) : "unknown";
    const updatedAt = stat.mtime.toISOString();
    const size = stat.size;
    const maxBytes = 10 * 1024 * 1024;
    const buffer = fs.readFileSync(filePath);
    const truncated = buffer.length > maxBytes;
    const slice = truncated ? buffer.subarray(0, maxBytes) : buffer;

    const imageTypes: Record<string, string> = {
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".gif": "image/gif",
      ".webp": "image/webp",
      ".bmp": "image/bmp",
      ".svg": "image/svg+xml",
    };

    if (imageTypes[ext]) {
      if (ext === ".svg") {
        const text = slice.toString("utf-8");
        const dataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
        return { ok: true, kind: "image", filePath, fileType, updatedAt, dataUrl, truncated };
      }
      const base64 = slice.toString("base64");
      const dataUrl = `data:${imageTypes[ext]};base64,${base64}`;
      return { ok: true, kind: "image", filePath, fileType, updatedAt, dataUrl, truncated };
    }

    const hasNull = slice.includes(0);
    if (!hasNull) {
      const content = slice.toString("utf-8");
      return { ok: true, kind: "text", filePath, fileType, updatedAt, content, truncated };
    }

    const hexBytes = slice.subarray(0, Math.min(slice.length, 512));
    const lines: string[] = [];
    for (let i = 0; i < hexBytes.length; i += 16) {
      const chunk = Array.from(hexBytes.subarray(i, i + 16))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join(" ");
      lines.push(chunk);
    }
    return {
      ok: true,
      kind: "binary",
      filePath,
      fileType,
      updatedAt,
      size,
      hex: lines.join("\n"),
      truncated,
    };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
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

ipcMain.handle("chat:history:get", async () => sharedChatHistory);

ipcMain.handle(
  "chat:history:set",
  async (_event, history: Array<{ role: string; content: string; status?: string }>) => {
    if (Array.isArray(history)) {
      sharedChatHistory = history.map((item) => ({
        role: String(item.role ?? ""),
        content: String(item.content ?? ""),
        status: typeof item.status === "string" ? item.status : undefined,
      }));
      emitChatHistoryUpdate();
    }
    return { ok: true };
  }
);

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

ipcMain.handle(
  "pet:chat:start",
  async (_event, req: { message: string; history?: Array<{ role: string; content: string }> }) => {
    const message = String(req?.message ?? "").trim();
    const history = Array.isArray(req?.history) ? req.history : [];
    if (!message) {
      return { ok: false, error: "消息不能为空" };
    }
    if (!petWorkspaceDir) {
      return { ok: false, error: "请先拖拽文件夹到桌宠，或在对话框中选择目录" };
    }
    const chatId = randomUUID();
    invokePythonChatStream(
      chatId,
      {
        message,
        payload: {
          history,
          workspace_dir: petWorkspaceDir,
          workspace_mode: true,
        },
      },
      emitPetChatStreamEvent
    );
    return { ok: true, chatId };
  }
);

ipcMain.handle("pet:chat:stop", async (_event, chatId: string) => {
  const process = activeChatProcesses.get(chatId);
  if (!process) {
    return;
  }
  process.kill();
  activeChatProcesses.delete(chatId);
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
