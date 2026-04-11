import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Input, Select, Space, Tag, Typography } from "antd";
import {
  BorderOutlined,
  CloseOutlined,
  FileOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  MinusOutlined,
  FullscreenExitOutlined,
} from "@ant-design/icons";

import { PreviewPanel } from "./components/PreviewPanel";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import type { AgentChatResponse, AgentChatStreamEvent, ChatMessage } from "./types/chat";
import type { FilePreview } from "./types/preview";
import type {
  EditTraceEvent,
  EditTraceEventDetail,
  EditTraceQuery,
  EditTraceSummary,
  TraceOperation,
} from "./types/trace";
import { useThemeMode } from "./theme";

type TaskType = "qa" | "reimburse" | "final_account" | "budget";

type FileTreeNode = {
  name: string;
  path: string;
  isDir: boolean;
  loaded?: boolean;
  children?: FileTreeNode[];
};

type WorkspaceFileEntry = {
  name: string;
  path: string;
  relativePath: string;
};

type TaskSummary = {
  taskType: TaskType;
  result: Record<string, unknown>;
};

type TaskHistoryItem = {
  id: string;
  taskType: TaskType;
  inputText: string;
  payload: Record<string, unknown>;
  status: "running" | "success" | "failed";
  createdAt: string;
  error?: string;
};

const { Title, Paragraph, Text } = Typography;

const TASK_HISTORY_STORAGE_KEY = "agent_task_history_v1";
const TASK_SUMMARY_STORAGE_KEY = "agent_task_summary_v1";
const DEFAULT_CHAT_MESSAGE: ChatMessage = {
  role: "agent",
  content: "你好，我已就绪。你可以直接提问报销规则，或选择任务类型后描述目标，我会给出可执行结果。",
};

const TASK_META: Record<TaskType, { label: string; demo: string }> = {
  qa: { label: "报销问答", demo: "餐饮发票能报销吗？" },
  reimburse: { label: "单次报销", demo: "2026-03-10 在教室举办活动，产生交通支出" },
  final_account: { label: "年度决算", demo: "请生成年度决算" },
  budget: { label: "预算生成", demo: "请生成下一年度预算" },
};

const TRACE_OPERATION_LABEL: Record<TraceOperation, string> = {
  write_file: "文本写入",
  update_excel_cell: "改单元格",
  update_excel_range: "批量粘贴",
  append_excel_rows: "追加行",
  trim_excel_sheet: "删除行列",
};

const TRACE_OPERATION_OPTIONS: Array<{ label: string; value: TraceOperation }> = (
  Object.keys(TRACE_OPERATION_LABEL) as TraceOperation[]
).map((key) => ({ value: key, label: TRACE_OPERATION_LABEL[key] }));

