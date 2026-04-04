import { useEffect, useRef, useState } from "react";

import { PreviewPanel } from "./components/PreviewPanel";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import type { AgentChatResponse, AgentChatStreamEvent, ChatMessage } from "./types/chat";
import type { TemplatePreview } from "./types/preview";

type TaskType = "qa" | "reimburse" | "final_account" | "budget";
type PanelPage = "dashboard" | "reimburse" | "history" | "annual";

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

const TASK_HISTORY_STORAGE_KEY = "agent_task_history_v1";
const TASK_SUMMARY_STORAGE_KEY = "agent_task_summary_v1";

export default function App() {
  const bridge = window.templateApi;
  const bridgeReady = Boolean(bridge);

  const [view, setView] = useState<"home" | "workspace">("home");
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [inputText, setInputText] = useState("");
  const [selectedTask, setSelectedTask] = useState<TaskType>("qa");
  const [panelPage, setPanelPage] = useState<PanelPage>("dashboard");
  const [historyFilterTask, setHistoryFilterTask] = useState<"all" | TaskType>("all");
  const [taskSummary, setTaskSummary] = useState<TaskSummary | null>(null);
  const [taskHistory, setTaskHistory] = useState<TaskHistoryItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollRafRef = useRef<number | null>(null);

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
      setPreview(payload);
    });

    return () => {
      unsubscribe();
      bridge.unwatchTemplate().catch(() => undefined);
    };
  }, [bridge]);

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

  const retryTask = async (item: TaskHistoryItem) => {
    if (!bridge || chatLoading) return;

    setSelectedTask(item.taskType);
    setInputText(item.inputText);
    updateTaskHistory(item.id, { status: "running", error: undefined });
    setChatLoading(true);
    setMessages((prev) => [...prev, { role: "agent", content: "", status: `正在重试任务: ${item.taskType}...` }]);

    try {
      const response = (await (
        typeof (bridge as any).runAgentTask === "function"
          ? (bridge as any).runAgentTask(item.taskType, item.payload)
          : bridge.chatWithAgent(item.inputText, {
              task_type: item.taskType,
              task_payload: item.payload,
            })
      )) as AgentChatResponse;

      if (!response.ok) {
        replaceLastAgentMessage(`重试失败：${response.error ?? "未知错误"}`);
        updateLastAgentMessageStatus("");
        updateTaskHistory(item.id, { status: "failed", error: response.error ?? "未知错误" });
        setChatLoading(false);
        return;
      }

      let content = response.reply ?? "已处理。";
      if (response.mode === "task" && response.task_result) {
        content += formatTaskResult(item.taskType, response.task_result);
        setTaskSummary({ taskType: item.taskType, result: response.task_result });
      }
      replaceLastAgentMessage(content);
      updateLastAgentMessageStatus("");
      updateTaskHistory(item.id, { status: "success", error: undefined });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      replaceLastAgentMessage(`重试异常：${message}`);
      updateLastAgentMessageStatus("");
      updateTaskHistory(item.id, { status: "failed", error: message });
    } finally {
      setChatLoading(false);
    }
  };

  const clearTaskHistory = () => {
    setTaskHistory([]);
    window.localStorage.removeItem(TASK_HISTORY_STORAGE_KEY);
  };

  const handleOpenTemplate = async (type: string, title: string) => {
    if (!bridge) {
      setError(
        "当前运行环境不是 Electron 窗口，无法访问本地文件系统。请执行 `npm run dev` 并在弹出的桌面窗口中操作。"
      );
      return;
    }

    setError(null);
    setLoading(true);
    try {
      // If we added getPredefinedTemplate to bridge:
      const targetPath = await (bridge as any).getPredefinedTemplate(type);
      setCurrentFile(targetPath);
      const snapshot = await bridge.getPreview(targetPath);
      setPreview(snapshot);
      if (type === "budget") {
        setSelectedTask("budget");
        setPanelPage("annual");
      } else if (type === "final") {
        setSelectedTask("final_account");
        setPanelPage("annual");
      } else {
        setSelectedTask("qa");
        setPanelPage("reimburse");
      }
      
      setMessages([
        {
          role: "agent",
          content: `已准备好${title}环境。模板文件已创建并打开。\n\n请上传或输入相关资料（如报销单、明细数据），我将开始自动处理并填写右侧的文档。`,
        },
      ]);
      setView("workspace");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = async () => {
    if (!bridge) {
      setError(
        "当前运行环境不是 Electron 窗口，无法访问本地文件系统。请执行 `npm run dev` 并在弹出的桌面窗口中操作。"
      );
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const selectedPath = await bridge.openTemplate();
      if (!selectedPath) {
        return;
      }
      setCurrentFile(selectedPath);
      const snapshot = await bridge.getPreview(selectedPath);
      setPreview(snapshot);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
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

  if (view === "home") {
    return (
      <div className="home-layout">
        <header className="home-header">
          <h1>智能报销 Agent</h1>
          <p>请选择你要执行的任务，启动对应的模板和助手。</p>
          {error && <p className="error">错误: {error}</p>}
        </header>

        <section className="feature-cards">
          <div className="feature-card" onClick={() => handleOpenTemplate("budget", "填写预算表")}>
            <div className="card-icon">📊</div>
            <h2>填写预算表</h2>
            <p>基于项目计划与其他资料，自动生成预算表格。</p>
          </div>
          <div className="feature-card" onClick={() => handleOpenTemplate("final", "填写决算表")}>
            <div className="card-icon">💵</div>
            <h2>填写决算表</h2>
            <p>根据核销单据、发票和账单录入，生成决算结果。</p>
          </div>
          <div className="feature-card" onClick={() => handleOpenTemplate("compare", "预算与决算核对")}>
            <div className="card-icon">⚖️</div>
            <h2>决算表和预算表核对</h2>
            <p>比对两份表单记录，发现并指出差异与异常项目。</p>
          </div>
        </section>
        
        {loading && <div className="home-loading">正在加载模板资源，请稍候...</div>}
      </div>
    );
  }

  const filteredTaskHistory =
    historyFilterTask === "all"
      ? taskHistory
      : taskHistory.filter((item) => item.taskType === historyFilterTask);

  const runningCount = taskHistory.filter((item) => item.status === "running").length;
  const successCount = taskHistory.filter((item) => item.status === "success").length;
  const failedCount = taskHistory.filter((item) => item.status === "failed").length;

  return (
    <div className="app-layout" ref={appRef}>
      <aside className="sidebar" style={{ flex: `0 0 ${sidebarWidthPx}px` }}>
        <h1>任务工作区</h1>
        <p>按页面处理报销问答、单次报销、历史记录与年度任务。</p>

        <div className="status-block" style={{ marginTop: 12 }}>
          <p>功能面板</p>
          <div className="task-output-list">
            <button className="sidebar-btn-secondary" onClick={() => setPanelPage("dashboard")}>Dashboard</button>
            <button className="sidebar-btn-secondary" onClick={() => setPanelPage("reimburse")}>单次报销</button>
            <button className="sidebar-btn-secondary" onClick={() => setPanelPage("history")}>历史记录</button>
            <button className="sidebar-btn-secondary" onClick={() => setPanelPage("annual")}>年度决算与预算</button>
          </div>
        </div>
        
        <button className="sidebar-btn-secondary" onClick={() => setView("home")} disabled={loading}>
          返回首页
        </button>

        <div className="status-block">
          <p>当前文件:</p>
          <p className="path">{currentFile ?? "未选择"}</p>
          {currentFile && (
            <button className="sidebar-btn-primary" onClick={handleDownload}>
              下载此文档
            </button>
          )}
        </div>
        {taskSummary && (
          <div className="status-block task-result-block">
            <p>最近任务结果:</p>
            <p className="task-type-label">{taskSummary.taskType}</p>
            {getTaskOutputPaths(taskSummary.taskType, taskSummary.result).length > 0 ? (
              <div className="task-output-list">
                {getTaskOutputPaths(taskSummary.taskType, taskSummary.result).map((outputPath, index) => (
                  <button
                    key={`${outputPath}-${index}`}
                    className="sidebar-btn-secondary"
                    onClick={() => void openOutputPath(outputPath)}
                  >
                    打开输出 {index + 1}
                  </button>
                ))}
              </div>
            ) : (
              <p className="task-output-empty">无可打开输出文件</p>
            )}
          </div>
        )}
        <div className="status-block task-result-block">
          <p>任务概览</p>
          <p className="task-output-empty">运行中: {runningCount}</p>
          <p className="task-output-empty">成功: {successCount}</p>
          <p className="task-output-empty">失败: {failedCount}</p>
        </div>
        {error && <p className="error">错误: {error}</p>}

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
        {panelPage === "dashboard" && (
          <section className="chat-panel" style={{ flex: "1 1 100%" }}>
            <div className="chat-header">
              <h2>Dashboard</h2>
              <button onClick={() => setPanelPage("reimburse")}>进入单次报销</button>
            </div>
            <div className="chat-messages-container">
              <div className="chat-messages">
                <div className="status-block">
                  <p>系统概览</p>
                  <p className="task-output-empty">当前任务类型：{selectedTask}</p>
                  <p className="task-output-empty">最近结果：{taskSummary?.taskType ?? "暂无"}</p>
                  <p className="task-output-empty">历史记录总数：{taskHistory.length}</p>
                </div>
                <div className="status-block">
                  <p>快捷入口</p>
                  <div className="task-output-list">
                    <button
                      className="sidebar-btn-primary"
                      disabled={chatLoading}
                      onClick={() => {
                        setSelectedTask("qa");
                        setInputText(getTaskDemoPrompt("qa"));
                        setPanelPage("reimburse");
                      }}
                    >
                      报销问答
                    </button>
                    <button
                      className="sidebar-btn-primary"
                      disabled={chatLoading}
                      onClick={() => {
                        setSelectedTask("reimburse");
                        setInputText(getTaskDemoPrompt("reimburse"));
                        setPanelPage("reimburse");
                      }}
                    >
                      单次报销
                    </button>
                    <button
                      className="sidebar-btn-primary"
                      disabled={chatLoading}
                      onClick={() => {
                        setSelectedTask("final_account");
                        setInputText(getTaskDemoPrompt("final_account"));
                        setPanelPage("annual");
                      }}
                    >
                      年度决算
                    </button>
                    <button
                      className="sidebar-btn-primary"
                      disabled={chatLoading}
                      onClick={() => {
                        setSelectedTask("budget");
                        setInputText(getTaskDemoPrompt("budget"));
                        setPanelPage("annual");
                      }}
                    >
                      预算生成
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {panelPage === "history" && (
          <section className="chat-panel" style={{ flex: "1 1 100%" }}>
            <div className="chat-header">
              <h2>任务历史</h2>
              <select
                value={historyFilterTask}
                onChange={(event) => setHistoryFilterTask(event.target.value as "all" | TaskType)}
                disabled={chatLoading}
              >
                <option value="all">全部任务</option>
                <option value="qa">报销问答</option>
                <option value="reimburse">单次报销</option>
                <option value="final_account">年度决算</option>
                <option value="budget">预算生成</option>
              </select>
              <button onClick={clearTaskHistory} disabled={chatLoading || taskHistory.length === 0}>
                清空历史
              </button>
            </div>
            <div className="chat-messages-container">
              <div className="chat-messages">
                {filteredTaskHistory.length === 0 ? (
                  <div className="status-block">
                    <p>暂无历史</p>
                    <p className="task-output-empty">当前筛选条件下没有任务记录。</p>
                  </div>
                ) : (
                  filteredTaskHistory.map((item) => (
                    <div key={item.id} className="status-block">
                      <p>{item.taskType}</p>
                      <p className="task-output-empty">时间: {new Date(item.createdAt).toLocaleString()}</p>
                      <p className="task-output-empty">输入: {item.inputText || "(无输入)"}</p>
                      <p className="task-output-empty">状态: {item.status}</p>
                      {item.error && <p className="task-history-error">错误: {item.error}</p>}
                      <button className="sidebar-btn-secondary" onClick={() => void retryTask(item)} disabled={chatLoading}>
                        重试该任务
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        )}

        {panelPage === "annual" && (
          <section className="chat-panel" style={{ flex: "1 1 100%" }}>
            <div className="chat-header">
              <h2>年度决算与预算</h2>
              <button
                disabled={chatLoading || !bridgeReady}
                onClick={() => {
                  setSelectedTask("final_account");
                  setInputText(getTaskDemoPrompt("final_account"));
                }}
              >
                准备年度决算
              </button>
              <button
                disabled={chatLoading || !bridgeReady}
                onClick={() => {
                  setSelectedTask("budget");
                  setInputText(getTaskDemoPrompt("budget"));
                }}
              >
                准备预算生成
              </button>
            </div>

            <div className="chat-messages-container">
              <div className="chat-messages">
                <div className="status-block">
                  <p>当前年度任务</p>
                  <p className="task-output-empty">任务类型: {selectedTask}</p>
                  <p className="task-output-empty">建议输入: 使用下方输入框直接执行。</p>
                </div>
                {taskSummary && (taskSummary.taskType === "final_account" || taskSummary.taskType === "budget") && (
                  <div className="status-block">
                    <p>最近年度输出</p>
                    <div className="task-output-list">
                      {getTaskOutputPaths(taskSummary.taskType, taskSummary.result).map((outputPath, index) => (
                        <button
                          key={`${outputPath}-${index}`}
                          className="sidebar-btn-secondary"
                          onClick={() => void openOutputPath(outputPath)}
                        >
                          打开输出 {index + 1}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="chat-input-row">
              <input
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleSend();
                  }
                }}
                placeholder={`输入任务说明，当前任务：${selectedTask}`}
                disabled={!bridgeReady || chatLoading}
              />
              <button
                onClick={() => {
                  if (selectedTask !== "final_account" && selectedTask !== "budget") {
                    setSelectedTask("final_account");
                  }
                  void handleSend();
                }}
                disabled={!bridgeReady || chatLoading}
              >
                {chatLoading ? "执行中..." : "执行年度任务"}
              </button>
            </div>
          </section>
        )}

        {panelPage === "reimburse" && (
          <>
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
                <h2>单次报销与问答</h2>
                <select
                  value={selectedTask}
                  onChange={(event) => setSelectedTask(event.target.value as TaskType)}
                  disabled={chatLoading || !bridgeReady}
                >
                  <option value="qa">报销问答</option>
                  <option value="reimburse">单次报销</option>
                  <option value="final_account">年度决算</option>
                  <option value="budget">预算生成</option>
                </select>
                <button
                  onClick={() => setInputText(getTaskDemoPrompt(selectedTask))}
                  disabled={chatLoading || !bridgeReady}
                >
                  填入当前任务示例
                </button>
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
                <input
                  value={inputText}
                  onChange={(event) => setInputText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      void handleSend();
                    }
                  }}
                  placeholder={`输入${selectedTask === "qa" ? "问题" : "任务说明"}，当前任务：${selectedTask}`}
                  disabled={!bridgeReady || chatLoading}
                />
                <button onClick={() => void handleSend()} disabled={!bridgeReady || chatLoading}>
                  {chatLoading ? "发送中..." : "发送"}
                </button>
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
          </>
        )}
      </main>
    </div>
  );
}

