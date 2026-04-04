export type AgentChatResponse = {
  ok: boolean;
  reply?: string;
  report_json?: Record<string, unknown>;
  report_markdown?: string;
  mode?: "llm" | "task";
  task_type?: "qa" | "reimburse" | "final_account" | "budget";
  task_result?: Record<string, unknown>;
  task_progress?: Array<Record<string, unknown>>;
  error?: string;
};

export type AgentChatStreamEvent =
  | { chatId: string; type: "delta"; delta: string }
  | { chatId: string; type: "status"; status: string }
  | { chatId: string; type: "done"; response: unknown }
  | { chatId: string; type: "error"; error: string };

export type ChatMessage = {
  role: "user" | "agent";
  content: string;
  status?: string;
};
