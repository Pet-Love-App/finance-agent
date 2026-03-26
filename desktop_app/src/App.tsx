import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PreviewPanel } from "./components/PreviewPanel";
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
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
      setPreview(payload);
    });

    return () => {
      unsubscribe();
      bridge.unwatchTemplate().catch(() => undefined);
    };
  }, [bridge]);

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

    const appendToLastAgentMessage = (addition: string) => {
      setMessages((prev) => {
        const targetIndex = [...prev].reverse().findIndex((item) => item.role === "agent");
        if (targetIndex < 0) {
          return prev;
        }
        const actualIndex = prev.length - 1 - targetIndex;
        const next = [...prev];
        next[actualIndex] = {
          ...next[actualIndex],
          content: next[actualIndex].content + addition,
        };
        return next;
      });
    };

    const replaceLastAgentMessage = (content: string) => {
      setMessages((prev) => {
        const targetIndex = [...prev].reverse().findIndex((item) => item.role === "agent");
        if (targetIndex < 0) {
          return prev;
        }
        const actualIndex = prev.length - 1 - targetIndex;
        const next = [...prev];
        next[actualIndex] = {
          ...next[actualIndex],
          content,
        };
        return next;
      });
    };

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

      setMessages((prev) => [...prev, { role: "agent", content: "" }]);

      let startedChatId = "";
      let streamedText = "";

      const stopListening = bridge.subscribeAgentChatEvent((event: any) => {
        if (event.chatId !== startedChatId) {
          return;
        }

        if (event.type === "delta") {
          streamedText += event.delta;
          appendToLastAgentMessage(event.delta);
          return;
        }

        if (event.type === "error") {
          const errText = `调用失败：${event.error || "未知错误"}`;
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
          stopListening();
          setChatLoading(false);
          return;
        }

        const response = event.response as AgentChatResponse;
        if (!response.ok) {
          replaceLastAgentMessage(`调用失败：${response.error ?? "未知错误"}`);
          stopListening();
          setChatLoading(false);
          return;
        }

        let finalContent = streamedText || response.reply || "已处理。";
        if (response.report_markdown && !finalContent.includes(response.report_markdown)) {
          finalContent += `\n\n${response.report_markdown}`;
        }
        replaceLastAgentMessage(finalContent);
        stopListening();
        setChatLoading(false);
      });

      try {
        const started = await bridge.startAgentChatStream(text, {
          history: historyForAgent,
        });
        startedChatId = started.chatId;
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
    <div className="app-layout">
      <aside className="sidebar">
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
      </aside>

      <main className="content">
        <section className="chat-panel">
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
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
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
        
        <div className="preview-container">
          <PreviewPanel preview={preview} />
        </div>
      </main>
    </div>
  );
}
