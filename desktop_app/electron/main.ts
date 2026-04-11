import path from "node:path";
import { spawn } from "node:child_process";
import fs from "node:fs";
import { randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";

import chokidar, { type FSWatcher } from "chokidar";
import dotenv from "dotenv";
import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";
import type { OpenDialogOptions } from "electron";
import * as XLSX from "xlsx";

import type { EditTraceQuery } from "./editTrace";
import { EditTraceStore } from "./editTrace";
import { parseTemplate } from "./templateParser";

dotenv.config({ path: path.join(process.cwd(), ".env") });

let mainWindow: BrowserWindow | null = null;
let petWindow: BrowserWindow | null = null;
let petChatWindow: BrowserWindow | null = null;
let compareWindow: BrowserWindow | null = null;
type SharedChatMessage = { role: string; content: string; status?: string };
type ChatSession = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  history: SharedChatMessage[];
};

const DEFAULT_CHAT_SESSION_TITLE = "新会话";
let legacySharedChatHistory: SharedChatMessage[] = [];
let sharedChatSessions: ChatSession[] = [];
let activeChatSessionId: string | null = null;
let chatHistoryVersion = 0;
let watcher: FSWatcher | null = null;
let currentFilePath: string | null = null;
const activeChatProcesses = new Map<string, ReturnType<typeof spawn>>();
const editTraceStore = new EditTraceStore();
let isQuitting = false;
let petWorkspaceDir: string | null = null;
let compareBoundDir: string | null = null;
let petDragState: { startMouseX: number; startMouseY: number; startWindowX: number; startWindowY: number } | null = null;

const isDev = !app.isPackaged;
const rendererDevServer = "http://localhost:5173";
const LLM_CONFIG_FILE_NAME = "llm_config.json";

type LlmProvider = "openai" | "glm" | "deepseek" | "qwen" | "anthropic" | "custom";
type LlmConfig = {
  provider: LlmProvider;
  apiKey: string;
  baseUrl: string;
  model: string;
};

const LLM_PROVIDER_PRESETS: Record<Exclude<LlmProvider, "custom">, { baseUrl: string; model: string }> = {
  openai: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
  glm: {
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash",
  },
  deepseek: {
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  qwen: {
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  anthropic: {
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-3-5-sonnet-latest",
  },
};

function inferProviderFromBaseUrl(baseUrl: string): LlmProvider {
  const lowered = baseUrl.toLowerCase();
  if (lowered.includes("bigmodel.cn") || lowered.includes("zhipu")) return "glm";
  if (lowered.includes("deepseek")) return "deepseek";
  if (lowered.includes("dashscope") || lowered.includes("aliyuncs")) return "qwen";
  if (lowered.includes("anthropic")) return "anthropic";
  if (lowered.includes("openai")) return "openai";
  return "custom";
}

function normalizeLlmBaseUrl(rawBaseUrl: string): string {
  const trimmed = String(rawBaseUrl ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed);
    const pathname = parsed.pathname.replace(/\/+$/, "");
    if (!pathname) {
      parsed.pathname = "/v1";
      return parsed.toString().replace(/\/+$/, "");
    }
    return `${parsed.origin}${pathname}`;
  } catch {
    return trimmed;
  }
}

function buildDefaultLlmConfig(): LlmConfig {
  const envBaseUrl = String(process.env.AGENT_LLM_BASE_URL ?? process.env.AGENT_LLM_API_URL ?? "").trim();
  const normalizedEnvBaseUrl = normalizeLlmBaseUrl(envBaseUrl);
  const provider = normalizedEnvBaseUrl ? inferProviderFromBaseUrl(normalizedEnvBaseUrl) : "openai";
  const preset = provider === "custom" ? undefined : LLM_PROVIDER_PRESETS[provider];
  return {
    provider,
    apiKey: String(process.env.AGENT_LLM_API_KEY ?? "").trim(),
    baseUrl: normalizedEnvBaseUrl || preset?.baseUrl || LLM_PROVIDER_PRESETS.openai.baseUrl,
    model: String(process.env.AGENT_LLM_MODEL ?? "").trim() || preset?.model || LLM_PROVIDER_PRESETS.openai.model,
  };
}

function sanitizeLlmConfig(input: Partial<LlmConfig> | null | undefined): LlmConfig {
  const fallback = buildDefaultLlmConfig();
  const providerValue = String(input?.provider ?? fallback.provider).trim().toLowerCase();
  const provider: LlmProvider =
    providerValue === "openai" ||
    providerValue === "glm" ||
    providerValue === "deepseek" ||
    providerValue === "qwen" ||
    providerValue === "anthropic" ||
    providerValue === "custom"
      ? providerValue
      : fallback.provider;

  const preset = provider === "custom" ? undefined : LLM_PROVIDER_PRESETS[provider];
  const normalizedBase = normalizeLlmBaseUrl(String(input?.baseUrl ?? "").trim());
  const baseUrl = normalizedBase || preset?.baseUrl || fallback.baseUrl;
  const model = String(input?.model ?? "").trim() || preset?.model || fallback.model;
  const apiKey = String(input?.apiKey ?? "").trim();

  return { provider, apiKey, baseUrl, model };
}

function llmConfigFilePath(): string {
  return path.join(app.getPath("userData"), LLM_CONFIG_FILE_NAME);
}

function loadLlmConfigFromDisk(): LlmConfig {
  const fallback = buildDefaultLlmConfig();
  try {
    const filePath = llmConfigFilePath();
    if (!fs.existsSync(filePath)) {
      return fallback;
    }
    const raw = fs.readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw) as Partial<LlmConfig>;
    return sanitizeLlmConfig(parsed);
  } catch {
    return fallback;
  }
}

