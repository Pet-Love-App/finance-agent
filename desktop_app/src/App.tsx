import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Input, Select, Space, Typography } from "antd";
import { FileOutlined, FolderOpenOutlined, FolderOutlined } from "@ant-design/icons";

import { PreviewPanel } from "./components/PreviewPanel";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import type { AgentChatResponse, AgentChatStreamEvent, ChatMessage } from "./types/chat";
import type { FilePreview } from "./types/preview";
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
  content: "可让我在绑定目录内读取/修改文件。建议描述：文件路径 + 修改目标。",
};

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
      const entries = await bridge.listDir(rootDir);
      if (entries?.ok && Array.isArray(entries.entries)) {
        setTreeNodes(entries.entries.map((entry: FileTreeNode) => ({ ...entry, loaded: false })));
        setExpandedPaths([]);
      } else {
        setTreeNodes([]);
      }
    } finally {
      setTreeLoading(false);
    }
  };

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
    if (task === "qa") return "餐饮发票能报销吗？";
    if (task === "reimburse") return "2026-03-10 在教室举办活动，产生交通支出";
    if (task === "final_account") return "请生成年度决算";
    return "请生成下一年度预算";
  };

  const formatTaskResult = (task: TaskType, taskResult?: Record<string, unknown>): string => {
    if (!taskResult) {
      return "";
    }

    if (task === "qa") {
      const answer = String(taskResult.answer ?? "");
      const citations = Array.isArray(taskResult.citations) ? taskResult.citations.length : 0;
      return `\n\n### 任务结果\n- 任务类型: 报销问答\n- 引用条目: ${citations}\n\n${answer}`;
    }

    if (task === "reimburse") {
      const recordId = taskResult.record_id ?? "N/A";
      const outputs = (taskResult.outputs as Record<string, unknown>) || {};
      return (
        `\n\n### 任务结果\n- 任务类型: 单次报销\n- 记录ID: ${recordId}` +
        `\n- Word: ${String(outputs.word_path ?? "")}` +
        `\n- Excel: ${String(outputs.excel_path ?? "")}` +
        `\n- EML: ${String(outputs.eml_path ?? "")}`
      );
    }

    if (task === "final_account") {
      return `\n\n### 任务结果\n- 任务类型: 年度决算\n- 决算文件: ${String(taskResult.final_account_path ?? "")}`;
    }

    return (
      `\n\n### 任务结果\n- 任务类型: 预算生成` +
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
        const response = (await (
          typeof (bridge as any).runAgentTask === "function"
            ? (bridge as any).runAgentTask(selectedTask, taskPayload)
            : bridge.chatWithAgent(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
              })
        )) as AgentChatResponse;
        if (!response.ok) {
          setMessages((prev) => [
            ...prev,
            { role: "agent", content: `调用失败：${response.error ?? "未知错误"}` },
          ]);
          updateTaskHistory(historyId, { status: "failed", error: response.error ?? "未知错误" });
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
          const errText = `调用失败：${event.error || "未知错误"}`;
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
          updateLastAgentMessageStatus("");
          updateTaskHistory(historyId, { status: "failed", error: event.error || "未知错误" });
          stopListening();
          setChatLoading(false);
          return;
        }

        stopTypewriter();

        const response = event.response as AgentChatResponse;
        if (!response.ok) {
          replaceLastAgentMessage(`调用失败：${response.error ?? "未知错误"}`);
          updateLastAgentMessageStatus("");
          updateTaskHistory(historyId, { status: "failed", error: response.error ?? "未知错误" });
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
        const started = await (
          typeof (bridge as any).startAgentTaskStream === "function"
            ? (bridge as any).startAgentTaskStream(selectedTask, taskPayload)
            : bridge.startAgentChatStream(text, {
                history: historyForAgent,
                task_type: selectedTask,
                task_payload: taskPayload,
              })
        );
        startedChatId = started.chatId;
        updateLastAgentMessageStatus(`正在执行任务: ${selectedTask}...`);
      } catch (startErr) {
        stopListening();
        throw startErr;
      }
    } catch (err) {
      const errText = `调用异常：${err instanceof Error ? err.message : String(err)}`;
      updateTaskHistory(historyId, {
        status: "failed",
        error: err instanceof Error ? err.message : String(err),
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

  const handlePreviewFile = async (filePath: string) => {
    if (!bridge) return;
    const lower = filePath.toLowerCase();
    const isTemplate = lower.endsWith(".xlsx") || lower.endsWith(".xls") || lower.endsWith(".docx");
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
          <Title level={4}>任务工作区</Title>
          <Paragraph>集中处理报销问答与任务执行，右侧实时预览文档。</Paragraph>
          <Button onClick={toggleMode} size="small">
            {mode === "dark" ? "切换浅色" : "切换深色"}
          </Button>
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

        {taskSummary && (
          <Card size="small" className="status-block task-result-block">
            <Text strong>最近任务结果:</Text>
            <Paragraph className="task-type-label">{taskSummary.taskType}</Paragraph>
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
                    { value: "qa", label: "报销问答" },
                    { value: "reimburse", label: "单次报销" },
                    { value: "final_account", label: "年度决算" },
                    { value: "budget", label: "预算生成" },
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
                  placeholder={`输入${selectedTask === "qa" ? "问题" : "任务说明"}，当前任务：${selectedTask}`}
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
          <PreviewPanel preview={preview} />
        </div>
      </main>
    </div>
  );
}

