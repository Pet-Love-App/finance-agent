import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Input, Select, Space, Typography } from "antd";
import { FileOutlined, FolderOpenOutlined, FolderOutlined } from "@ant-design/icons";

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

  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [inputText, setInputText] = useState("");
  const [selectedTask, setSelectedTask] = useState<TaskType>("qa");
  const [taskSummary, setTaskSummary] = useState<TaskSummary | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollRafRef = useRef<number | null>(null);
  const lastSyncedMessagesRef = useRef<string>("");
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

    const hydrateRoot = async () => {
      try {
        setTreeLoading(true);
        const dir = await bridge.getProjectDir();
        if (dir) {
          setRootDir(dir);
          const result = await bridge.listDir(dir);
          if (result?.ok && Array.isArray(result.entries)) {
            setTreeNodes(result.entries.map((entry: FileTreeNode) => ({ ...entry, loaded: false })));
          } else {
            setTreeNodes([]);
          }
        }
      } finally {
        setTreeLoading(false);
      }
    };

    void hydrateRoot();
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

  useEffect(() => {
    if (!rootDir || !bridge || typeof bridge.listDir !== "function") {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshTreeNodes();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [rootDir, bridge, expandedPaths]);

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
      const history = (await bridge.getChatHistory()) as ChatMessage[] | undefined;
      if (Array.isArray(history) && history.length > 0) {
        lastSyncedMessagesRef.current = JSON.stringify(history);
        setMessages(history);
      } else {
        lastSyncedMessagesRef.current = JSON.stringify([DEFAULT_CHAT_MESSAGE]);
        void bridge.setChatHistory([DEFAULT_CHAT_MESSAGE]);
      }
    };

    if (typeof bridge.subscribeChatHistory === "function") {
      unsubscribe = bridge.subscribeChatHistory((history: unknown) => {
        if (!Array.isArray(history)) return;
        const serialized = JSON.stringify(history);
        if (serialized === lastSyncedMessagesRef.current) return;
        lastSyncedMessagesRef.current = serialized;
        setMessages(history as ChatMessage[]);
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
    const serialized = JSON.stringify(messages);
    if (serialized === lastSyncedMessagesRef.current) {
      return;
    }
    lastSyncedMessagesRef.current = serialized;
    void bridge.setChatHistory(messages);
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
    const intervalMs = 18;
    const charsPerTick = 4;

    const tick = () => {
      const pending = typewriterPendingRef.current;
      if (!pending) {
        typewriterRunningRef.current = false;
        typewriterTimerRef.current = null;
        return;
      }

      const slice = pending.slice(0, charsPerTick);
      typewriterPendingRef.current = pending.slice(charsPerTick);
      appendToLastAgentMessage(slice);

      typewriterTimerRef.current = window.setTimeout(tick, intervalMs);
    };

    typewriterTimerRef.current = window.setTimeout(tick, 0);
  };

  const getTaskPayload = (task: TaskType, text: string): Record<string, unknown> => {
    if (task === "qa") {
      return { query: text };
    }
    if (task === "reimburse") {
      return {
        paths: currentFile ? [currentFile] : [],
        activity_text: text,
        rules: { max_amount: 50000, required_activity_date: true },
      };
    }
    if (task === "final_account") {
      return { filters: {} };
    }
    return {
      aggregate: { total_amount: 1000, count: 1, by_month: [] },
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
      const answer = String(taskResult.answer ?? "");
      const citations = Array.isArray(taskResult.citations) ? taskResult.citations.length : 0;
      return `\n\n### 任务结果\n- 任务类型: ${TASK_META[task].label}\n- 引用条目: ${citations}\n\n${answer}`;
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
    const taskPayload = getTaskPayload(selectedTask, text);
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
        const response = (await (useWorkspaceMode
          ? bridge.chatWithAgent(text, {
              history: historyForAgent,
              workspace_mode: true,
              workspace_dir: rootDir,
            })
          : typeof (bridge as any).runAgentTask === "function"
            ? (bridge as any).runAgentTask(selectedTask, taskPayload)
            : bridge.chatWithAgent(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
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
          stopTypewriter();
          const friendly = buildFriendlyError(event.error || "未知错误");
          const errText = friendly.detail;
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
          updateLastAgentMessageStatus("");
          updateTaskHistory(historyId, { status: "failed", error: friendly.short });
          stopListening();
          setChatLoading(false);
          return;
        }

        stopTypewriter();

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
        stopListening();
        setChatLoading(false);
      });

      try {
        const started = await (useWorkspaceMode
          ? bridge.startAgentChatStream(text, {
              history: historyForAgent,
              workspace_mode: true,
              workspace_dir: rootDir,
            })
          : typeof (bridge as any).startAgentTaskStream === "function"
            ? (bridge as any).startAgentTaskStream(selectedTask, taskPayload)
            : bridge.startAgentChatStream(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
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

  const handleDownload = async () => {
    if (!bridge || !currentFile) return;
    try {
      await (bridge as any).saveAs(currentFile);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
    <div className="app-layout" ref={appRef}>
      <aside className="sidebar" style={{ flex: `0 0 ${sidebarWidthPx}px` }}>
        <Space direction="vertical" size="small" className="sidebar-header">
          <Title level={4}>功能面板</Title>
          <Paragraph>集中处理任务、查看输出并实时预览文件。</Paragraph>
          <Space size="small" wrap>
            <Button onClick={toggleMode} size="small">
              {mode === "dark" ? "切换浅色" : "切换深色"}
            </Button>
            <Button onClick={clearChatMessages} size="small" disabled={chatLoading}>
              清空对话
            </Button>
          </Space>
        </Space>

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
                <Title level={4}>对话</Title>
                <Select
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
                <Button onClick={() => setInputText(getTaskDemoPrompt(selectedTask))} disabled={chatLoading || !bridgeReady}>
                  填入示例
                </Button>
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

              <div className="chat-input-row">
                <Input
                  value={inputText}
                  onChange={(event) => setInputText(event.target.value)}
                  onPressEnter={() => void handleSend()}
                  placeholder={`输入${selectedTask === "qa" ? "问题" : "任务说明"}，当前任务：${TASK_META[selectedTask].label}`}
                  disabled={!bridgeReady || chatLoading}
                />
                <Button onClick={() => void handleSend()} disabled={!bridgeReady || chatLoading} type="primary">
                  {chatLoading ? "发送中..." : "发送"}
                </Button>
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
  );
}