function saveLlmConfigToDisk(config: LlmConfig): void {
  const filePath = llmConfigFilePath();
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(config, null, 2), "utf-8");
}

function buildChatEnv(baseEnv: NodeJS.ProcessEnv, config: LlmConfig): NodeJS.ProcessEnv {
  const nextEnv: NodeJS.ProcessEnv = {
    ...baseEnv,
    AGENT_LLM_BASE_URL: config.baseUrl,
    AGENT_LLM_MODEL: config.model,
  };

  if (config.apiKey) {
    nextEnv.AGENT_LLM_API_KEY = config.apiKey;
  } else {
    delete nextEnv.AGENT_LLM_API_KEY;
  }

  return nextEnv;
}

let currentLlmConfig: LlmConfig = buildDefaultLlmConfig();

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

  const indexFileUrl = pathToFileURL(path.join(__dirname, "../dist/index.html")).toString();
  target.loadURL(`${indexFileUrl}#${normalized}`);
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
      env: buildChatEnv(
        {
        ...process.env,
        PYTHONUTF8: "1",
        PYTHONIOENCODING: "utf-8",
        },
        currentLlmConfig
      ),
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
    env: buildChatEnv(
      {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
      },
      currentLlmConfig
    ),
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
    titleBarStyle: "hidden",
    titleBarOverlay: false,
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
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("pet:workspace-updated", petWorkspaceDir);
  }
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("pet:workspace-updated", petWorkspaceDir);
  }
}

function setBoundWorkspaceDir(dir: string): string {
  const normalized = path.resolve(dir);
  petWorkspaceDir = normalized;
  emitWorkspaceUpdated();
  return normalized;
}

function emitChatHistoryUpdate(): void {
  const activeSession = getActiveChatSession();
  const history = activeSession?.history ?? [];
  const payload = {
    history,
    version: chatHistoryVersion,
  };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("chat:history:update", payload);
  }
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("chat:history:update", payload);
  }
}

function bumpChatHistoryVersion(): number {
  chatHistoryVersion += 1;
  return chatHistoryVersion;
}

type ChatSessionMeta = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};

function sanitizeChatHistory(history: Array<{ role: string; content: string; status?: string }>): SharedChatMessage[] {
  return history.map((item) => ({
    role: String(item.role ?? ""),
    content: String(item.content ?? ""),
    status: typeof item.status === "string" ? item.status : undefined,
  }));
}

function emitLlmConfigUpdated(): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("llm:config:updated", currentLlmConfig);
  }
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("llm:config:updated", currentLlmConfig);
  }
}

function deriveSessionTitleFromHistory(history: SharedChatMessage[]): string {
  const userMessage = history.find((item) => item.role === "user" && item.content.trim());
  if (!userMessage) {
    return DEFAULT_CHAT_SESSION_TITLE;
  }
  const firstLine = userMessage.content.trim().replace(/\s+/g, " ");
  return firstLine.slice(0, 24) || DEFAULT_CHAT_SESSION_TITLE;
}

function toChatSessionMeta(session: ChatSession): ChatSessionMeta {
  return {
    id: session.id,
    title: session.title,
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
    messageCount: session.history.length,
  };
}

function getChatSessionById(sessionId: string): ChatSession | undefined {
  return sharedChatSessions.find((session) => session.id === sessionId);
}

function getActiveChatSession(): ChatSession | undefined {
  if (!activeChatSessionId) {
    return undefined;
  }
  return getChatSessionById(activeChatSessionId);
}

function createChatSession(initialHistory: SharedChatMessage[] = []): ChatSession {
  const now = new Date().toISOString();
  const session: ChatSession = {
    id: randomUUID(),
    title: deriveSessionTitleFromHistory(initialHistory),
    createdAt: now,
    updatedAt: now,
    history: initialHistory,
  };
  sharedChatSessions = [session, ...sharedChatSessions];
  activeChatSessionId = session.id;
  return session;
}

function ensureChatSessionsInitialized(): void {
  if (sharedChatSessions.length > 0 && activeChatSessionId) {
    return;
  }
  const initialHistory = legacySharedChatHistory.length > 0 ? legacySharedChatHistory : [];
  createChatSession(initialHistory);
  legacySharedChatHistory = [];
}

function emitChatSessionsUpdate(): void {
  ensureChatSessionsInitialized();
  const payload = {
    activeSessionId: activeChatSessionId,
    sessions: sharedChatSessions.map(toChatSessionMeta),
  };
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("chat:sessions:update", payload);
  }
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.webContents.send("chat:sessions:update", payload);
  }
}

function getDialogParentWindow(...candidates: Array<BrowserWindow | null>): BrowserWindow | undefined {
  for (const candidate of candidates) {
    if (candidate && !candidate.isDestroyed()) {
      return candidate;
    }
  }
  return undefined;
}

