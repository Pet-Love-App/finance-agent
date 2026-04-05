import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Button, Input, Select, Space, Typography } from "antd";

type ChatMessage = { role: "user" | "agent"; content: string };
type ChatSessionMeta = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};
const DEFAULT_CHAT_MESSAGE: ChatMessage = {
  role: "agent",
  content: "你好，我是桌宠助手。先绑定工作目录，然后告诉我“文件路径 + 想改成什么”，我会一步步帮你处理。",
};

const QUICK_PROMPTS = [
  "先列出当前目录文件",
  "读取 src/main.ts 并概述结构",
  "把 README 标题改成“智能报销助手”",
];

export function PetChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lastSyncedMessagesRef = useRef<string>("");

  useEffect(() => {
    document.body.classList.add("pet-route-body");
    const previousTitle = document.title;
    document.title = "桌宠对话";
    return () => {
      document.body.classList.remove("pet-route-body");
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;

    if (window.petChatApi && typeof window.petChatApi.subscribeWorkspaceUpdate === "function") {
      unsubscribe = window.petChatApi.subscribeWorkspaceUpdate((dir) => {
        setWorkspaceDir(dir ?? null);
      });
    }

    const refreshDir = async () => {
      if (window.petChatApi && typeof window.petChatApi.getWorkspaceDir === "function") {
        const dir = await window.petChatApi.getWorkspaceDir();
        setWorkspaceDir(dir ?? null);
      }
    };

    void refreshDir();
    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, []);

  useEffect(() => {
    const api = window.petChatApi;
    if (!api || typeof api.getChatHistory !== "function") {
      return;
    }

    let unsubscribeHistory: (() => void) | null = null;
    let unsubscribeSessions: (() => void) | null = null;

    const hydrateHistory = async () => {
      if (typeof api.listChatSessions === "function") {
        const sessionState = await api.listChatSessions();
        if (sessionState && Array.isArray(sessionState.sessions)) {
          setSessions(sessionState.sessions as ChatSessionMeta[]);
          setActiveSessionId(
            typeof sessionState.activeSessionId === "string" ? sessionState.activeSessionId : null
          );
        }
      }

      const history = (await api.getChatHistory()) as ChatMessage[] | undefined;
      if (Array.isArray(history) && history.length > 0) {
        lastSyncedMessagesRef.current = JSON.stringify(history);
        setMessages(history);
      } else {
        lastSyncedMessagesRef.current = JSON.stringify([DEFAULT_CHAT_MESSAGE]);
        void api.setChatHistory([DEFAULT_CHAT_MESSAGE]);
      }
    };

    if (typeof api.subscribeChatHistory === "function") {
      unsubscribeHistory = api.subscribeChatHistory((history: unknown) => {
        if (!Array.isArray(history)) return;
        const serialized = JSON.stringify(history);
        if (serialized === lastSyncedMessagesRef.current) return;
        lastSyncedMessagesRef.current = serialized;
        setMessages(history as ChatMessage[]);
      });
    }

    if (typeof api.subscribeChatSessions === "function") {
      unsubscribeSessions = api.subscribeChatSessions((payload: unknown) => {
        if (!payload || typeof payload !== "object") return;
        const sessionsPayload = payload as { sessions?: unknown; activeSessionId?: unknown };
        if (Array.isArray(sessionsPayload.sessions)) {
          setSessions(sessionsPayload.sessions as ChatSessionMeta[]);
        }
        setActiveSessionId(
          typeof sessionsPayload.activeSessionId === "string" ? sessionsPayload.activeSessionId : null
        );
      });
    }

    void hydrateHistory();
    return () => {
      if (unsubscribeHistory) unsubscribeHistory();
      if (unsubscribeSessions) unsubscribeSessions();
    };
  }, []);

  useEffect(() => {
    if (!window.petChatApi || typeof window.petChatApi.setChatHistory !== "function") {
      return;
    }
    const serialized = JSON.stringify(messages);
    if (serialized === lastSyncedMessagesRef.current) {
      return;
    }
    lastSyncedMessagesRef.current = serialized;
    void window.petChatApi.setChatHistory(messages);
  }, [messages]);

  const appendMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
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

  const sendMessage = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || !window.petChatApi || chatLoading) return;

    const supportsStream =
      typeof window.petChatApi.startChatStream === "function" &&
      typeof window.petChatApi.subscribeChatEvent === "function";

    const userMessage: ChatMessage = { role: "user", content: text };
    setInput("");
    appendMessage(userMessage);
    setChatLoading(true);

    const history = [...messages, userMessage];

    if (!supportsStream) {
      const resp = await window.petChatApi.chat(text, history);
      if (!resp || !resp.ok) {
        appendMessage({ role: "agent", content: "失败：" + ((resp && resp.error) || "未知错误") });
        setChatLoading(false);
        return;
      }

      appendMessage({ role: "agent", content: resp.reply || "已处理" });
      setChatLoading(false);
      return;
    }

    setMessages((prev) => [...prev, { role: "agent", content: "" }]);

    let startedChatId = "";
    let streamedText = "";

    const stopListening = window.petChatApi.subscribeChatEvent((event) => {
      if (!startedChatId) {
        startedChatId = event.chatId;
      }
      if (event.chatId !== startedChatId) {
        return;
      }
      if (event.type === "delta") {
        streamedText += event.delta;
        appendToLastAgentMessage(event.delta);
        return;
      }
      if (event.type === "error") {
        const errText = "失败：" + (event.error || "未知错误");
        replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
        stopListening();
        setChatLoading(false);
        return;
      }
      if (event.type === "done") {
        const response = event.response as { ok?: boolean; reply?: string; error?: string };
        if (!response?.ok) {
          const errText = "失败：" + (response?.error || "未知错误");
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
        } else {
          const finalContent = streamedText || response.reply || "已处理";
          replaceLastAgentMessage(finalContent);
        }
        stopListening();
        setChatLoading(false);
      }
    });

    try {
      const started = await window.petChatApi.startChatStream(text, history);
      if (!started || !started.ok || !started.chatId) {
        stopListening();
        replaceLastAgentMessage("失败：" + (started?.error || "无法启动流式输出"));
        setChatLoading(false);
        return;
      }
      startedChatId = started.chatId;
    } catch (err) {
      stopListening();
      replaceLastAgentMessage(`失败：${err instanceof Error ? err.message : String(err)}`);
      setChatLoading(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void sendMessage();
    }
  };

  const onOpenPanel = async () => {
    if (window.petChatApi && typeof window.petChatApi.openMainWindow === "function") {
      await window.petChatApi.openMainWindow();
    }
    if (window.petChatApi && typeof window.petChatApi.closePetChat === "function") {
      await window.petChatApi.closePetChat();
    }
  };

  const onClose = async () => {
    if (window.petChatApi && typeof window.petChatApi.closePetChat === "function") {
      await window.petChatApi.closePetChat();
    }
  };

  const onBind = async () => {
    if (window.petChatApi && typeof window.petChatApi.pickWorkspaceDir === "function") {
      await window.petChatApi.pickWorkspaceDir();
    }
  };

  const onUsePrompt = (text: string) => {
    setInput(text);
  };

  const onQuickSend = async (text: string) => {
    if (chatLoading) return;
    await sendMessage(text);
  };

  const onCreateSession = async () => {
    if (chatLoading) return;
    if (!window.petChatApi || typeof window.petChatApi.createChatSession !== "function") return;
    const created = (await window.petChatApi.createChatSession()) as
      | { ok?: boolean; activeSessionId?: string; history?: ChatMessage[] }
      | undefined;
    if (!created?.ok) return;
    const history = Array.isArray(created.history) && created.history.length > 0 ? created.history : [DEFAULT_CHAT_MESSAGE];
    lastSyncedMessagesRef.current = JSON.stringify(history);
    setMessages(history);
    if (typeof created.activeSessionId === "string") {
      setActiveSessionId(created.activeSessionId);
    }
    if (history.length === 1 && history[0].content === DEFAULT_CHAT_MESSAGE.content) {
      void window.petChatApi.setChatHistory(history);
    }
  };

  const onSwitchSession = async (sessionId: string) => {
    if (chatLoading || !sessionId) return;
    if (!window.petChatApi || typeof window.petChatApi.switchChatSession !== "function") return;
    const result = (await window.petChatApi.switchChatSession(sessionId)) as
      | { ok?: boolean; activeSessionId?: string; history?: ChatMessage[] }
      | undefined;
    if (!result?.ok) return;
    const history = Array.isArray(result.history) && result.history.length > 0 ? result.history : [DEFAULT_CHAT_MESSAGE];
    lastSyncedMessagesRef.current = JSON.stringify(history);
    setMessages(history);
    setActiveSessionId(typeof result.activeSessionId === "string" ? result.activeSessionId : sessionId);
    if (history.length === 1 && history[0].content === DEFAULT_CHAT_MESSAGE.content) {
      void window.petChatApi.setChatHistory(history);
    }
  };

  const isBound = Boolean(workspaceDir);

  return (
    <div className="pet-chat-root">
      <header className="pet-chat-header">
        <div className="pet-chat-header-info">
          <div className="pet-chat-title">
            <span className="pet-chat-title-emoji">🤖</span>
            <Typography.Text strong>桌宠助手</Typography.Text>
          </div>
          <Typography.Text className="pet-chat-dir" title={workspaceDir || "未绑定"}>
            目录：{workspaceDir || "未绑定"}
          </Typography.Text>
        </div>
        <div className="pet-chat-session-tools">
          <Select
            className="pet-chat-session-select"
            size="small"
            value={activeSessionId ?? undefined}
            placeholder="选择会话"
            onChange={(value) => void onSwitchSession(value)}
            disabled={chatLoading || sessions.length === 0}
            options={sessions.map((session) => ({
              value: session.id,
              label: `${session.title || "新会话"} (${session.messageCount})`,
            }))}
          />
          <Button size="small" onClick={() => void onCreateSession()} disabled={chatLoading}>
            新会话
          </Button>
        </div>
        <div className="pet-chat-header-actions">
          <span className={`pet-chat-badge ${isBound ? "ready" : "warn"}`}>
            {isBound ? "已绑定" : "待绑定"}
          </span>
          <Button size="small" onClick={() => void onBind()} className="pet-chat-bind-btn">
            {isBound ? "切换目录" : "绑定目录"}
          </Button>
        </div>
        <Button
          className="pet-chat-close"
          onClick={() => void onClose()}
          aria-label="关闭"
          type="text"
          size="small"
        >
          &times;
        </Button>
      </header>

      <div className="pet-chat-body">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`pet-chat-msg ${message.role}`}>
            <div className="pet-chat-msg-role">{message.role === "user" ? "你" : "助手"}</div>
            {message.content}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      <div className="pet-chat-input">
        <div className="pet-chat-quick">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="pet-chat-quick-item"
              onClick={() => onUsePrompt(prompt)}
              onDoubleClick={() => void onQuickSend(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
        <Input.TextArea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="例如：把 src/main.ts 中标题改为“智能报销助手”"
          autoSize={{ minRows: 3, maxRows: 5 }}
        />
        <Space className="pet-chat-actions" size={8}>
          <Button onClick={() => void onOpenPanel()}>打开功能面板</Button>
          <Typography.Text className="pet-chat-send-hint">Ctrl/Cmd + Enter 发送</Typography.Text>
          <Button type="primary" onClick={() => void sendMessage()} loading={chatLoading}>
            {chatLoading ? "处理中" : "发送"}
          </Button>
        </Space>
      </div>
    </div>
  );
}
