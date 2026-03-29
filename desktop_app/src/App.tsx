import { useEffect, useRef, useState } from "react";

import { PreviewPanel } from "./components/PreviewPanel";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import type { AgentChatResponse, AgentChatStreamEvent, ChatMessage } from "./types/chat";
import type { TemplatePreview } from "./types/preview";

export default function App() {
  const bridge = window.templateApi;
  const bridgeReady = Boolean(bridge);

  const [view, setView] = useState<"home" | "workspace">("home");
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [inputText, setInputText] = useState("");
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

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInputText("");
    setChatLoading(true);

    stopTypewriter();

    try {
      const supportsStream =
        typeof bridge.startAgentChatStream === "function" &&
        typeof bridge.subscribeAgentChatEvent === "function";

      if (!supportsStream) {
        const response = (await bridge.chatWithAgent(text, {
          history: historyForAgent,
        })) as AgentChatResponse;
        if (!response.ok) {
          setMessages((prev) => [
            ...prev,
            { role: "agent", content: `调用失败：${response.error ?? "未知错误"}` },
          ]);
          setChatLoading(false);
          return;
        }

        let content = response.reply ?? "已处理。";
        if (response.report_markdown) {
          content += `\n\n${response.report_markdown}`;
        }

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
          stopListening();
          setChatLoading(false);
          return;
        }

        stopTypewriter();

        const response = event.response as AgentChatResponse;
        if (!response.ok) {
          replaceLastAgentMessage(`调用失败：${response.error ?? "未知错误"}`);
          updateLastAgentMessageStatus("");
          stopListening();
          setChatLoading(false);
          return;
        }

        let finalContent = streamedText || response.reply || "已处理。";
        if (response.report_markdown && !finalContent.includes(response.report_markdown)) {
          finalContent += `\n\n${response.report_markdown}`;
        }
        replaceLastAgentMessage(finalContent);
        updateLastAgentMessageStatus("");
        stopListening();
        setChatLoading(false);
      });

      try {
        const started = await bridge.startAgentChatStream(text, {
          history: historyForAgent,
        });
        startedChatId = started.chatId;
        updateLastAgentMessageStatus("正在分析意图...");
      } catch (startErr) {
        stopListening();
        throw startErr;
      }
    } catch (err) {
      const errText = `调用异常：${err instanceof Error ? err.message : String(err)}`;
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

  return (
    <div className="app-layout" ref={appRef}>
      <aside className="sidebar" style={{ flex: `0 0 ${sidebarWidthPx}px` }}>
        <h1>任务工作区</h1>
        <p>自动监控文件变化，可随时与 Agent 对话处理。</p>
        
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
            <h2>Agent 对话</h2>
            <button
              onClick={() => setInputText("运行sample审计")}
              disabled={chatLoading || !bridgeReady}
            >
              填入示例指令
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
              placeholder="输入问题，例如：运行sample审计"
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
      </main>
    </div>
  );
}