function getSenderWindow(event: Electron.IpcMainInvokeEvent): BrowserWindow | null {
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (senderWindow && !senderWindow.isDestroyed()) {
    return senderWindow;
  }
  return mainWindow && !mainWindow.isDestroyed() ? mainWindow : null;
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

function listWorkspaceFiles(rootDir: string): Array<{ name: string; path: string; relativePath: string }> {
  const files: Array<{ name: string; path: string; relativePath: string }> = [];
  const stack: Array<{ dir: string; depth: number }> = [{ dir: rootDir, depth: 0 }];
  const maxDepth = 12;
  const maxCount = 10000;
  const skipDirs = new Set([
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
  ]);

  while (stack.length > 0 && files.length < maxCount) {
    const current = stack.pop();
    if (!current) {
      break;
    }
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(current.dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      if (entry.name.startsWith(".")) {
        continue;
      }
      const fullPath = path.join(current.dir, entry.name);
      if (entry.isDirectory()) {
        if (current.depth < maxDepth && !skipDirs.has(entry.name)) {
          stack.push({ dir: fullPath, depth: current.depth + 1 });
        }
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      try {
        const relativePath = path.relative(rootDir, fullPath).replace(/\\/g, "/");
        files.push({ name: entry.name, path: fullPath, relativePath });
      } catch {
        // ignore file path normalization failures
      }
    }
  }

  files.sort((a, b) => a.relativePath.localeCompare(b.relativePath, "zh-Hans-CN"));
  return files;
}

function normalizeExcelCellValue(raw: string): string | number | boolean {
  const text = String(raw ?? "");
  const trimmed = text.trim();
  if (trimmed === "") {
    return "";
  }
  if (/^(true|false)$/i.test(trimmed)) {
    return trimmed.toLowerCase() === "true";
  }
  if (/^[+-]?(\d+(\.\d+)?|\.\d+)$/.test(trimmed)) {
    return Number(trimmed);
  }
  return text;
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

function createCompareWindow(): void {
  if (compareWindow && !compareWindow.isDestroyed()) {
    if (compareWindow.isMinimized()) {
      compareWindow.restore();
    }
    if (!compareWindow.isVisible()) {
      compareWindow.show();
    }
    compareWindow.focus();
    return;
  }

  compareWindow = new BrowserWindow({
    width: 1480,
    height: 920,
    show: true,
    titleBarStyle: "hidden",
    titleBarOverlay: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  compareWindow.setMenu(null);
  loadRendererRoute(compareWindow, "/compare");
  compareWindow.on("closed", () => {
    compareWindow = null;
  });
}

type CompareFileEntry = {
  path: string;
  name: string;
  ext: string;
  size: number;
  updatedAt: string;
};

function compareFileExtSupported(ext: string): boolean {
  return (
    ext === ".xlsx" ||
    ext === ".xls" ||
    ext === ".docx" ||
    ext === ".doc" ||
    ext === ".pdf"
  );
}

function listComparableFilesInDir(rootDir: string): CompareFileEntry[] {
  const files: CompareFileEntry[] = [];
  const stack: Array<{ dir: string; depth: number }> = [{ dir: rootDir, depth: 0 }];
  const maxDepth = 5;
  const maxCount = 3000;

  while (stack.length > 0 && files.length < maxCount) {
    const current = stack.pop();
    if (!current) {
      break;
    }
    let entries: fs.Dirent[] = [];
    try {
      entries = fs.readdirSync(current.dir, { withFileTypes: true });
    } catch {
      continue;
    }

    for (const entry of entries) {
      const fullPath = path.join(current.dir, entry.name);
      if (entry.isDirectory()) {
        if (current.depth < maxDepth) {
          stack.push({ dir: fullPath, depth: current.depth + 1 });
        }
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }

      const ext = path.extname(entry.name).toLowerCase();
      if (!compareFileExtSupported(ext)) {
        continue;
      }
      try {
        const stat = fs.statSync(fullPath);
        files.push({
          path: fullPath,
          name: entry.name,
          ext,
          size: stat.size,
          updatedAt: stat.mtime.toISOString(),
        });
      } catch {
        // ignore one file stat failure and continue scanning
      }
    }
  }

  return files.sort((a, b) => {
    const updatedDiff = Date.parse(b.updatedAt) - Date.parse(a.updatedAt);
    if (updatedDiff !== 0) {
      return updatedDiff;
    }
    return a.name.localeCompare(b.name, "zh-Hans-CN");
  });
}

function resolveDefaultBoundDir(): string | null {
  const projectRoot = isDev ? path.join(app.getAppPath(), "..") : path.join(app.getAppPath(), "..", "..");
  try {
    const stat = fs.statSync(projectRoot);
    if (stat.isDirectory()) {
      return projectRoot;
    }
  } catch {
    // ignore
  }
  return null;
}

function ensurePetWorkspaceDir(): string | null {
  if (petWorkspaceDir) {
    try {
      if (fs.statSync(petWorkspaceDir).isDirectory()) {
        return petWorkspaceDir;
      }
    } catch {
      petWorkspaceDir = null;
    }
  }
  const fallback = resolveDefaultBoundDir();
  if (!fallback) {
    return null;
  }
  petWorkspaceDir = path.resolve(fallback);
  return petWorkspaceDir;
}

function ensureCompareBoundDir(): string | null {
  if (compareBoundDir) {
    try {
      if (fs.statSync(compareBoundDir).isDirectory()) {
        return compareBoundDir;
      }
    } catch {
      compareBoundDir = null;
    }
  }
  compareBoundDir = resolveDefaultBoundDir();
  return compareBoundDir;
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
      { name: "可预览文件", extensions: ["xlsx", "xls", "docx", "doc", "pdf"] },
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
  const bound = ensurePetWorkspaceDir();
  return bound ?? "";
});

ipcMain.handle("template:pickDir", async () => {
  const parent = getDialogParentWindow(mainWindow);
  const options: OpenDialogOptions = {
    title: "选择目录",
    properties: ["openDirectory"],
  };
  const result = parent ? await dialog.showOpenDialog(parent, options) : await dialog.showOpenDialog(options);
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "已取消" };
  }
  const dir = normalizeWorkspaceDir(result.filePaths[0]);
  if (!dir) {
    return { ok: false, message: "目录无效" };
  }
  return { ok: true, dir: setBoundWorkspaceDir(dir) };
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

ipcMain.handle("template:listWorkspaceFiles", async (_event, targetDir: string) => {
  const dirPath = String(targetDir ?? "").trim();
  if (!dirPath) {
    return { ok: false, error: "目录不能为空" };
  }
  try {
    const stat = fs.statSync(dirPath);
    if (!stat.isDirectory()) {
      return { ok: false, error: "目标不是目录" };
    }
    return { ok: true, files: listWorkspaceFiles(path.resolve(dirPath)) };
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

ipcMain.handle(
  "template:writeFile",
  async (_event, payload: { targetPath: string; content: string }) => {
    const filePath = String(payload?.targetPath ?? "");
    if (!filePath) {
      return { ok: false, error: "文件路径不能为空" };
    }
    if (!fs.existsSync(filePath)) {
      return { ok: false, error: "文件不存在" };
    }
    try {
      const content = String(payload?.content ?? "");
      await editTraceStore.recordMutation({
        operation: "write_file",
        targetPath: filePath,
        meta: {
          contentLength: content.length,
        },
        run: () => {
          const stat = fs.statSync(filePath);
          if (!stat.isFile()) {
            throw new Error("目标不是文件");
          }
          fs.writeFileSync(filePath, content, "utf-8");
        },
      });
      const updated = fs.statSync(filePath);
      return {
        ok: true,
        filePath,
        updatedAt: updated.mtime.toISOString(),
      };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
);

ipcMain.handle(
  "template:updateExcelCell",
  async (
    _event,
    payload: {
      targetPath: string;
      sheetName: string;
      rowIndex: number;
      colIndex: number;
      value: string;
    }
  ) => {
    const filePath = String(payload?.targetPath ?? "");
    if (!filePath) {
      return { ok: false, error: "文件路径不能为空" };
    }
    if (!fs.existsSync(filePath)) {
      return { ok: false, error: "文件不存在" };
    }
    const ext = path.extname(filePath).toLowerCase();
    if (ext !== ".xlsx" && ext !== ".xls") {
      return { ok: false, error: "仅支持编辑 xlsx/xls 文件" };
    }
    try {
      await editTraceStore.recordMutation({
        operation: "update_excel_cell",
        targetPath: filePath,
        meta: {
          sheetName: payload.sheetName,
          rowIndex: payload.rowIndex,
          colIndex: payload.colIndex,
        },
        run: () => {
          const workbook = XLSX.readFile(filePath, { cellDates: true });
          const fallbackSheetName = workbook.SheetNames[0];
          if (!fallbackSheetName) {
            throw new Error("工作簿无可用工作表");
          }
          const sheetName = workbook.SheetNames.includes(payload.sheetName)
            ? payload.sheetName
            : fallbackSheetName;
          const worksheet = workbook.Sheets[sheetName];
          if (!worksheet) {
            throw new Error("工作表不存在");
          }

          const rowIndex = Math.max(0, Number(payload.rowIndex) || 0);
          const colIndex = Math.max(0, Number(payload.colIndex) || 0);
          const cellAddress = XLSX.utils.encode_cell({ r: rowIndex, c: colIndex });
          const nextValue = normalizeExcelCellValue(payload.value);

          worksheet[cellAddress] = {
            t: typeof nextValue === "number" ? "n" : typeof nextValue === "boolean" ? "b" : "s",
            v: nextValue as XLSX.CellObject["v"],
          };

          const existingRef = String(worksheet["!ref"] ?? "").trim();
          if (!existingRef) {
            worksheet["!ref"] = `${cellAddress}:${cellAddress}`;
          } else {
            const range = XLSX.utils.decode_range(existingRef);
            range.s.r = Math.min(range.s.r, rowIndex);
            range.s.c = Math.min(range.s.c, colIndex);
            range.e.r = Math.max(range.e.r, rowIndex);
            range.e.c = Math.max(range.e.c, colIndex);
            worksheet["!ref"] = XLSX.utils.encode_range(range);
          }

          XLSX.writeFile(workbook, filePath);
        },
      });
      const updated = fs.statSync(filePath);
      return { ok: true, updatedAt: updated.mtime.toISOString() };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
);

ipcMain.handle(
  "template:updateExcelRange",
  async (
    _event,
    payload: {
      targetPath: string;
      sheetName: string;
      startRowIndex: number;
      startColIndex: number;
      values: string[][];
    }
  ) => {
    const filePath = String(payload?.targetPath ?? "");
    if (!filePath) {
      return { ok: false, error: "文件路径不能为空" };
    }
    if (!fs.existsSync(filePath)) {
      return { ok: false, error: "文件不存在" };
    }
    const ext = path.extname(filePath).toLowerCase();
    if (ext !== ".xlsx" && ext !== ".xls") {
      return { ok: false, error: "仅支持编辑 xlsx/xls 文件" };
    }
    try {
      const matrix = Array.isArray(payload.values)
        ? payload.values
            .map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? "")) : []))
            .filter((row) => row.length > 0)
        : [];
      if (matrix.length === 0) {
        return { ok: false, error: "粘贴内容为空" };
      }
      await editTraceStore.recordMutation({
        operation: "update_excel_range",
        targetPath: filePath,
        meta: {
          sheetName: payload.sheetName,
          startRowIndex: payload.startRowIndex,
          startColIndex: payload.startColIndex,
          rowCount: matrix.length,
          colCount: matrix[0]?.length ?? 0,
        },
        run: () => {
          const workbook = XLSX.readFile(filePath, { cellDates: true });
          const fallbackSheetName = workbook.SheetNames[0];
          if (!fallbackSheetName) {
            throw new Error("工作簿无可用工作表");
          }
          const sheetName = workbook.SheetNames.includes(payload.sheetName)
            ? payload.sheetName
            : fallbackSheetName;
          const worksheet = workbook.Sheets[sheetName];
          if (!worksheet) {
            throw new Error("工作表不存在");
          }

          const startRow = Math.max(0, Number(payload.startRowIndex) || 0);
          const startCol = Math.max(0, Number(payload.startColIndex) || 0);
          let maxRow = startRow;
          let maxCol = startCol;

          for (let rowOffset = 0; rowOffset < matrix.length; rowOffset += 1) {
            const row = matrix[rowOffset];
            for (let colOffset = 0; colOffset < row.length; colOffset += 1) {
              const rowIndex = startRow + rowOffset;
              const colIndex = startCol + colOffset;
              const cellAddress = XLSX.utils.encode_cell({ r: rowIndex, c: colIndex });
              const nextValue = normalizeExcelCellValue(row[colOffset]);
              worksheet[cellAddress] = {
                t: typeof nextValue === "number" ? "n" : typeof nextValue === "boolean" ? "b" : "s",
                v: nextValue as XLSX.CellObject["v"],
              };
              maxRow = Math.max(maxRow, rowIndex);
              maxCol = Math.max(maxCol, colIndex);
            }
          }

          const existingRef = String(worksheet["!ref"] ?? "").trim();
          if (!existingRef) {
            worksheet["!ref"] = XLSX.utils.encode_range({
              s: { r: startRow, c: startCol },
              e: { r: maxRow, c: maxCol },
            });
          } else {
            const range = XLSX.utils.decode_range(existingRef);
            range.s.r = Math.min(range.s.r, startRow);
            range.s.c = Math.min(range.s.c, startCol);
            range.e.r = Math.max(range.e.r, maxRow);
            range.e.c = Math.max(range.e.c, maxCol);
            worksheet["!ref"] = XLSX.utils.encode_range(range);
          }

          XLSX.writeFile(workbook, filePath);
        },
      });
      const updated = fs.statSync(filePath);
      return { ok: true, updatedAt: updated.mtime.toISOString() };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
);

ipcMain.handle(
  "template:appendExcelRows",
  async (
    _event,
    payload: {
      targetPath: string;
      sheetName: string;
      count: number;
    }
  ) => {
    const filePath = String(payload?.targetPath ?? "");
    if (!filePath) {
      return { ok: false, error: "文件路径不能为空" };
    }
    if (!fs.existsSync(filePath)) {
      return { ok: false, error: "文件不存在" };
    }
    const ext = path.extname(filePath).toLowerCase();
    if (ext !== ".xlsx" && ext !== ".xls") {
      return { ok: false, error: "仅支持编辑 xlsx/xls 文件" };
    }
    try {
      await editTraceStore.recordMutation({
        operation: "append_excel_rows",
        targetPath: filePath,
        meta: {
          sheetName: payload.sheetName,
          count: payload.count,
        },
        run: () => {
          const workbook = XLSX.readFile(filePath, { cellDates: true });
          const fallbackSheetName = workbook.SheetNames[0];
          if (!fallbackSheetName) {
            throw new Error("工作簿无可用工作表");
          }
          const sheetName = workbook.SheetNames.includes(payload.sheetName)
            ? payload.sheetName
            : fallbackSheetName;
          const worksheet = workbook.Sheets[sheetName];
          if (!worksheet) {
            throw new Error("工作表不存在");
          }
          const count = Math.max(1, Math.min(200, Number(payload.count) || 1));
          const existingRef = String(worksheet["!ref"] ?? "").trim();
          if (!existingRef) {
            const endRow = Math.max(0, count - 1);
            worksheet["!ref"] = XLSX.utils.encode_range({
              s: { r: 0, c: 0 },
              e: { r: endRow, c: 0 },
            });
          } else {
            const range = XLSX.utils.decode_range(existingRef);
            range.e.r += count;
            worksheet["!ref"] = XLSX.utils.encode_range(range);
          }

          XLSX.writeFile(workbook, filePath);
        },
      });
      const updated = fs.statSync(filePath);
      return { ok: true, updatedAt: updated.mtime.toISOString() };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
);

ipcMain.handle(
  "template:trimExcelSheet",
  async (
    _event,
    payload: {
      targetPath: string;
      sheetName: string;
      axis: "row" | "col";
      count: number;
    }
  ) => {
    const filePath = String(payload?.targetPath ?? "");
    if (!filePath) {
      return { ok: false, error: "文件路径不能为空" };
    }
    if (!fs.existsSync(filePath)) {
      return { ok: false, error: "文件不存在" };
    }
    const ext = path.extname(filePath).toLowerCase();
    if (ext !== ".xlsx" && ext !== ".xls") {
      return { ok: false, error: "仅支持编辑 xlsx/xls 文件" };
    }
    try {
      await editTraceStore.recordMutation({
        operation: "trim_excel_sheet",
        targetPath: filePath,
        meta: {
          sheetName: payload.sheetName,
          axis: payload.axis,
          count: payload.count,
        },
        run: () => {
          const workbook = XLSX.readFile(filePath, { cellDates: true });
          const fallbackSheetName = workbook.SheetNames[0];
          if (!fallbackSheetName) {
            throw new Error("工作簿无可用工作表");
          }
          const sheetName = workbook.SheetNames.includes(payload.sheetName)
            ? payload.sheetName
            : fallbackSheetName;
          const worksheet = workbook.Sheets[sheetName];
          if (!worksheet) {
            throw new Error("工作表不存在");
          }
          const existingRef = String(worksheet["!ref"] ?? "").trim();
          if (!existingRef) {
            throw new Error("工作表为空，无法删除");
          }
          const range = XLSX.utils.decode_range(existingRef);
          const count = Math.max(1, Math.min(200, Number(payload.count) || 1));

          if (payload.axis === "row") {
            const oldEndRow = range.e.r;
            const newEndRow = Math.max(range.s.r, oldEndRow - count);
            if (newEndRow === oldEndRow) {
              throw new Error("已无法继续删除末行");
            }
            for (let r = newEndRow + 1; r <= oldEndRow; r += 1) {
              for (let c = range.s.c; c <= range.e.c; c += 1) {
                const addr = XLSX.utils.encode_cell({ r, c });
                delete worksheet[addr];
              }
            }
            range.e.r = newEndRow;
          } else {
            const oldEndCol = range.e.c;
            const newEndCol = Math.max(range.s.c, oldEndCol - count);
            if (newEndCol === oldEndCol) {
              throw new Error("已无法继续删除末列");
            }
            for (let c = newEndCol + 1; c <= oldEndCol; c += 1) {
              for (let r = range.s.r; r <= range.e.r; r += 1) {
                const addr = XLSX.utils.encode_cell({ r, c });
                delete worksheet[addr];
              }
            }
            range.e.c = newEndCol;
          }

          worksheet["!ref"] = XLSX.utils.encode_range(range);
          XLSX.writeFile(workbook, filePath);
        },
      });
      const updated = fs.statSync(filePath);
      return { ok: true, updatedAt: updated.mtime.toISOString() };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }
);

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

ipcMain.handle("trace:list", async (_event, query?: string | EditTraceQuery) => {
  if (typeof query === "string") {
    const normalizedPath = String(query).trim();
    return editTraceStore.list({ targetPath: normalizedPath || undefined });
  }
  return editTraceStore.list(query);
});

ipcMain.handle("trace:get", async (_event, eventId: string) => {
  const id = String(eventId ?? "").trim();
  if (!id) {
    return null;
  }
  return editTraceStore.get(id);
});

ipcMain.handle("trace:replay", async (_event, eventId: string) => {
  const id = String(eventId ?? "").trim();
  if (!id) {
    return { ok: false, error: "事件ID不能为空" };
  }
  const event = editTraceStore.get(id);
  if (!event) {
    return { ok: false, error: "事件不存在" };
  }
  if (!event.replayText) {
    return { ok: false, error: "当前事件不支持文本回放" };
  }
  return {
    ok: true,
    targetPath: event.targetPath,
    content: event.replayText,
    timestamp: event.timestamp,
  };
});

ipcMain.handle("trace:clear", async () => {
  editTraceStore.clear();
  return { ok: true };
});

ipcMain.handle("compare:openWindow", async () => {
  createCompareWindow();
  return { ok: true };
});

ipcMain.handle("compare:getBoundDir", async () => {
  return ensureCompareBoundDir();
});

ipcMain.handle("compare:setBoundDir", async (_event, targetDir: string) => {
  const dirPath = String(targetDir ?? "").trim();
  if (!dirPath) {
    return { ok: false, error: "目录不能为空" };
  }
  try {
    const stat = fs.statSync(dirPath);
    if (!stat.isDirectory()) {
      return { ok: false, error: "目标不是目录" };
    }
    compareBoundDir = path.resolve(dirPath);
    return { ok: true, dir: compareBoundDir };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

ipcMain.handle("compare:pickBoundDir", async () => {
  const parent = getDialogParentWindow(compareWindow, mainWindow);
  const options: OpenDialogOptions = {
    title: "选择已绑定目录",
    properties: ["openDirectory"],
  };
  const result = parent ? await dialog.showOpenDialog(parent, options) : await dialog.showOpenDialog(options);
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "已取消" };
  }
  const selected = result.filePaths[0];
  try {
    const stat = fs.statSync(selected);
    if (!stat.isDirectory()) {
      return { ok: false, error: "目标不是目录" };
    }
    compareBoundDir = path.resolve(selected);
    return { ok: true, dir: compareBoundDir };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

ipcMain.handle("compare:listBoundFiles", async () => {
  const boundDir = ensureCompareBoundDir();
  if (!boundDir) {
    return { ok: false, error: "尚未绑定目录" };
  }
  try {
    const files = listComparableFilesInDir(boundDir);
    return { ok: true, dir: boundDir, files };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

ipcMain.handle("compare:pickFile", async (_event, payload?: { role?: "final" | "budget" }) => {
  const role = payload?.role === "final" ? "决算表" : payload?.role === "budget" ? "预算表" : "文件";
  const parent = getDialogParentWindow(compareWindow, mainWindow);
  const options: OpenDialogOptions = {
    title: `上传${role}`,
    properties: ["openFile"],
    filters: [
      { name: "可预览文件", extensions: ["xlsx", "xls", "docx", "doc", "pdf"] },
      { name: "All Files", extensions: ["*"] },
    ],
  };
  const result = parent ? await dialog.showOpenDialog(parent, options) : await dialog.showOpenDialog(options);
  if (result.canceled || result.filePaths.length === 0) {
    return { ok: false, message: "已取消" };
  }
  return { ok: true, path: result.filePaths[0] };
});

ipcMain.handle("compare:previewTemplate", async (_event, filePath: string) => {
  const targetPath = String(filePath ?? "").trim();
  if (!targetPath) {
    return { ok: false, error: "文件路径不能为空" };
  }
  if (!fs.existsSync(targetPath)) {
    return { ok: false, error: "文件不存在" };
  }
  try {
    const preview = await parseTemplate(targetPath);
    return { ok: true, preview };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
});

ipcMain.handle("trace:summary", async (_event, query?: string | EditTraceQuery) => {
  if (typeof query === "string") {
    const normalizedPath = String(query).trim();
    return editTraceStore.summary({ targetPath: normalizedPath || undefined });
  }
  return editTraceStore.summary(query);
});

ipcMain.handle("trace:export", async (_event, query?: string | EditTraceQuery) => {
  const parent = getDialogParentWindow(mainWindow);
  const selectedQuery: EditTraceQuery =
    typeof query === "string"
      ? { targetPath: String(query).trim() || undefined }
      : query ?? {};
  const list = editTraceStore.list(selectedQuery);
  const summary = editTraceStore.summary(selectedQuery);
  const payload = {
    exportedAt: new Date().toISOString(),
    query: selectedQuery,
    summary,
    events: list,
  };
  const result = parent
    ? await dialog.showSaveDialog(parent, {
        title: "导出编辑轨迹",
        defaultPath: `edit-trace-${Date.now()}.json`,
        filters: [{ name: "JSON", extensions: ["json"] }],
      })
    : await dialog.showSaveDialog({
        title: "导出编辑轨迹",
        defaultPath: `edit-trace-${Date.now()}.json`,
        filters: [{ name: "JSON", extensions: ["json"] }],
      });
  if (result.canceled || !result.filePath) {
    return { ok: false, message: "已取消导出" };
  }
  fs.writeFileSync(result.filePath, JSON.stringify(payload, null, 2), "utf-8");
  return { ok: true, filePath: result.filePath, count: list.length };
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

ipcMain.handle("chat:history:get", async () => {
  ensureChatSessionsInitialized();
  return {
    history: getActiveChatSession()?.history ?? [],
    version: chatHistoryVersion,
  };
});

ipcMain.handle("llm:config:get", async () => {
  return currentLlmConfig;
});

ipcMain.handle("llm:config:set", async (_event, input: Partial<LlmConfig>) => {
  const nextConfig = sanitizeLlmConfig(input);
  currentLlmConfig = nextConfig;
  saveLlmConfigToDisk(nextConfig);
  emitLlmConfigUpdated();
  return { ok: true, config: nextConfig };
});

ipcMain.handle(
  "chat:history:set",
  async (_event, history: Array<{ role: string; content: string; status?: string }>) => {
    ensureChatSessionsInitialized();
    if (Array.isArray(history) && activeChatSessionId) {
      const session = getChatSessionById(activeChatSessionId);
      if (session) {
        session.history = sanitizeChatHistory(history);
        session.updatedAt = new Date().toISOString();
        if (session.title === DEFAULT_CHAT_SESSION_TITLE) {
          session.title = deriveSessionTitleFromHistory(session.history);
        }
      }
      bumpChatHistoryVersion();
      emitChatHistoryUpdate();
      emitChatSessionsUpdate();
    }
    return { ok: true, version: chatHistoryVersion };
  }
);

ipcMain.handle("chat:sessions:list", async () => {
  ensureChatSessionsInitialized();
  return {
    activeSessionId: activeChatSessionId,
    sessions: sharedChatSessions.map(toChatSessionMeta),
  };
});

ipcMain.handle("chat:sessions:create", async (_event, input?: { title?: string }) => {
  ensureChatSessionsInitialized();
  const requestedTitle = String(input?.title ?? "").trim();
  const session = createChatSession();
  if (requestedTitle) {
    session.title = requestedTitle.slice(0, 60);
  }
  bumpChatHistoryVersion();
  emitChatHistoryUpdate();
  emitChatSessionsUpdate();
  return {
    ok: true,
    activeSessionId: session.id,
    session: toChatSessionMeta(session),
    history: session.history,
  };
});

ipcMain.handle("chat:sessions:switch", async (_event, sessionId: string) => {
  ensureChatSessionsInitialized();
  const session = getChatSessionById(String(sessionId ?? ""));
  if (!session) {
    return { ok: false, error: "会话不存在" };
  }
  activeChatSessionId = session.id;
  bumpChatHistoryVersion();
  emitChatHistoryUpdate();
  emitChatSessionsUpdate();
  return { ok: true, activeSessionId: session.id, history: session.history };
});

ipcMain.handle("chat:sessions:rename", async (_event, input: { sessionId: string; title: string }) => {
  ensureChatSessionsInitialized();
  const sessionId = String(input?.sessionId ?? "");
  const title = String(input?.title ?? "").trim();
  const session = getChatSessionById(sessionId);
  if (!session) {
    return { ok: false, error: "会话不存在" };
  }
  session.title = (title || DEFAULT_CHAT_SESSION_TITLE).slice(0, 60);
  session.updatedAt = new Date().toISOString();
  emitChatSessionsUpdate();
  return { ok: true };
});

ipcMain.handle("chat:sessions:delete", async (_event, sessionId: string) => {
  ensureChatSessionsInitialized();
  const targetId = String(sessionId ?? "");
  const target = getChatSessionById(targetId);
  if (!target) {
    return { ok: false, error: "会话不存在" };
  }

  if (sharedChatSessions.length <= 1) {
    target.history = [];
    target.title = DEFAULT_CHAT_SESSION_TITLE;
    target.updatedAt = new Date().toISOString();
    activeChatSessionId = target.id;
    bumpChatHistoryVersion();
    emitChatHistoryUpdate();
    emitChatSessionsUpdate();
    return { ok: true, activeSessionId: target.id, history: target.history };
  }

  sharedChatSessions = sharedChatSessions.filter((item) => item.id !== targetId);
  if (!activeChatSessionId || activeChatSessionId === targetId) {
    activeChatSessionId = sharedChatSessions[0]?.id ?? null;
  }
  bumpChatHistoryVersion();
  emitChatHistoryUpdate();
  emitChatSessionsUpdate();
  return {
    ok: true,
    activeSessionId: activeChatSessionId,
    history: getActiveChatSession()?.history ?? [],
  };
});

ipcMain.handle("pet:openMain", async () => {
  showOrCreateMainWindow();
});

ipcMain.handle("window:minimize", async (event) => {
  const target = getSenderWindow(event);
  if (!target) {
    return { ok: false };
  }
  target.minimize();
  return { ok: true };
});

ipcMain.handle("window:toggleMaximize", async (event) => {
  const target = getSenderWindow(event);
  if (!target) {
    return { ok: false, maximized: false };
  }
  if (target.isMaximized()) {
    target.unmaximize();
  } else {
    target.maximize();
  }
  return { ok: true, maximized: target.isMaximized() };
});

ipcMain.handle("window:isMaximized", async (event) => {
  const target = getSenderWindow(event);
  return { maximized: Boolean(target?.isMaximized()) };
});

ipcMain.handle("window:close", async (event) => {
  const target = getSenderWindow(event);
  if (!target) {
    return { ok: false };
  }
  target.close();
  return { ok: true };
});

ipcMain.handle("pet:closeChat", async () => {
  if (petChatWindow && !petChatWindow.isDestroyed()) {
    petChatWindow.hide();
  }
});

ipcMain.handle("pet:openChat", async () => {
  createPetChatWindow();
});

ipcMain.handle("pet:getWorkspaceDir", async () => {
  return ensurePetWorkspaceDir();
});

ipcMain.handle("pet:setWorkspaceDir", async (_event, droppedPath: string) => {
  const dir = normalizeWorkspaceDir(droppedPath);
  if (!dir) {
    return { ok: false, message: "未识别到有效目录" };
  }
  return { ok: true, dir: setBoundWorkspaceDir(dir) };
});

ipcMain.handle("pet:pickWorkspaceDir", async () => {
  const parent = getDialogParentWindow(petChatWindow, petWindow, mainWindow);
  try {
    const options: OpenDialogOptions = {
      title: "选择目录",
      properties: ["openDirectory"],
    };
    const result = parent ? await dialog.showOpenDialog(parent, options) : await dialog.showOpenDialog(options);
    if (result.canceled || result.filePaths.length === 0) {
      return { ok: false, message: "已取消" };
    }
    const dir = normalizeWorkspaceDir(result.filePaths[0]);
    if (!dir) {
      return { ok: false, message: "目录无效" };
    }
    return { ok: true, dir: setBoundWorkspaceDir(dir) };
  } finally {
    if (petChatWindow && !petChatWindow.isDestroyed()) {
      petChatWindow.setAlwaysOnTop(true, "screen-saver");
      petChatWindow.focus();
    }
  }
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
  const workspaceDir = ensurePetWorkspaceDir();
  if (!workspaceDir) {
    return { ok: false, error: "请先拖拽文件夹到桌宠，或在对话框中选择目录" };
  }

  const response = (await invokePythonChat({
    message,
    payload: {
      history,
      workspace_dir: workspaceDir,
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
    const workspaceDir = ensurePetWorkspaceDir();
    if (!workspaceDir) {
      return { ok: false, error: "请先拖拽文件夹到桌宠，或在对话框中选择目录" };
    }
    const chatId = randomUUID();
    invokePythonChatStream(
      chatId,
      {
        message,
        payload: {
          history,
          workspace_dir: workspaceDir,
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
  currentLlmConfig = loadLlmConfigFromDisk();
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
