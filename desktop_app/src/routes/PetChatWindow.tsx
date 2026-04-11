import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Button, Input, Modal, Select, Space, Typography, message as antdMessage } from "antd";
import { MarkdownRenderer } from "../components/MarkdownRenderer";

type ChatMessage = { role: "user" | "agent"; content: string; status?: string };
type ChatSessionMeta = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
};
type LlmProvider = "openai" | "glm" | "deepseek" | "qwen" | "anthropic" | "custom";
type LlmConfig = {
  provider: LlmProvider;
  apiKey: string;
  baseUrl: string;
  model: string;
};

const LLM_PROVIDER_PRESETS: Record<
  Exclude<LlmProvider, "custom">,
  { label: string; baseUrl: string; model: string }
> = {
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
  glm: {
    label: "GLM (智谱)",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash",
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  qwen: {
    label: "Qwen (阿里云百炼)",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  anthropic: {
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-3-5-sonnet-latest",
  },
};

const DEFAULT_LLM_CONFIG: LlmConfig = {
  provider: "openai",
  apiKey: "",
  baseUrl: LLM_PROVIDER_PRESETS.openai.baseUrl,
  model: LLM_PROVIDER_PRESETS.openai.model,
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
const STREAM_IDLE_TIMEOUT_MS = 45000;

export function PetChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [llmConfig, setLlmConfig] = useState<LlmConfig>(DEFAULT_LLM_CONFIG);
  const [llmConfigOpen, setLlmConfigOpen] = useState(false);
  const [llmConfigLoading, setLlmConfigLoading] = useState(false);
  const [llmConfigSaving, setLlmConfigSaving] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lastSyncedMessagesRef = useRef<string>("");
  const latestMessagesRef = useRef<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const chatHistoryVersionRef = useRef(0);
  const streamInFlightRef = useRef(false);
  const chatHistorySaveTimerRef = useRef<number | null>(null);

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
    document.body.classList.add("pet-route-body");
    return () => {
      document.body.classList.remove("pet-route-body");
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    latestMessagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    const api = window.petChatApi;
    if (!api || typeof api.getLlmConfig !== "function") {
      return;
    }

    let unsubscribe: (() => void) | null = null;

    const hydrateConfig = async () => {
      setLlmConfigLoading(true);
      try {
        const config = await api.getLlmConfig();
        if (config && typeof config === "object") {
          const parsed = config as LlmConfig;
          setLlmConfig({
            provider: parsed.provider ?? "openai",
            apiKey: parsed.apiKey ?? "",
            baseUrl: parsed.baseUrl ?? "",
            model: parsed.model ?? "",
          });
        }
      } finally {
        setLlmConfigLoading(false);
      }
    };

    if (typeof api.subscribeLlmConfig === "function") {
      unsubscribe = api.subscribeLlmConfig((config: LlmConfig) => {
        setLlmConfig(config);
      });
    }

    void hydrateConfig();
    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, []);

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

      const historyPayload = await api.getChatHistory();
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
        void api.setChatHistory(fallback).then((result) => {
          const version = Number((result as { version?: unknown })?.version);
          if (Number.isFinite(version)) {
            chatHistoryVersionRef.current = Math.max(chatHistoryVersionRef.current, version);
          }
        });
      }
    };

    if (typeof api.subscribeChatHistory === "function") {
      unsubscribeHistory = api.subscribeChatHistory((payload: unknown) => {
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
    const api = window.petChatApi;
    if (!api || typeof api.setChatHistory !== "function") {
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
      void api.setChatHistory(snapshot).then((result) => {
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

  const replaceLastAgentMessage = (content: string) => {
    setMessages((prev) => {
      for (let index = prev.length - 1; index >= 0; index -= 1) {
        if (prev[index].role !== "agent") continue;
        const next = [...prev];
        next[index] = { ...next[index], content, status: "" };
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
      streamInFlightRef.current = false;
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

    streamInFlightRef.current = true;
    setMessages((prev) => [...prev, { role: "agent", content: "" }]);

    let startedChatId = "";
    let streamedText = "";
    let streamLastActivityAt = Date.now();
    let streamWatchdogTimer: number | null = null;
    let typewriterPending = "";
    let typewriterTimer: number | null = null;
    let typewriterRunning = false;
    let streamActive = true;

    const clearStreamTimers = () => {
      if (streamWatchdogTimer !== null) {
        window.clearInterval(streamWatchdogTimer);
        streamWatchdogTimer = null;
      }
      if (typewriterTimer !== null) {
        window.clearTimeout(typewriterTimer);
        typewriterTimer = null;
      }
      typewriterRunning = false;
    };

    const flushTypewriterAll = () => {
      if (typewriterTimer !== null) {
        window.clearTimeout(typewriterTimer);
        typewriterTimer = null;
      }
      typewriterRunning = false;
      if (typewriterPending) {
        appendToLastAgentMessage(typewriterPending);
        typewriterPending = "";
      }
    };

    const pushTypewriterDelta = (delta: string) => {
      if (!delta) return;
      typewriterPending += delta;
      if (typewriterRunning) return;

      typewriterRunning = true;
      const tick = () => {
        if (!typewriterPending) {
          typewriterRunning = false;
          typewriterTimer = null;
          return;
        }
        // Adaptive speed avoids long backlog when model returns big deltas.
        const charsPerTick =
          typewriterPending.length > 240
            ? 24
            : typewriterPending.length > 120
              ? 14
              : typewriterPending.length > 60
                ? 8
                : 4;
        const intervalMs = typewriterPending.length > 240 ? 8 : typewriterPending.length > 120 ? 12 : 16;
        const slice = typewriterPending.slice(0, charsPerTick);
        typewriterPending = typewriterPending.slice(charsPerTick);
        appendToLastAgentMessage(slice);
        typewriterTimer = window.setTimeout(tick, intervalMs);
      };
      typewriterTimer = window.setTimeout(tick, 0);
    };

    const startWatchdog = (stopListening: () => void) => {
      if (streamWatchdogTimer !== null) {
        window.clearInterval(streamWatchdogTimer);
      }
      streamWatchdogTimer = window.setInterval(() => {
        if (!streamActive) return;
        const idleFor = Date.now() - streamLastActivityAt;
        if (idleFor < STREAM_IDLE_TIMEOUT_MS) return;
        flushTypewriterAll();
        const timeoutText = "失败：流式输出超时，请重试。";
        replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${timeoutText}` : timeoutText);
        updateLastAgentMessageStatus("");
        if (startedChatId && typeof window.petChatApi?.stopChatStream === "function") {
          void window.petChatApi.stopChatStream(startedChatId);
        }
        stopListening();
        clearStreamTimers();
        streamActive = false;
        streamInFlightRef.current = false;
        setChatLoading(false);
      }, 1000);
    };

    const stopListening = window.petChatApi.subscribeChatEvent((event) => {
      if (!startedChatId) {
        startedChatId = event.chatId;
      }
      if (event.chatId !== startedChatId) {
        return;
      }
      streamLastActivityAt = Date.now();
      if (event.type === "status") {
        updateLastAgentMessageStatus(event.status || "正在处理...");
        return;
      }
      if (event.type === "delta") {
        streamedText += event.delta;
        pushTypewriterDelta(event.delta);
        return;
      }
      if (event.type === "error") {
        flushTypewriterAll();
        const errText = "失败：" + (event.error || "未知错误");
        replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
        updateLastAgentMessageStatus("");
        clearStreamTimers();
        streamActive = false;
        streamInFlightRef.current = false;
        stopListening();
        setChatLoading(false);
        return;
      }
      if (event.type === "done") {
        flushTypewriterAll();
        const response = event.response as { ok?: boolean; reply?: string; error?: string };
        if (!response?.ok) {
          const errText = "失败：" + (response?.error || "未知错误");
          replaceLastAgentMessage(streamedText ? `${streamedText}\n\n${errText}` : errText);
        } else {
          const finalContent = streamedText || response.reply || "已处理";
          replaceLastAgentMessage(finalContent);
        }
        updateLastAgentMessageStatus("");
        clearStreamTimers();
        streamActive = false;
        streamInFlightRef.current = false;
        stopListening();
        setChatLoading(false);
      }
    });

    try {
      const started = await window.petChatApi.startChatStream(text, history);
      if (!started || !started.ok || !started.chatId) {
        clearStreamTimers();
        streamActive = false;
        streamInFlightRef.current = false;
        stopListening();
        replaceLastAgentMessage("失败：" + (started?.error || "无法启动流式输出"));
        setChatLoading(false);
        return;
      }
      startedChatId = started.chatId;
      updateLastAgentMessageStatus("正在处理...");
      streamLastActivityAt = Date.now();
      startWatchdog(stopListening);
    } catch (err) {
      clearStreamTimers();
      streamActive = false;
      streamInFlightRef.current = false;
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

  const onProviderChange = (provider: LlmProvider) => {
    setLlmConfig((prev) => {
      if (provider === "custom") {
        return { ...prev, provider };
      }
      const preset = LLM_PROVIDER_PRESETS[provider];
      return {
        ...prev,
        provider,
        baseUrl: preset.baseUrl,
        model: preset.model,
      };
    });
  };

  const onSaveLlmConfig = async () => {
    const api = window.petChatApi;
    if (!api || typeof api.setLlmConfig !== "function") return;
    if (!llmConfig.baseUrl.trim()) {
      antdMessage.error("Base URL 不能为空");
      return;
    }
    if (!llmConfig.model.trim()) {
      antdMessage.error("模型名不能为空");
      return;
    }

    setLlmConfigSaving(true);
    try {
      const result = await api.setLlmConfig(llmConfig);
      if (!result?.ok) {
        antdMessage.error("保存失败");
        return;
      }
      setLlmConfig(result.config);
      setLlmConfigOpen(false);
      antdMessage.success("模型配置已保存，后续对话将使用新配置");
    } finally {
      setLlmConfigSaving(false);
    }
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
          <Button
            size="small"
            onClick={() => setLlmConfigOpen(true)}
            className="pet-chat-settings-btn"
            loading={llmConfigLoading}
          >
            模型设置
          </Button>
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
            {message.role === "agent" ? (
              <div className="pet-chat-msg-content">
                {message.status ? <div className="pet-chat-status">{message.status}</div> : null}
                <div className="markdown-content">
                  <MarkdownRenderer content={message.content} />
                </div>
              </div>
            ) : (
              message.content
            )}
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

      <Modal
        title="模型配置"
        open={llmConfigOpen}
        onCancel={() => setLlmConfigOpen(false)}
        onOk={() => void onSaveLlmConfig()}
        okText={llmConfigSaving ? "保存中..." : "保存"}
        confirmLoading={llmConfigSaving}
      >
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            支持 OpenAI、GLM、DeepSeek、Qwen、Anthropic，以及自定义兼容接口。
          </Typography.Text>
          <Typography.Text>提供商</Typography.Text>
          <Select<LlmProvider>
            value={llmConfig.provider}
            onChange={onProviderChange}
            options={[
              { value: "openai", label: LLM_PROVIDER_PRESETS.openai.label },
              { value: "glm", label: LLM_PROVIDER_PRESETS.glm.label },
              { value: "deepseek", label: LLM_PROVIDER_PRESETS.deepseek.label },
              { value: "qwen", label: LLM_PROVIDER_PRESETS.qwen.label },
              { value: "anthropic", label: LLM_PROVIDER_PRESETS.anthropic.label },
              { value: "custom", label: "自定义" },
            ]}
          />
          <Typography.Text>API Key</Typography.Text>
          <Input.Password
            value={llmConfig.apiKey}
            onChange={(event) =>
              setLlmConfig((prev) => ({
                ...prev,
                apiKey: event.target.value,
              }))
            }
            placeholder="输入你的 API Key（本地模型可留空）"
          />
          <Typography.Text>Base URL</Typography.Text>
          <Input
            value={llmConfig.baseUrl}
            onChange={(event) =>
              setLlmConfig((prev) => ({
                ...prev,
                baseUrl: event.target.value,
              }))
            }
            placeholder="例如 https://api.openai.com/v1"
          />
          <Typography.Text>模型名</Typography.Text>
          <Input
            value={llmConfig.model}
            onChange={(event) =>
              setLlmConfig((prev) => ({
                ...prev,
                model: event.target.value,
              }))
            }
            placeholder="例如 gpt-4o-mini"
          />
        </Space>
      </Modal>
    </div>
  );
}