export default function App() {
  const bridge = window.templateApi;
  const bridgeReady = Boolean(bridge);
  const { mode, toggleMode } = useThemeMode();
  const [windowMaximized, setWindowMaximized] = useState(false);

  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [inputText, setInputText] = useState("");
  const [referencedFiles, setReferencedFiles] = useState<WorkspaceFileEntry[]>([]);
  const [mentionPickerOpen, setMentionPickerOpen] = useState(false);
  const [mentionKeyword, setMentionKeyword] = useState("");
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFileEntry[]>([]);
  const [workspaceFilesLoading, setWorkspaceFilesLoading] = useState(false);
  const [selectedTask, setSelectedTask] = useState<TaskType>("qa");
  const [taskSummary, setTaskSummary] = useState<TaskSummary | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollRafRef = useRef<number | null>(null);
  const lastSyncedMessagesRef = useRef<string>("");
  const latestMessagesRef = useRef<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const chatHistoryVersionRef = useRef(0);
  const streamInFlightRef = useRef(false);
  const chatHistorySaveTimerRef = useRef<number | null>(null);
  const [rootDir, setRootDir] = useState<string | null>(null);
  const [treeNodes, setTreeNodes] = useState<FileTreeNode[]>([]);
  const [expandedPaths, setExpandedPaths] = useState<string[]>([]);
  const [loadingPaths, setLoadingPaths] = useState<string[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const treeRefreshInFlightRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);

  const [editorContent, setEditorContent] = useState("");
  const [editorDirty, setEditorDirty] = useState(false);
  const [editorSaving, setEditorSaving] = useState(false);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [editorAutoSave, setEditorAutoSave] = useState(true);
  const [editorLastSavedAt, setEditorLastSavedAt] = useState<string | null>(null);
  const [traceEvents, setTraceEvents] = useState<EditTraceEvent[]>([]);
  const [traceFilterPath, setTraceFilterPath] = useState("");
  const [traceStatusFilter, setTraceStatusFilter] = useState<"all" | "ok" | "failed">("all");
  const [traceOperationFilter, setTraceOperationFilter] = useState<TraceOperation[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceDetail, setTraceDetail] = useState<EditTraceEventDetail | null>(null);
  const [traceSummary, setTraceSummary] = useState<EditTraceSummary | null>(null);

  const appRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const inputComposerRef = useRef<HTMLDivElement>(null);
  const [chatPanePercent, setChatPanePercent] = useState<number>(45);
  const [sidebarWidthPx, setSidebarWidthPx] = useState<number>(280);
  const splitterDragRef = useRef<
    | null
    | {
        kind: "chat";
        pointerId: number;
        startX: number;
        startPercent: number;
        width: number;
        sign: 1 | -1;
      }
    | {
        kind: "sidebar";
        pointerId: number;
        startX: number;
        startWidthPx: number;
        appWidth: number;
      }
  >(null);

  const RESIZE_HIT_PX = 8;

  const typewriterPendingRef = useRef("");
  const typewriterTimerRef = useRef<number | null>(null);
  const typewriterRunningRef = useRef(false);

  const extractHistoryEnvelope = (
    payload: unknown
  ): { history: ChatMessage[]; version?: number } | null => {
    if (Array.isArray(payload)) {
      return { history: payload as ChatMessage[] };
    }
    if (!payload || typeof payload !== "object") {
      return null;
    }
    const envelope = payload as { history?: unknown; version?: unknown };
    if (!Array.isArray(envelope.history)) {
      return null;
    }
    const version = Number(envelope.version);
    return {
      history: envelope.history as ChatMessage[],
      version: Number.isFinite(version) ? version : undefined,
    };
  };

  useEffect(() => {
    try {
      const historyRaw = window.localStorage.getItem(TASK_HISTORY_STORAGE_KEY);
      if (historyRaw) {
        const parsed = JSON.parse(historyRaw) as TaskHistoryItem[];
        if (Array.isArray(parsed)) {
          setTaskHistory(parsed.slice(0, 20));
        }
      }
      const summaryRaw = window.localStorage.getItem(TASK_SUMMARY_STORAGE_KEY);
      if (summaryRaw) {
        const parsed = JSON.parse(summaryRaw) as TaskSummary;
        if (parsed && typeof parsed === "object" && parsed.taskType && parsed.result) {
          setTaskSummary(parsed);
        }
      }
    } catch {
      // ignore localStorage parse errors
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(TASK_HISTORY_STORAGE_KEY, JSON.stringify(taskHistory));
    } catch {
      // ignore localStorage write errors
    }
  }, [taskHistory]);

  useEffect(() => {
    try {
      if (!taskSummary) {
        window.localStorage.removeItem(TASK_SUMMARY_STORAGE_KEY);
      } else {
        window.localStorage.setItem(TASK_SUMMARY_STORAGE_KEY, JSON.stringify(taskSummary));
      }
    } catch {
      // ignore localStorage write errors
    }
  }, [taskSummary]);

  useEffect(() => {
    if (scrollRafRef.current !== null) {
      cancelAnimationFrame(scrollRafRef.current);
    }
    scrollRafRef.current = requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: chatLoading ? "auto" : "smooth" });
    });
    return () => {
      if (scrollRafRef.current !== null) {
        cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
  }, [messages, chatLoading]);

  useEffect(() => {
    latestMessagesRef.current = messages;
  }, [messages]);
  const [error, setError] = useState<string | null>(
    bridgeReady
      ? null
      : "未检测到 Electron 预加载桥接（templateApi）。请使用 `npm run dev` 启动 Electron 窗口，而不是仅在浏览器中打开 Vite 页面。"
  );

  useEffect(() => {
    if (!bridge) {
      return;
    }

    const unsubscribe = bridge.subscribePreviewUpdate((payload) => {
      setPreview({ kind: "template", data: payload });
    });

    return () => {
      unsubscribe();
      bridge.unwatchTemplate().catch(() => undefined);
    };
  }, [bridge]);

  useEffect(() => {
    if (!bridge?.isWindowMaximized) {
      return;
    }
    let mounted = true;
    bridge
      .isWindowMaximized()
      .then((result) => {
        if (mounted) {
          setWindowMaximized(Boolean(result?.maximized));
        }
      })
      .catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, [bridge]);

  const handleWindowMinimize = async () => {
    await bridge?.minimizeWindow?.();
  };

  const handleWindowToggleMaximize = async () => {
    const result = await bridge?.toggleMaximizeWindow?.();
    if (result) {
      setWindowMaximized(Boolean(result.maximized));
    }
  };

  const handleWindowClose = async () => {
    await bridge?.closeWindow?.();
  };

  useEffect(() => {
    if (!preview || preview.kind !== "text") {
      setEditorContent("");
      setEditorDirty(false);
      setEditorError(null);
      setEditorLastSavedAt(null);
      return;
    }
    setEditorContent(preview.content);
    setEditorDirty(false);
    setEditorError(null);
    setEditorLastSavedAt(preview.updatedAt);
  }, [preview]);

  const traceQuery = useMemo<EditTraceQuery>(() => {
    const normalizedPath = traceFilterPath.trim();
    return {
      targetPath: normalizedPath || undefined,
      operations: traceOperationFilter.length > 0 ? traceOperationFilter : undefined,
      status: traceStatusFilter === "all" ? undefined : traceStatusFilter,
    };
  }, [traceFilterPath, traceOperationFilter, traceStatusFilter]);

  const refreshTraceEvents = async (query?: EditTraceQuery) => {
    if (!bridge || typeof (bridge as any).listEditTrace !== "function") {
      return;
    }
    setTraceLoading(true);
    try {
      const usedQuery = query ?? traceQuery;
      const [events, summary] = await Promise.all([
        ((await (bridge as any).listEditTrace(usedQuery)) ?? []) as EditTraceEvent[],
        typeof (bridge as any).getEditTraceSummary === "function"
          ? ((await (bridge as any).getEditTraceSummary(usedQuery)) as EditTraceSummary)
          : null,
      ]);
      setTraceEvents(Array.isArray(events) ? events : []);
      setTraceSummary(summary);
    } finally {
      setTraceLoading(false);
    }
  };

  useEffect(() => {
    if (!bridge || typeof (bridge as any).listEditTrace !== "function") {
      return;
    }
    void refreshTraceEvents(traceQuery);
    const timer = window.setInterval(() => {
      void refreshTraceEvents(traceQuery);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [bridge, traceQuery]);

  useEffect(() => {
    if (!bridge || typeof bridge.getProjectDir !== "function" || typeof bridge.listDir !== "function") {
      return;
    }

    let unsubscribeWorkspace: (() => void) | null = null;

    const loadRootTree = async (dir: string) => {
      setRootDir(dir);
      setExpandedPaths([]);
      const result = await bridge.listDir(dir);
      if (result?.ok && Array.isArray(result.entries)) {
        setTreeNodes(result.entries.map((entry: FileTreeNode) => ({ ...entry, loaded: false })));
      } else {
        setTreeNodes([]);
      }
    };

    const hydrateRoot = async () => {
      try {
        setTreeLoading(true);
        const boundDir =
          typeof bridge.getWorkspaceDir === "function" ? await bridge.getWorkspaceDir() : null;
        const dir = boundDir || (await bridge.getProjectDir());
        if (dir) {
          await loadRootTree(dir);
        }
      } finally {
        setTreeLoading(false);
      }
    };

    if (typeof bridge.subscribeWorkspaceUpdate === "function") {
      unsubscribeWorkspace = bridge.subscribeWorkspaceUpdate((dir) => {
        if (!dir) return;
        setTreeLoading(true);
        void loadRootTree(dir).finally(() => {
          setTreeLoading(false);
        });
      });
    }

    void hydrateRoot();
    return () => {
      if (unsubscribeWorkspace) unsubscribeWorkspace();
    };
  }, [bridge]);

  const updateTreeNode = (
    nodes: FileTreeNode[],
    targetPath: string,
    updater: (node: FileTreeNode) => FileTreeNode
  ): FileTreeNode[] => {
    return nodes.map((node) => {
      if (node.path === targetPath) {
        return updater(node);
      }
      if (node.children && node.children.length > 0) {
        return { ...node, children: updateTreeNode(node.children, targetPath, updater) };
      }
      return node;
    });
  };

  const mergeEntriesWithExistingNodes = (
    entries: FileTreeNode[],
    existingNodes: FileTreeNode[] = []
  ): FileTreeNode[] => {
    const existingMap = new Map(existingNodes.map((node) => [node.path, node]));
    return entries.map((entry) => {
      const prev = existingMap.get(entry.path);
      return {
        ...entry,
        loaded: prev?.loaded ?? false,
        children: prev?.children,
      };
    });
  };

  const refreshTreeNodes = async () => {
    if (!rootDir || !bridge || typeof bridge.listDir !== "function") return;
    if (treeRefreshInFlightRef.current) return;
    treeRefreshInFlightRef.current = true;
    try {
      const expandedSnapshot = [...expandedPaths];
      const rootEntries = await bridge.listDir(rootDir);
      if (rootEntries?.ok && Array.isArray(rootEntries.entries)) {
        setTreeNodes((prev) => mergeEntriesWithExistingNodes(rootEntries.entries as FileTreeNode[], prev));
      }

      for (const dirPath of expandedSnapshot) {
        const result = await bridge.listDir(dirPath);
        if (!result?.ok || !Array.isArray(result.entries)) continue;
        setTreeNodes((prev) =>
          updateTreeNode(prev, dirPath, (node) => ({
            ...node,
            loaded: true,
            children: mergeEntriesWithExistingNodes(result.entries as FileTreeNode[], node.children ?? []),
          }))
        );
      }
    } finally {
      treeRefreshInFlightRef.current = false;
    }
  };

  const loadDirectoryChildren = async (dirPath: string) => {
    if (!bridge || typeof bridge.listDir !== "function") return;
    if (loadingPaths.includes(dirPath)) return;
    setLoadingPaths((prev) => [...prev, dirPath]);
    try {
      const result = await bridge.listDir(dirPath);
      if (result?.ok && Array.isArray(result.entries)) {
        setTreeNodes((prev) =>
          updateTreeNode(prev, dirPath, (node) => ({
            ...node,
            loaded: true,
            children: result.entries?.map((entry: FileTreeNode) => ({ ...entry, loaded: false })) ?? [],
          }))
        );
      }
    } finally {
      setLoadingPaths((prev) => prev.filter((item) => item !== dirPath));
    }
  };

  const toggleFolder = async (node: FileTreeNode) => {
    if (!node.isDir) return;
    const isExpanded = expandedPaths.includes(node.path);
    if (isExpanded) {
      setExpandedPaths((prev) => prev.filter((item) => item !== node.path));
      return;
    }
    setExpandedPaths((prev) => [...prev, node.path]);
    if (!node.loaded) {
      await loadDirectoryChildren(node.path);
    }
  };

  const handlePickRoot = async () => {
    if (!bridge || typeof bridge.pickProjectDir !== "function" || typeof bridge.listDir !== "function") return;
    setTreeLoading(true);
    try {
      const result = await bridge.pickProjectDir();
      if (!result?.ok || !result.dir) {
        return;
      }
      setRootDir(result.dir);
      setExpandedPaths([]);
      const entries = await bridge.listDir(result.dir);
      if (entries?.ok && Array.isArray(entries.entries)) {
        setTreeNodes(entries.entries.map((entry: FileTreeNode) => ({ ...entry, loaded: false })));
      } else {
        setTreeNodes([]);
      }
    } finally {
      setTreeLoading(false);
    }
  };

  const handleRefreshTree = async () => {
    if (!rootDir || !bridge || typeof bridge.listDir !== "function") return;
    setTreeLoading(true);
    try {
      await refreshTreeNodes();
    } finally {
      setTreeLoading(false);
    }
  };

  const toRelativePath = (targetPath: string): string => {
    if (!rootDir) return targetPath;
    const normalizedRoot = rootDir.replace(/\\/g, "/").toLowerCase();
    const normalizedTarget = targetPath.replace(/\\/g, "/");
    if (normalizedTarget.toLowerCase().startsWith(`${normalizedRoot}/`)) {
      return normalizedTarget.slice(normalizedRoot.length + 1);
    }
    if (normalizedTarget.toLowerCase() === normalizedRoot) {
      return "";
    }
    return normalizedTarget;
  };

  const ensureWorkspaceFilesLoaded = async () => {
    if (
      !rootDir ||
      !bridge ||
      typeof (bridge as any).listWorkspaceFiles !== "function" ||
      workspaceFilesLoading
    ) {
      return;
    }
    if (workspaceFiles.length > 0) {
      return;
    }
    setWorkspaceFilesLoading(true);
    try {
      const result = await (bridge as any).listWorkspaceFiles(rootDir);
      if (result?.ok && Array.isArray(result.files)) {
        setWorkspaceFiles(result.files as WorkspaceFileEntry[]);
      } else {
        setWorkspaceFiles([]);
      }
    } finally {
      setWorkspaceFilesLoading(false);
    }
  };

  const openMentionPicker = () => {
    if (!bridgeReady || !rootDir) return;
    setMentionPickerOpen(true);
    void ensureWorkspaceFilesLoaded();
  };

  const removeReferencedFile = (targetPath: string) => {
    setReferencedFiles((prev) => prev.filter((item) => item.path !== targetPath));
  };

  const selectReferencedFile = (entry: WorkspaceFileEntry) => {
    setReferencedFiles((prev) => {
      if (prev.some((item) => item.path === entry.path)) return prev;
      return [...prev, entry];
    });
    setMentionPickerOpen(false);
    setMentionKeyword("");
    setInputText((prev) => prev.replace(/@$/, ""));
  };

  const filteredWorkspaceFiles = useMemo(() => {
    const keyword = mentionKeyword.trim().toLowerCase();
    if (!keyword) {
      return workspaceFiles.slice(0, 200);
    }
    return workspaceFiles
      .filter((item) => item.relativePath.toLowerCase().includes(keyword))
      .slice(0, 200);
  }, [mentionKeyword, workspaceFiles]);

  const buildReferencedContext = async (): Promise<{
    referencedPaths: string[];
    referencedContextText: string;
  }> => {
    if (!bridge || referencedFiles.length === 0) {
      return { referencedPaths: [], referencedContextText: "" };
    }
    const snippets: string[] = [];
    for (const item of referencedFiles.slice(0, 8)) {
      try {
        const result = (await bridge.readFile(item.path)) as any;
        if (!result?.ok) {
          snippets.push(
            `文件: ${item.relativePath}\n类型: unreadable\n说明: ${String(result?.error || "读取失败")}`
          );
          continue;
        }
        if (result.kind === "text") {
          const content = String(result.content || "");
          snippets.push(
            `文件: ${item.relativePath}\n类型: text\n内容:\n${content.slice(0, 6000)}${
              content.length > 6000 || result.truncated ? "\n...(已截断)" : ""
            }`
          );
          continue;
        }
        snippets.push(`文件: ${item.relativePath}\n类型: ${String(result.kind || "binary")}\n说明: 非文本文件`);
      } catch (err) {
        snippets.push(
          `文件: ${item.relativePath}\n类型: unreadable\n说明: ${
            err instanceof Error ? err.message : String(err)
          }`
        );
      }
    }
    return {
      referencedPaths: referencedFiles.map((item) => item.relativePath || toRelativePath(item.path)),
      referencedContextText: snippets.join("\n\n---\n\n"),
    };
  };

  useEffect(() => {
    if (!rootDir || !bridge || typeof bridge.listDir !== "function") {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshTreeNodes();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [rootDir, bridge, expandedPaths]);

  useEffect(() => {
    if (!rootDir || !bridge || typeof bridge.setWorkspaceDir !== "function") {
      return;
    }
    void bridge.setWorkspaceDir(rootDir);
  }, [rootDir, bridge]);

  useEffect(() => {
    setWorkspaceFiles([]);
    setMentionKeyword("");
    setMentionPickerOpen(false);
    setReferencedFiles([]);
  }, [rootDir]);

  useEffect(() => {
    if (!mentionPickerOpen) {
      return;
    }
    const onMouseDown = (event: MouseEvent) => {
      const container = inputComposerRef.current;
      if (!container) return;
      if (container.contains(event.target as Node)) return;
      setMentionPickerOpen(false);
    };
    window.addEventListener("mousedown", onMouseDown);
    return () => {
      window.removeEventListener("mousedown", onMouseDown);
    };
  }, [mentionPickerOpen]);

  const renderTreeNodes = (nodes: FileTreeNode[], depth = 0) => {
    return nodes.map((node) => {
      const isExpanded = expandedPaths.includes(node.path);
      const isLoading = loadingPaths.includes(node.path);
      return (
        <div key={node.path} className="file-tree-node" style={{ paddingLeft: depth * 14 + 8 }}>
          <button
            className={`file-tree-label${node.isDir ? " is-dir" : ""}`}
            type="button"
            onClick={() => {
              if (node.isDir) {
                void toggleFolder(node);
              } else {
                void handlePreviewFile(node.path);
              }
            }}
            aria-expanded={node.isDir ? isExpanded : undefined}
          >
            <span className="file-tree-chevron" aria-hidden="true">
              {node.isDir ? (isExpanded ? "▾" : "▸") : ""}
            </span>
            <span className="file-tree-icon" aria-hidden="true">
              {node.isDir ? (isExpanded ? <FolderOpenOutlined /> : <FolderOutlined />) : <FileOutlined />}
            </span>
            <span className="file-tree-name">{node.name}</span>
            {isLoading && <span className="file-tree-loading">加载中</span>}
          </button>
          {node.isDir && isExpanded && node.children && node.children.length > 0 && (
            <div className="file-tree-children">{renderTreeNodes(node.children, depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  useEffect(() => {
    if (!bridge || typeof bridge.getChatHistory !== "function") {
      return;
    }

    let unsubscribe: (() => void) | null = null;

    const hydrateHistory = async () => {
      const historyPayload = await bridge.getChatHistory();
      const parsed = extractHistoryEnvelope(historyPayload);
      const history = parsed?.history;
      if (typeof parsed?.version === "number") {
        chatHistoryVersionRef.current = parsed.version;
      }
      if (Array.isArray(history) && history.length > 0) {
        const serialized = JSON.stringify(history);
        lastSyncedMessagesRef.current = serialized;
        latestMessagesRef.current = history;
        setMessages(history);
      } else {
        const fallback = [DEFAULT_CHAT_MESSAGE];
        const serialized = JSON.stringify(fallback);
        lastSyncedMessagesRef.current = serialized;
        latestMessagesRef.current = fallback;
        setMessages(fallback);
        void bridge.setChatHistory(fallback).then((result) => {
          const version = Number((result as { version?: unknown })?.version);
          if (Number.isFinite(version)) {
            chatHistoryVersionRef.current = Math.max(chatHistoryVersionRef.current, version);
          }
        });
      }
    };

    if (typeof bridge.subscribeChatHistory === "function") {
      unsubscribe = bridge.subscribeChatHistory((payload: unknown) => {
        const parsed = extractHistoryEnvelope(payload);
        if (!parsed) return;
        if (streamInFlightRef.current) return;
        if (
          typeof parsed.version === "number" &&
          parsed.version < chatHistoryVersionRef.current
        ) {
          return;
        }
        if (typeof parsed.version === "number") {
          chatHistoryVersionRef.current = parsed.version;
        }
        const serialized = JSON.stringify(parsed.history);
        if (serialized === lastSyncedMessagesRef.current) return;
        lastSyncedMessagesRef.current = serialized;
        latestMessagesRef.current = parsed.history;
        setMessages(parsed.history);
      });
    }

    void hydrateHistory();
    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, [bridge]);

  useEffect(() => {
    if (!bridge || typeof bridge.setChatHistory !== "function") {
      return;
    }
    if (streamInFlightRef.current) {
      return;
    }
    const serialized = JSON.stringify(messages);
    if (serialized === lastSyncedMessagesRef.current) {
      return;
    }
    if (chatHistorySaveTimerRef.current !== null) {
      window.clearTimeout(chatHistorySaveTimerRef.current);
    }
    chatHistorySaveTimerRef.current = window.setTimeout(() => {
      const snapshot = latestMessagesRef.current;
      const snapshotSerialized = JSON.stringify(snapshot);
      if (snapshotSerialized === lastSyncedMessagesRef.current) {
        return;
      }
      lastSyncedMessagesRef.current = snapshotSerialized;
      void bridge.setChatHistory(snapshot).then((result) => {
        const version = Number((result as { version?: unknown })?.version);
        if (Number.isFinite(version)) {
          chatHistoryVersionRef.current = Math.max(chatHistoryVersionRef.current, version);
        }
      });
      chatHistorySaveTimerRef.current = null;
    }, 120);
    return () => {
      if (chatHistorySaveTimerRef.current !== null) {
        window.clearTimeout(chatHistorySaveTimerRef.current);
        chatHistorySaveTimerRef.current = null;
      }
    };
  }, [bridge, messages]);

  useEffect(() => {
    const onPointerMove = (event: PointerEvent) => {
      const drag = splitterDragRef.current;
      if (!drag) return;
      if (event.pointerId !== drag.pointerId) return;

      const deltaX = event.clientX - drag.startX;

      if (drag.kind === "chat") {
        if (!drag.width) return;
        const deltaPercent = ((deltaX * drag.sign) / drag.width) * 100;
        const next = drag.startPercent + deltaPercent;

        const minPanePx = 320;
        const minPercent = Math.min(45, (minPanePx / drag.width) * 100);
        const maxPercent = 100 - minPercent;

        setChatPanePercent(Math.max(minPercent, Math.min(maxPercent, next)));
        return;
      }

      const minSidebarPx = 220;
      const minMainPx = 520;
      const maxSidebarPx = Math.max(minSidebarPx, drag.appWidth - minMainPx);
      const nextSidebar = drag.startWidthPx + deltaX;
      setSidebarWidthPx(Math.max(minSidebarPx, Math.min(maxSidebarPx, nextSidebar)));
    };

    const stopDragging = () => {
      if (!splitterDragRef.current) return;
      splitterDragRef.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    const onPointerUp = () => stopDragging();
    const onPointerCancel = () => stopDragging();

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerCancel);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerCancel);
      stopDragging();
    };
  }, []);

  const updateLastAgentMessageStatus = (status: string) => {
    setMessages((prev) => {
      for (let index = prev.length - 1; index >= 0; index -= 1) {
        if (prev[index].role !== "agent") continue;
        const next = [...prev];
        next[index] = { ...next[index], status };
        return next;
      }
      return prev;
    });
  };

  const appendToLastAgentMessage = (addition: string) => {
    if (!addition) return;
    setMessages((prev) => {
      for (let index = prev.length - 1; index >= 0; index -= 1) {
        if (prev[index].role !== "agent") continue;
        const next = [...prev];
        next[index] = { ...next[index], content: next[index].content + addition };
        return next;
      }
      return prev;
    });
  };

  const replaceLastAgentMessage = (content: string) => {
    setMessages((prev) => {
      for (let index = prev.length - 1; index >= 0; index -= 1) {
        if (prev[index].role !== "agent") continue;
        const next = [...prev];
        next[index] = { ...next[index], content };
        return next;
      }
      return prev;
    });
  };

  const stopTypewriter = () => {
    if (typewriterTimerRef.current !== null) {
      window.clearTimeout(typewriterTimerRef.current);
      typewriterTimerRef.current = null;
    }
    typewriterRunningRef.current = false;
    typewriterPendingRef.current = "";
  };

  const flushTypewriterAll = () => {
    if (typewriterTimerRef.current !== null) {
      window.clearTimeout(typewriterTimerRef.current);
      typewriterTimerRef.current = null;
    }
    typewriterRunningRef.current = false;
    if (typewriterPendingRef.current) {
      appendToLastAgentMessage(typewriterPendingRef.current);
      typewriterPendingRef.current = "";
    }
  };

  const pushTypewriterDelta = (delta: string) => {
    if (!delta) return;
    typewriterPendingRef.current += delta;

    if (typewriterRunningRef.current) {
      return;
    }

    typewriterRunningRef.current = true;

    const tick = () => {
      const pending = typewriterPendingRef.current;
      if (!pending) {
        typewriterRunningRef.current = false;
        typewriterTimerRef.current = null;
        return;
      }

      // Adaptive speed avoids visible stalls when upstream emits large chunks.
      const charsPerTick = pending.length > 240 ? 24 : pending.length > 120 ? 14 : pending.length > 60 ? 8 : 4;
      const intervalMs = pending.length > 240 ? 8 : pending.length > 120 ? 12 : 16;
      const slice = pending.slice(0, charsPerTick);
      typewriterPendingRef.current = pending.slice(charsPerTick);
      appendToLastAgentMessage(slice);

      typewriterTimerRef.current = window.setTimeout(tick, intervalMs);
    };

    typewriterTimerRef.current = window.setTimeout(tick, 0);
  };

  const resolveActiveChatSessionId = async (): Promise<string> => {
    if (!bridge || typeof bridge.listChatSessions !== "function") {
      return "";
    }
    try {
      const sessionsState = await bridge.listChatSessions();
      return typeof sessionsState?.activeSessionId === "string" ? sessionsState.activeSessionId : "";
    } catch {
      return "";
    }
  };

  const getTaskPayload = (task: TaskType, text: string, chatSessionId: string): Record<string, unknown> => {
    const sessionPayload = chatSessionId ? { chat_session_id: chatSessionId } : {};
    if (task === "qa") {
      return { ...sessionPayload, query: text };
    }
    if (task === "reimburse") {
      return {
        ...sessionPayload,
        paths: currentFile ? [currentFile] : [],
        activity_text: text,
        rules: { max_amount: 50000, required_activity_date: true },
      };
    }
    if (task === "final_account") {
      return { ...sessionPayload, filters: {} };
    }
    return {
      ...sessionPayload,
      aggregate: {},
      strategy: { growth_rate: 0.08 },
    };
  };

  const getTaskDemoPrompt = (task: TaskType): string => {
    return TASK_META[task].demo;
  };

  const formatTaskResult = (task: TaskType, taskResult?: Record<string, unknown>): string => {
    if (!taskResult) {
      return "";
    }

    if (task === "qa") {
      // Chat replies should stay conversational; do not append QA evaluation/debug fields.
      return "";
    }

    if (task === "reimburse") {
      const recordId = taskResult.record_id ?? "N/A";
      const outputs = (taskResult.outputs as Record<string, unknown>) || {};
      return (
        `\n\n### 任务结果\n- 任务类型: ${TASK_META[task].label}\n- 记录ID: ${recordId}` +
        `\n- Word: ${String(outputs.word_path ?? "")}` +
        `\n- Excel: ${String(outputs.excel_path ?? "")}` +
        `\n- EML: ${String(outputs.eml_path ?? "")}`
      );
    }

    if (task === "final_account") {
      return `\n\n### 任务结果\n- 任务类型: ${TASK_META[task].label}\n- 决算文件: ${String(taskResult.final_account_path ?? "")}`;
    }

    return (
      `\n\n### 任务结果\n- 任务类型: ${TASK_META[task].label}` +
      `\n- 预算文件: ${String(taskResult.budget_path ?? "")}` +
      `\n- 报告文件: ${String(taskResult.report_path ?? "")}`
    );
  };

  const getTaskOutputPaths = (task: TaskType, taskResult: Record<string, unknown>): string[] => {
    if (task === "reimburse") {
      const outputs = (taskResult.outputs as Record<string, unknown>) || {};
      return [
        String(outputs.word_path ?? ""),
        String(outputs.excel_path ?? ""),
        String(outputs.eml_path ?? ""),
      ].filter(Boolean);
    }
    if (task === "final_account") {
      return [String(taskResult.final_account_path ?? "")].filter(Boolean);
    }
    if (task === "budget") {
      return [String(taskResult.budget_path ?? ""), String(taskResult.report_path ?? "")].filter(Boolean);
    }
    return [];
  };

  const openOutputPath = async (targetPath: string) => {
    if (!bridge || !targetPath) return;
    if (typeof (bridge as any).openLocalPath !== "function") return;
    const result = await (bridge as any).openLocalPath(targetPath);
    if (!result?.ok) {
      setError(result?.message || "打开文件失败");
    }
  };

  const pushTaskHistory = (item: TaskHistoryItem) => {
    setTaskHistory((prev) => [item, ...prev].slice(0, 20));
  };

  const updateTaskHistory = (id: string, patch: Partial<TaskHistoryItem>) => {
    setTaskHistory((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const clearTaskHistory = () => {
    setTaskHistory([]);
  };

  const clearChatMessages = () => {
    setMessages([DEFAULT_CHAT_MESSAGE]);
  };

  const formatTraceTime = (iso: string): string => {
    return new Date(iso).toLocaleTimeString();
  };

  const formatBytes = (size: number): string => {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleSelectTraceEvent = async (eventId: string) => {
    if (!bridge || typeof (bridge as any).getEditTrace !== "function") {
      return;
    }
    const detail = (await (bridge as any).getEditTrace(eventId)) as EditTraceEventDetail | null;
    setTraceDetail(detail);
  };

  const handleReplayTraceEvent = async (eventId: string) => {
    if (!bridge || typeof (bridge as any).replayEditTrace !== "function") {
      return;
    }
    const result = await (bridge as any).replayEditTrace(eventId);
    if (!result?.ok) {
      setError(result?.error || "回放失败");
      return;
    }
    const targetPath = String(result.targetPath ?? "");
    const replayContent = String(result.content ?? "");
    if (!targetPath) {
      return;
    }
    setCurrentFile(targetPath);
    setPreview({
      kind: "text",
      filePath: targetPath,
      fileType: targetPath.split(".").pop() || "txt",
      updatedAt: String(result.timestamp || new Date().toISOString()),
      content: replayContent,
      truncated: false,
    });
    setEditorContent(replayContent);
    setEditorDirty(false);
    setEditorError(null);
  };

  const handleClearTraceEvents = async () => {
    if (!bridge || typeof (bridge as any).clearEditTrace !== "function") {
      return;
    }
    await (bridge as any).clearEditTrace();
    setTraceDetail(null);
    setTraceEvents([]);
    setTraceSummary(null);
  };

  const handleExportTraceEvents = async () => {
    if (!bridge || typeof (bridge as any).exportEditTrace !== "function") {
      return;
    }
    const result = await (bridge as any).exportEditTrace(traceQuery);
    if (!result?.ok) {
      if (result?.message && result.message !== "已取消导出") {
        setError(result.message);
      }
      return;
    }
    setError(null);
  };

  const buildFriendlyError = (input: unknown): { short: string; detail: string } => {
    const raw = String(input ?? "未知错误").trim() || "未知错误";
    const lower = raw.toLowerCase();

    if (lower.includes("not a zip file")) {
      return {
        short: "Excel 文件已损坏",
        detail:
          "调用失败：目标 Excel 文件结构异常，无法直接读取。\n\n" +
          "建议：\n" +
          "1. 若系统已自动备份并重建，请重试本次写入。\n" +
          "2. 若仍失败，请从备份恢复原文件后再编辑。\n" +
          "3. 之后请仅使用 xlsx 专用编辑能力，避免文本写入 .xlsx。\n\n" +
          `原始错误：${raw}`,
      };
    }

    if (
      lower.includes("permission denied") ||
      raw.includes("权限不足") ||
      raw.includes("文件被占用")
    ) {
      return {
        short: "文件无法写入（可能被占用）",
        detail:
          "调用失败：无法写入目标文件。\n\n" +
          "建议：\n" +
          "1. 关闭正在打开该文件的 Excel/WPS。\n" +
          "2. 确认目标目录不是只读，并且当前账号有写权限。\n" +
          "3. 可先改为新文件名再重试。\n\n" +
          `原始错误：${raw}`,
      };
    }

    if (
      raw.includes("请先拖拽文件夹") ||
      raw.includes("未绑定有效目录") ||
      raw.includes("workspace_dir")
    ) {
      return {
        short: "未选择工作目录",
        detail:
          "调用失败：还没有可操作的工作目录。\n\n" +
          "建议：\n" +
          "1. 在左侧“文件”区域点击“切换”，选择项目目录。\n" +
          "2. 再次发送你的编辑指令。",
      };
    }

    return {
      short: "调用失败",
      detail: `调用失败：${raw}`,
    };
  };

  const handleSend = async () => {
    if (!bridge) {
      setError("当前运行环境不是 Electron，无法与本地 Agent 通信。");
      return;
    }

    const text = inputText.trim();
    if (!text || chatLoading) {
      return;
    }

    const historyForAgent = [
      ...messages.map((item) => ({
        role: item.role === "agent" ? "assistant" : "user",
        content: item.content,
      })),
      { role: "user", content: text },
    ];
    const referencedContext = await buildReferencedContext();
    const activeChatSessionId = await resolveActiveChatSessionId();
    const taskPayload = {
      ...getTaskPayload(selectedTask, text, activeChatSessionId),
      referenced_files: referencedContext.referencedPaths,
      referenced_file_context: referencedContext.referencedContextText,
    };
    const useWorkspaceMode = selectedTask === "qa" && Boolean(rootDir);
    const historyId = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    pushTaskHistory({
      id: historyId,
      taskType: selectedTask,
      inputText: text,
      payload: taskPayload,
      status: "running",
      createdAt: new Date().toISOString(),
    });

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInputText("");
    setChatLoading(true);

    stopTypewriter();

    try {
      const supportsStream =
        typeof bridge.startAgentChatStream === "function" &&
        typeof bridge.subscribeAgentChatEvent === "function";

      if (!supportsStream) {
        streamInFlightRef.current = false;
        const response = (await (useWorkspaceMode
          ? bridge.chatWithAgent(text, {
              history: historyForAgent,
              workspace_mode: true,
              workspace_dir: rootDir,
              chat_session_id: activeChatSessionId,
              referenced_files: referencedContext.referencedPaths,
              referenced_file_context: referencedContext.referencedContextText,
            })
          : typeof (bridge as any).runAgentTask === "function"
            ? (bridge as any).runAgentTask(selectedTask, taskPayload)
            : bridge.chatWithAgent(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
                chat_session_id: activeChatSessionId,
                referenced_files: referencedContext.referencedPaths,
                referenced_file_context: referencedContext.referencedContextText,
              }))) as AgentChatResponse;
        if (!response.ok) {
          const friendly = buildFriendlyError(response.error);
          setMessages((prev) => [
            ...prev,
            { role: "agent", content: friendly.detail },
          ]);
          updateTaskHistory(historyId, { status: "failed", error: friendly.short });
          setChatLoading(false);
          return;
        }

        let content = response.reply ?? "已处理。";
        if (response.report_markdown) {
          content += `\n\n${response.report_markdown}`;
        }
        if (response.mode === "task" && response.task_result) {
          content += formatTaskResult(selectedTask, response.task_result);
          setTaskSummary({ taskType: selectedTask, result: response.task_result });
        }
        updateTaskHistory(historyId, { status: "success", error: undefined });

        setMessages((prev) => [...prev, { role: "agent", content }]);
        setChatLoading(false);
        return;
      }

      streamInFlightRef.current = true;
      setMessages((prev) => [...prev, { role: "agent", content: "", status: "正在连接 Agent..." }]);

      let startedChatId = "";
      let streamedText = "";

      const stopListening = bridge.subscribeAgentChatEvent((event: AgentChatStreamEvent) => {
        if (!startedChatId) {
          startedChatId = event.chatId;
        }

        if (event.chatId !== startedChatId) {
          return;
        }

        if (event.type === "status") {
          updateLastAgentMessageStatus(event.status);
          return;
        }

        if (event.type === "delta") {
          streamedText += event.delta;
          pushTypewriterDelta(event.delta);
          return;
        }

        if (event.type === "error") {
          flushTypewriterAll();
          const friendly = buildFriendlyError(event.error || "未知错误");
          const errText = friendly.detail;
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
          updateLastAgentMessageStatus("");
          updateTaskHistory(historyId, { status: "failed", error: friendly.short });
          streamInFlightRef.current = false;
          stopListening();
          setChatLoading(false);
          return;
        }

        flushTypewriterAll();

        const response = event.response as AgentChatResponse;
        if (!response.ok) {
          const friendly = buildFriendlyError(response.error ?? "未知错误");
          replaceLastAgentMessage(friendly.detail);
          updateLastAgentMessageStatus("");
          updateTaskHistory(historyId, { status: "failed", error: friendly.short });
          stopListening();
          setChatLoading(false);
          return;
        }

        let finalContent = streamedText || response.reply || "已处理。";
        if (response.report_markdown && !finalContent.includes(response.report_markdown)) {
          finalContent += `\n\n${response.report_markdown}`;
        }
        if (response.mode === "task" && response.task_result) {
          finalContent += formatTaskResult(selectedTask, response.task_result);
          setTaskSummary({ taskType: selectedTask, result: response.task_result });
        }
        updateTaskHistory(historyId, { status: "success", error: undefined });
        replaceLastAgentMessage(finalContent);
        updateLastAgentMessageStatus("");
        streamInFlightRef.current = false;
        stopListening();
        setChatLoading(false);
      });

      try {
        const started = await (useWorkspaceMode
          ? bridge.startAgentChatStream(text, {
              history: historyForAgent,
              workspace_mode: true,
              workspace_dir: rootDir,
              chat_session_id: activeChatSessionId,
              referenced_files: referencedContext.referencedPaths,
              referenced_file_context: referencedContext.referencedContextText,
            })
          : typeof (bridge as any).startAgentTaskStream === "function"
            ? (bridge as any).startAgentTaskStream(selectedTask, taskPayload)
            : bridge.startAgentChatStream(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
                chat_session_id: activeChatSessionId,
                referenced_files: referencedContext.referencedPaths,
                referenced_file_context: referencedContext.referencedContextText,
              }));
        startedChatId = started.chatId;
        updateLastAgentMessageStatus(
          useWorkspaceMode ? "正在执行目录编辑..." : `正在执行任务: ${selectedTask}...`
        );
      } catch (startErr) {
        stopListening();
        throw startErr;
      }
    } catch (err) {
      streamInFlightRef.current = false;
      stopTypewriter();
      const friendly = buildFriendlyError(err instanceof Error ? err.message : String(err));
      const errText = friendly.detail;
      updateTaskHistory(historyId, {
        status: "failed",
        error: friendly.short,
      });
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "agent" && !last.content.trim()) {
          const next = [...prev];
          next[next.length - 1] = { role: "agent", content: errText };
          return next;
        }
        return [...prev, { role: "agent", content: errText }];
      });
      setChatLoading(false);
    }
  };

  const persistEditedFile = async (nextContent: string) => {
    if (!bridge || !currentFile || preview?.kind !== "text") return false;
    if (editorSaving) return false;
    setEditorSaving(true);
    setEditorError(null);
    try {
      const writeResult = await bridge.writeFile(currentFile, nextContent);
      if (!writeResult?.ok) {
        setEditorError(writeResult?.error || "保存失败");
        return false;
      }
      setEditorDirty(false);
      setEditorLastSavedAt(writeResult.updatedAt || new Date().toISOString());
      setPreview((prev) => {
        if (!prev || prev.kind !== "text") return prev;
        return {
          ...prev,
          content: nextContent,
          updatedAt: writeResult.updatedAt || prev.updatedAt,
        };
      });
      void refreshTraceEvents(traceQuery);
      return true;
    } catch (err) {
      setEditorError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setEditorSaving(false);
    }
  };

  const updateExcelCell = async (
    sheetName: string,
    rowIndex: number,
    colIndex: number,
    value: string
  ) => {
    if (!bridge || !currentFile) return;
    const result = await bridge.updateExcelCell(currentFile, sheetName, rowIndex, colIndex, value);
    if (!result?.ok) {
      setError(result?.error || "更新单元格失败");
      return;
    }
    const snapshot = await bridge.getPreview(currentFile);
    setPreview({ kind: "template", data: snapshot });
    setError(null);
    void refreshTraceEvents(traceQuery);
  };

  const updateExcelRange = async (
    sheetName: string,
    startRowIndex: number,
    startColIndex: number,
    values: string[][]
  ) => {
    if (!bridge || !currentFile) return;
    const result = await bridge.updateExcelRange(
      currentFile,
      sheetName,
      startRowIndex,
      startColIndex,
      values
    );
    if (!result?.ok) {
      setError(result?.error || "批量粘贴失败");
      return;
    }
    const snapshot = await bridge.getPreview(currentFile);
    setPreview({ kind: "template", data: snapshot });
    setError(null);
    void refreshTraceEvents(traceQuery);
  };

  const appendExcelRows = async (sheetName: string, count: number) => {
    if (!bridge || !currentFile) return;
    const result = await bridge.appendExcelRows(currentFile, sheetName, count);
    if (!result?.ok) {
      setError(result?.error || "追加空行失败");
      return;
    }
    const snapshot = await bridge.getPreview(currentFile);
    setPreview({ kind: "template", data: snapshot });
    setError(null);
    void refreshTraceEvents(traceQuery);
  };

  const trimExcelSheet = async (sheetName: string, axis: "row" | "col", count: number) => {
    if (!bridge || !currentFile) return;
    const result = await bridge.trimExcelSheet(currentFile, sheetName, axis, count);
    if (!result?.ok) {
      setError(result?.error || "结构编辑失败");
      return;
    }
    const snapshot = await bridge.getPreview(currentFile);
    setPreview({ kind: "template", data: snapshot });
    setError(null);
    void refreshTraceEvents(traceQuery);
  };

  useEffect(() => {
    if (!editorAutoSave || !editorDirty || preview?.kind !== "text") {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      return;
    }
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }
    saveTimerRef.current = window.setTimeout(() => {
      void persistEditedFile(editorContent);
    }, 600);

    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [editorAutoSave, editorDirty, editorContent, preview?.kind, currentFile]);

  const handlePreviewFile = async (filePath: string) => {
    if (!bridge) return;
    const lower = filePath.toLowerCase();
    const isTemplate =
      lower.endsWith(".xlsx") ||
      lower.endsWith(".xls") ||
      lower.endsWith(".docx") ||
      lower.endsWith(".doc") ||
      lower.endsWith(".pdf");
    try {
      if (isTemplate) {
        const snapshot = await bridge.getPreview(filePath);
        setCurrentFile(filePath);
        setPreview({ kind: "template", data: snapshot });
        setError(null);
        return;
      }

      if (typeof bridge.unwatchTemplate === "function") {
        await bridge.unwatchTemplate();
      }

      const response = (await bridge.readFile(filePath)) as any;
      if (!response?.ok) {
        setError(response?.error || "预览失败");
        return;
      }

      if (response.kind === "text") {
        setPreview({
          kind: "text",
          filePath: response.filePath || filePath,
          fileType: response.fileType || "unknown",
          updatedAt: response.updatedAt || new Date().toISOString(),
          content: response.content || "",
          truncated: response.truncated,
        });
        setEditorContent(response.content || "");
        setEditorDirty(false);
        setEditorError(null);
        setEditorLastSavedAt(response.updatedAt || new Date().toISOString());
      } else if (response.kind === "image") {
        setPreview({
          kind: "image",
          filePath: response.filePath || filePath,
          fileType: response.fileType || "unknown",
          updatedAt: response.updatedAt || new Date().toISOString(),
          dataUrl: response.dataUrl || "",
          truncated: response.truncated,
        });
      } else {
        setPreview({
          kind: "binary",
          filePath: response.filePath || filePath,
          fileType: response.fileType || "unknown",
          updatedAt: response.updatedAt || new Date().toISOString(),
          size: typeof response.size === "number" ? response.size : 0,
          hex: response.hex || "",
          truncated: response.truncated,
        });
      }

      setCurrentFile(filePath);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <header className="window-titlebar">
        <div className="window-titlebar-drag">
          <span className="window-title-text">桌宠助手</span>
        </div>
        <div className="window-titlebar-actions">
          <button
            type="button"
            className="window-control-btn"
            aria-label="最小化"
            title="最小化"
            onClick={() => void handleWindowMinimize()}
          >
            <MinusOutlined />
          </button>
          <button
            type="button"
            className="window-control-btn"
            aria-label={windowMaximized ? "还原" : "最大化"}
            title={windowMaximized ? "还原" : "最大化"}
            onClick={() => void handleWindowToggleMaximize()}
          >
            {windowMaximized ? <FullscreenExitOutlined /> : <BorderOutlined />}
          </button>
          <button
            type="button"
            className="window-control-btn is-close"
            aria-label="关闭"
            title="关闭"
            onClick={() => void handleWindowClose()}
          >
            <CloseOutlined />
          </button>
        </div>
      </header>
      <div className="app-layout" ref={appRef}>
        <aside className="sidebar" style={{ flex: `0 0 ${sidebarWidthPx}px` }}>
        <Space direction="vertical" size="small" className="sidebar-header">
          <div className="sidebar-title-row">
            <Title level={4}>功能面板</Title>
            <Text className={`ready-pill ${bridgeReady ? "is-ready" : "is-warn"}`}>
              {bridgeReady ? "连接正常" : "连接未就绪"}
            </Text>
          </div>
          <Paragraph>按“文件准备 → 发起任务 → 查看结果”的流程操作，上手更快。</Paragraph>
          <div className="sidebar-steps" aria-label="任务步骤">
            <span className="sidebar-step is-active">1 选任务</span>
            <span className="sidebar-step">2 发起任务</span>
            <span className="sidebar-step">3 查看结果</span>
          </div>
          <Button
            type="primary"
            className="primary-action-btn"
            onClick={() => void bridge?.openCompareWindow?.()}
            disabled={!bridgeReady}
          >
            打开比对窗口
          </Button>
          <Space size="small" wrap className="sidebar-quick-actions">
            <Button onClick={() => setInputText(getTaskDemoPrompt(selectedTask))} size="small" disabled={chatLoading || !bridgeReady}>
              填入示例
            </Button>
            <Button onClick={clearChatMessages} size="small" disabled={chatLoading}>
              清空对话
            </Button>
            <Button onClick={toggleMode} size="small">
              {mode === "dark" ? "切换浅色" : "切换深色"}
            </Button>
          </Space>
        </Space>

        <Card size="small" className="status-block task-focus-card">
          <div className="task-focus-header">
            <Text strong>当前任务</Text>
            <Select
              size="small"
              value={selectedTask}
              onChange={(value) => setSelectedTask(value as TaskType)}
              disabled={chatLoading || !bridgeReady}
              options={[
                { value: "qa", label: TASK_META.qa.label },
                { value: "reimburse", label: TASK_META.reimburse.label },
                { value: "final_account", label: TASK_META.final_account.label },
                { value: "budget", label: TASK_META.budget.label },
              ]}
            />
          </div>
          <Text className="task-focus-hint">示例：{TASK_META[selectedTask].demo}</Text>
        </Card>

        <Card size="small" className="status-block file-tree-card">
          <div className="file-tree-header">
            <Text strong>文件</Text>
            <Space size="small">
              <Button size="small" onClick={() => void handleRefreshTree()} disabled={!bridgeReady || treeLoading}>
                刷新
              </Button>
              <Button size="small" onClick={() => void handlePickRoot()} disabled={!bridgeReady || treeLoading}>
                切换
              </Button>
            </Space>
          </div>
          <Paragraph className="file-tree-root">{rootDir ?? "未选择目录"}</Paragraph>
          <div className="file-tree">
            {treeLoading ? (
              <Text className="task-output-empty">正在加载目录...</Text>
            ) : treeNodes.length === 0 ? (
              <Text className="task-output-empty">暂无文件</Text>
            ) : (
              renderTreeNodes(treeNodes)
            )}
          </div>
        </Card>

        {taskSummary && (
          <Card size="small" className="status-block task-result-block">
            <Text strong>最近任务结果:</Text>
            <Paragraph className="task-type-label">{TASK_META[taskSummary.taskType].label}</Paragraph>
            {getTaskOutputPaths(taskSummary.taskType, taskSummary.result).length > 0 ? (
              <Space direction="vertical" size="small" className="task-output-list">
                {getTaskOutputPaths(taskSummary.taskType, taskSummary.result).map((outputPath, index) => (
                  <Button
                    key={`${outputPath}-${index}`}
                    onClick={() => void openOutputPath(outputPath)}
                  >
                    打开输出 {index + 1}
                  </Button>
                ))}
              </Space>
            ) : (
              <Text className="task-output-empty">无可打开输出文件</Text>
            )}
          </Card>
        )}

        <details className="sidebar-advanced-block">
          <summary>高级功能：编辑轨迹</summary>
          <Card size="small" className="status-block trace-card">
            <div className="task-history-header">
              <Text strong>编辑轨迹</Text>
              <Space size="small">
                <Button
                  size="small"
                  onClick={() => void refreshTraceEvents(traceQuery)}
                  disabled={!bridgeReady || traceLoading}
                >
                  刷新
                </Button>
                <Button
                  size="small"
                  onClick={() => void handleExportTraceEvents()}
                  disabled={!bridgeReady || traceEvents.length === 0}
                >
                  导出
                </Button>
                <Button
                  size="small"
                  onClick={() => void handleClearTraceEvents()}
                  disabled={!bridgeReady || traceEvents.length === 0}
                >
                  清空
                </Button>
              </Space>
            </div>
            {traceSummary && (
              <div className="trace-summary">
                <span>总计 {traceSummary.total}</span>
                <span>成功 {traceSummary.ok}</span>
                <span>失败 {traceSummary.failed}</span>
              </div>
            )}
            <Input
              size="small"
              value={traceFilterPath}
              onChange={(event) => setTraceFilterPath(event.target.value)}
              placeholder="按文件路径筛选轨迹"
            />
            <Select
              size="small"
              value={traceStatusFilter}
              onChange={(value) => setTraceStatusFilter(value as "all" | "ok" | "failed")}
              options={[
                { label: "全部状态", value: "all" },
                { label: "仅成功", value: "ok" },
                { label: "仅失败", value: "failed" },
              ]}
            />
            <Select
              mode="multiple"
              size="small"
              value={traceOperationFilter}
              onChange={(value) => setTraceOperationFilter(value as TraceOperation[])}
              options={TRACE_OPERATION_OPTIONS}
              placeholder="筛选操作类型"
              maxTagCount="responsive"
            />
            <div className="trace-list">
              {traceLoading ? (
                <Text className="task-output-empty">加载中...</Text>
              ) : traceEvents.length === 0 ? (
                <Text className="task-output-empty">暂无编辑事件</Text>
              ) : (
                traceEvents.map((event) => (
                  <button
                    key={event.id}
                    type="button"
                    className={`trace-item ${traceDetail?.id === event.id ? "active" : ""}`}
                    onClick={() => void handleSelectTraceEvent(event.id)}
                  >
                    <div className="trace-item-top">
                      <span className="trace-op">{TRACE_OPERATION_LABEL[event.operation]}</span>
                      <span className={`trace-status ${event.status}`}>{event.status === "ok" ? "成功" : "失败"}</span>
                    </div>
                    <div className="trace-path" title={event.targetPath}>{event.targetPath}</div>
                    <div className="trace-meta">
                      <span>{formatTraceTime(event.timestamp)}</span>
                      {event.diff && (
                        <span>
                          +{event.diff.added} -{event.diff.removed} ~{event.diff.changed}
                        </span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </Card>
        </details>

        <details className="sidebar-advanced-block">
          <summary>高级功能：任务历史</summary>
          <Card size="small" className="status-block task-history-block">
            <div className="task-history-header">
              <Text strong>任务历史</Text>
              <Button
                size="small"
                className="task-clear-btn"
                onClick={clearTaskHistory}
                disabled={taskHistory.length === 0}
              >
                清空
              </Button>
            </div>
            <div className="task-history-list">
              {taskHistory.length === 0 ? (
                <Text className="task-output-empty">暂无任务记录</Text>
              ) : (
                taskHistory.map((item) => (
                  <div className="task-history-item" key={item.id}>
                    <div className="task-history-top">
                      <span className="task-history-type">{TASK_META[item.taskType].label}</span>
                      <span className={`task-history-status ${item.status}`}>
                        {item.status === "running" ? "运行中" : item.status === "success" ? "成功" : "失败"}
                      </span>
                    </div>
                    <div className="task-history-input">{item.inputText || "(空输入)"}</div>
                    {item.error ? <div className="task-history-error">{item.error}</div> : null}
                  </div>
                ))
              )}
            </div>
          </Card>
        </details>

        {error && <Alert type="error" message={`错误: ${error}`} />}

        <div
          className="resize-handle resize-handle--right"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整侧边栏宽度"
          tabIndex={0}
          onPointerDown={(event) => {
            const container = appRef.current;
            if (!container) return;

            const sidebarEl = (event.currentTarget as HTMLDivElement).parentElement;
            if (sidebarEl) {
              const rect = sidebarEl.getBoundingClientRect();
              if (event.clientX < rect.right - RESIZE_HIT_PX) return;
            }

            const rect = container.getBoundingClientRect();
            splitterDragRef.current = {
              kind: "sidebar",
              pointerId: event.pointerId,
              startX: event.clientX,
              startWidthPx: sidebarWidthPx,
              appWidth: rect.width,
            };
            (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
            document.body.style.userSelect = "none";
            document.body.style.cursor = "col-resize";
          }}
          onKeyDown={(event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            const delta = event.key === "ArrowLeft" ? -12 : 12;
            setSidebarWidthPx((prev) => Math.max(220, prev + delta));
          }}
        />
        </aside>

        <main className="content" ref={contentRef}>
        <section className="chat-panel" style={{ flex: `0 0 ${chatPanePercent}%` }}>
              <div
                className="resize-handle resize-handle--right"
                role="separator"
                aria-orientation="vertical"
                aria-label="调整聊天与预览宽度"
                tabIndex={0}
                onPointerDown={(event) => {
                  const container = contentRef.current;
                  if (!container) return;

                  const chatEl = (event.currentTarget as HTMLDivElement).parentElement;
                  if (chatEl) {
                    const rect = chatEl.getBoundingClientRect();
                    if (event.clientX < rect.right - RESIZE_HIT_PX) return;
                  }

                  const rect = container.getBoundingClientRect();
                  splitterDragRef.current = {
                    kind: "chat",
                    pointerId: event.pointerId,
                    startX: event.clientX,
                    startPercent: chatPanePercent,
                    width: rect.width,
                    sign: 1,
                  };
                  (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
                  document.body.style.userSelect = "none";
                  document.body.style.cursor = "col-resize";
                }}
                onKeyDown={(event) => {
                  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                  event.preventDefault();
                  const delta = event.key === "ArrowLeft" ? -2 : 2;
                  setChatPanePercent((prev) => Math.max(20, Math.min(80, prev + delta)));
                }}
              />
              <div className="chat-header">
                <div className="chat-header-main">
                  <Title level={4}>对话执行区</Title>
                  <Text className="chat-header-subtitle">
                    当前任务：{TASK_META[selectedTask].label}
                  </Text>
                </div>
              </div>

              <div className="chat-messages-container">
                <div className="chat-messages">
                  {messages.map((msg, index) => (
                    <div key={index} className={`chat-message-row ${msg.role}`}>
                      <div className="chat-avatar">{msg.role === "user" ? "我" : "AI"}</div>
                      <div className="chat-msg-bubble-container">
                        <div className="chat-msg-name">{msg.role === "user" ? "你" : "Agent"}</div>
                        <div className={`chat-msg-bubble ${msg.role}`}>
                          {msg.role === "agent" ? (
                            <div className="markdown-content">
                              {msg.status && (
                                <div className="agent-status-card" aria-live="polite">
                                  <span className="spinner-icon" aria-hidden="true">
                                    ↻
                                  </span>
                                  <span className="agent-status-text">{msg.status}</span>
                                </div>
                              )}
                              <MarkdownRenderer content={msg.content} />
                            </div>
                          ) : (
                            <div className="plaintext-content">{msg.content}</div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              <div className="chat-input-row chat-input-row--column" ref={inputComposerRef}>
                {referencedFiles.length > 0 && (
                  <div className="chat-referenced-tabs">
                    {referencedFiles.map((item) => (
                      <Tag
                        key={item.path}
                        closable
                        onClose={(event) => {
                          event.preventDefault();
                          removeReferencedFile(item.path);
                        }}
                        className="chat-reference-tag"
                      >
                        {item.relativePath || item.name}
                      </Tag>
                    ))}
                  </div>
                )}
                {mentionPickerOpen && (
                  <div className="mention-picker-panel">
                    <Input
                      size="small"
                      value={mentionKeyword}
                      placeholder="搜索文件路径..."
                      onChange={(event) => setMentionKeyword(event.target.value)}
                    />
                    <div className="mention-picker-list">
                      {workspaceFilesLoading ? (
                        <div className="mention-picker-empty">正在加载文件...</div>
                      ) : filteredWorkspaceFiles.length === 0 ? (
                        <div className="mention-picker-empty">未匹配到文件</div>
                      ) : (
                        filteredWorkspaceFiles.map((item) => (
                          <button
                            type="button"
                            key={item.path}
                            className="mention-picker-item"
                            onClick={() => selectReferencedFile(item)}
                          >
                            <span className="mention-picker-name">{item.name}</span>
                            <span className="mention-picker-path">{item.relativePath}</span>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                )}
                <div className="chat-input-actions">
                  <Input
                    value={inputText}
                    onChange={(event) => {
                      const next = event.target.value;
                      const insertedAt = next.length > inputText.length && next.endsWith("@");
                      setInputText(next);
                      if (insertedAt) {
                        openMentionPicker();
                      }
                    }}
                    onPressEnter={() => void handleSend()}
                    placeholder={`输入${selectedTask === "qa" ? "问题" : "任务说明"}，当前任务：${TASK_META[selectedTask].label}（输入 @ 引用文件）`}
                    disabled={!bridgeReady || chatLoading}
                  />
                  <Button onClick={() => void handleSend()} disabled={!bridgeReady || chatLoading} type="primary">
                    {chatLoading ? "发送中..." : "发送"}
                  </Button>
                </div>
              </div>
        </section>

        <div className="preview-container" style={{ flex: `1 1 ${100 - chatPanePercent}%` }}>
          <div
            className="resize-handle resize-handle--left"
            role="separator"
            aria-orientation="vertical"
            aria-label="调整聊天与预览宽度"
            tabIndex={0}
            onPointerDown={(event) => {
              const container = contentRef.current;
              if (!container) return;

              const previewEl = (event.currentTarget as HTMLDivElement).parentElement;
              if (previewEl) {
                const rect = previewEl.getBoundingClientRect();
                if (event.clientX > rect.left + RESIZE_HIT_PX) return;
              }

              const rect = container.getBoundingClientRect();
              splitterDragRef.current = {
                kind: "chat",
                pointerId: event.pointerId,
                startX: event.clientX,
                startPercent: chatPanePercent,
                width: rect.width,
                sign: 1,
              };
              (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
              document.body.style.userSelect = "none";
              document.body.style.cursor = "col-resize";
            }}
            onKeyDown={(event) => {
              if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
              event.preventDefault();
              const delta = event.key === "ArrowLeft" ? -2 : 2;
              setChatPanePercent((prev) => Math.max(20, Math.min(80, prev + delta)));
            }}
          />
          {traceDetail && (
            <section className="trace-detail-panel">
              <div className="trace-detail-header">
                <span className="trace-detail-title">编辑回放</span>
                <Space size="small">
                  <Button size="small" onClick={() => void handleReplayTraceEvent(traceDetail.id)}>
                    回放到该步
                  </Button>
                  <Button size="small" onClick={() => setTraceDetail(null)}>
                    收起
                  </Button>
                </Space>
              </div>
              <div className="trace-detail-grid">
                <div>类型: {TRACE_OPERATION_LABEL[traceDetail.operation]}</div>
                <div>时间: {new Date(traceDetail.timestamp).toLocaleString()}</div>
                <div>状态: {traceDetail.status === "ok" ? "成功" : "失败"}</div>
                <div>目标: {traceDetail.targetPath}</div>
                <div>变更前: {traceDetail.before.kind} / {formatBytes(traceDetail.before.size)}</div>
                <div>变更后: {traceDetail.after.kind} / {formatBytes(traceDetail.after.size)}</div>
              </div>
              {traceDetail.diff && (
                <div className="trace-diff-box">
                  <div className="trace-diff-summary">
                    +{traceDetail.diff.added} -{traceDetail.diff.removed} ~{traceDetail.diff.changed}
                  </div>
                  <pre className="trace-snippet">
                    {traceDetail.diff.snippets
                      .map((snippet) => `L${snippet.line}\n- ${snippet.before}\n+ ${snippet.after}`)
                      .join("\n\n")}
                  </pre>
                </div>
              )}
              {(traceDetail.beforeContent || traceDetail.afterContent) && (
                <div className="trace-content-compare">
                  <div className="trace-content-pane">
                    <div className="trace-content-title">Before</div>
                    <pre className="trace-snippet">
                      {(traceDetail.beforeContent ?? "").split(/\r?\n/).slice(0, 80).join("\n")}
                    </pre>
                  </div>
                  <div className="trace-content-pane">
                    <div className="trace-content-title">After</div>
                    <pre className="trace-snippet">
                      {(traceDetail.afterContent ?? "").split(/\r?\n/).slice(0, 80).join("\n")}
                    </pre>
                  </div>
                </div>
              )}
            </section>
          )}
          {preview?.kind === "text" && (
            <section className="editor-panel">
              <div className="editor-toolbar">
                <span className="editor-title">可视化编辑</span>
                <span className={`editor-status ${editorDirty ? "dirty" : "saved"}`}>
                  {editorSaving
                    ? "保存中..."
                    : editorDirty
                      ? "未保存"
                      : editorLastSavedAt
                        ? `已保存 ${new Date(editorLastSavedAt).toLocaleTimeString()}`
                        : "已保存"}
                </span>
                <label className="editor-autosave">
                  <input
                    type="checkbox"
                    checked={editorAutoSave}
                    onChange={(event) => setEditorAutoSave(event.target.checked)}
                  />
                  自动保存
                </label>
                <Button
                  size="small"
                  type="primary"
                  onClick={() => void persistEditedFile(editorContent)}
                  disabled={editorSaving || !editorDirty}
                >
                  保存
                </Button>
              </div>
              <textarea
                className="editor-textarea"
                value={editorContent}
                onChange={(event) => {
                  const next = event.target.value;
                  setEditorContent(next);
                  setEditorDirty(true);
                  setPreview((prev) => {
                    if (!prev || prev.kind !== "text") return prev;
                    return { ...prev, content: next };
                  });
                }}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
                    event.preventDefault();
                    void persistEditedFile(editorContent);
                  }
                }}
                spellCheck={false}
              />
              {editorError && <div className="editor-error">{editorError}</div>}
            </section>
          )}
          <PreviewPanel
            preview={preview}
            onExcelCellChange={updateExcelCell}
            onExcelRangeChange={updateExcelRange}
            onExcelAppendRows={appendExcelRows}
            onExcelTrimSheet={trimExcelSheet}
          />
        </div>
        </main>
      </div>
    </>
  );
}

