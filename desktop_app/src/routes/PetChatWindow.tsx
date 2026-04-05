import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Button, Input, Space, Typography } from "antd";

type ChatMessage = { role: "user" | "agent"; content: string };
const DEFAULT_CHAT_MESSAGE: ChatMessage = {
  role: "agent",
  content: "可让我在绑定目录内读取/修改文件。建议描述：文件路径 + 修改目标。",
};

export function PetChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([DEFAULT_CHAT_MESSAGE]);
  const [input, setInput] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lastSyncedMessagesRef = useRef<string>("");

  useEffect(() => {
    document.body.classList.add("pet-route-body", "pet-chat-body");
    return () => {
      document.body.classList.remove("pet-route-body", "pet-chat-body");
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
    if (!window.petChatApi || typeof window.petChatApi.getChatHistory !== "function") {
      return;
    }

    let unsubscribe: (() => void) | null = null;

    const hydrateHistory = async () => {
      const history = (await window.petChatApi.getChatHistory()) as ChatMessage[] | undefined;
      if (Array.isArray(history) && history.length > 0) {
        lastSyncedMessagesRef.current = JSON.stringify(history);
        setMessages(history);
      } else {
        lastSyncedMessagesRef.current = JSON.stringify([DEFAULT_CHAT_MESSAGE]);
        void window.petChatApi.setChatHistory([DEFAULT_CHAT_MESSAGE]);
      }
    };

    if (typeof window.petChatApi.subscribeChatHistory === "function") {
      unsubscribe = window.petChatApi.subscribeChatHistory((history: unknown) => {
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

  const sendMessage = async () => {
    const text = input.trim();
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

  return (
    <div className="pet-chat-root">
      <header className="pet-chat-header">
        <div className="pet-chat-header-info">
          <div className="pet-chat-title">
            <span className="pet-chat-title-emoji">🤖</span>
            <Typography.Text strong>桌宠对话框</Typography.Text>
          </div>
          <Typography.Text className="pet-chat-dir">目录：{workspaceDir || "未绑定"}</Typography.Text>
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
            {message.content}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      <div className="pet-chat-input">
        <Input.TextArea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="例如：把 src/main.ts 中标题改为 智能报销助手"
          autoSize={{ minRows: 3, maxRows: 5 }}
        />
        <Space className="pet-chat-actions" size={8}>
          <Button onClick={() => void onBind()}>选择目录</Button>
          <Button onClick={() => void onOpenPanel()}>打开功能面板</Button>
          <Button type="primary" onClick={() => void sendMessage()}>
            发送
          </Button>
        </Space>
      </div>
    </div>
  );
}
