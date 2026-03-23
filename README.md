# Electron 模板实时预览（MVP）

## 功能
- 选择 `xlsx/xls/docx` 模板文件。
- 实时监听文件保存并自动刷新预览。
- Excel 以表格预览，Word 以文本段落预览。

## 运行
```bash
cd desktop_app
npm install
npm run dev
```

## Agent 自由问答（可选）
默认可使用内置规则问答和审计触发；若要启用自由问答（LLM），请在启动 Electron 前配置环境变量：

```bash
# PowerShell 示例
$env:AGENT_LLM_API_KEY="你的Key"
$env:AGENT_LLM_MODEL="gpt-4o-mini"
# 可选，默认 https://api.openai.com/v1
$env:AGENT_LLM_BASE_URL="https://api.openai.com/v1"
# 可选，默认 60 秒
$env:AGENT_LLM_TIMEOUT="60"
```

说明：
- 未设置 `AGENT_LLM_API_KEY` 时，系统继续走本地规则回复，不会调用云端模型。
- 设置后，普通对话会进入 LLM 自由问答；`sample/示例/demo` 和传入审计 payload 仍优先走审计流程。

### 使用 LM Studio（本地模型）
LM Studio 默认提供 OpenAI 兼容接口，可直接接入：

```bash
# PowerShell 示例
$env:AGENT_LLM_BASE_URL="http://127.0.0.1:1234/v1"
$env:AGENT_LLM_MODEL="google/gemma-3-4b"
# 本地地址可不设置 Key；若你在 LM Studio 开启了鉴权，再设置即可
# $env:AGENT_LLM_API_KEY="lm-studio"
```

也可以放到 `desktop_app/.env`（推荐）：

```bash
AGENT_LLM_BASE_URL=http://127.0.0.1:1234/v1
AGENT_LLM_MODEL=google/gemma-3-4b
```

注意：
- 请先在 LM Studio 中启动 Local Server（OpenAI Compatible）。
- 若返回模型不存在，请把 `AGENT_LLM_MODEL` 改为 LM Studio 实际显示的 model id。

## 知识库（RAG）
若你已将报销制度文档放入 `docs/reimbursement`，可先构建本地知识库索引：

```bash
# 在项目根目录执行
python -m reimbursement_agent.kb.ingest --source docs/reimbursement --output data/kb/reimbursement_kb.json
```

然后在 `desktop_app/.env` 增加（可选，默认已指向该路径）：

```bash
AGENT_KB_PATH=../data/kb/reimbursement_kb.json
AGENT_KB_TOP_K=4
AGENT_KB_MAX_CHARS=1800
```

说明：
- 聊天时会先检索知识库片段，再交给 LLM 生成答案。
- 文档更新后，重新执行一次 `ingest` 命令即可刷新知识库。

## 目录
- `electron/main.ts`：Electron 主进程、IPC、文件监听。
- `electron/preload.ts`：安全桥接 API。
- `electron/templateParser.ts`：模板解析逻辑。
- `src/App.tsx`：交互入口与状态管理。
- `src/components/PreviewPanel.tsx`：预览区渲染。

## 可扩展建议
- 增加 PDF/image 附件预览组件。
- 将 `parseTemplate` 迁移到 worker_threads 提升大文件性能。
- 为预览数据增加 JSON Schema 版本控制。
