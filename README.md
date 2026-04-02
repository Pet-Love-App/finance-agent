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

### 接入 Paratera 云端模型
你提供的平台地址可直接接入（OpenAI 兼容接口）：

```bash
# PowerShell 示例（推荐仅在当前会话临时设置）
$env:AGENT_LLM_API_KEY="<你的真实Key>"
$env:AGENT_LLM_API_URL="https://llmapi.paratera.com"
$env:AGENT_LLM_MODEL="<平台可用模型ID>"
```

说明：
- `AGENT_LLM_API_URL` 与 `AGENT_LLM_BASE_URL` 均可使用，代码会优先读取 `BASE_URL`，否则读取 `API_URL`。
- 若地址未带 `/v1`，系统会自动补齐为 `/v1` 后再调用 `chat/completions`。
- 请不要把 Key 写入代码仓库，建议放入本地环境变量或未提交的 `.env` 文件。
- API Key 具备完整账户权限，请定期轮换并避免在日志/截图中泄露。

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

## Agent 后端架构

### 技术栈
```
- LangGraph (>=0.2.0)      # Agent 工作流框架
- Pandas (>=2.0.0)         # 数据处理
- jsonschema (>=4.0.0)     # JSON 验证
- python-docx/pptx/openpyxl # Office 文件支持
```

### 核心结构
```
agent/                          # 核心 Agent 模块
├── state.py                    # LangGraph 状态定义
├── schemas.py                  # JSON Schema + 类目同义词映射
├── graph_builder.py            # LangGraph 流程图构建
├── nodes.py                    # 5 个处理节点的实现
├── utils.py                    # 通用工具函数
├── sample_data.py              # 示例测试数据
│
├── kb/                         # 知识库模块
│   ├── retriever.py           # 知识库检索（文本相似度）
│   └── ingest.py              # 知识库数据导入

agent.py                        # 主入口脚本

data/kb/
└── reimbursement_kb.json      # 知识库存储文件
```

### 工作流程（5 阶段管道）

```
输入数据 → Data_Extraction → Category_Alignment → Consistency_Check 
       → Compliance_Audit → Report_Generator → JSON/Markdown 报告
```

#### 各节点职责

| 节点 | 功能 | 输出 |
|------|------|------|
| **Data_Extraction** | 加载、验证、标准化预算/决算数据 | DataFrame + 规范化数据 |
| **Category_Alignment** | 用模糊匹配把决算支出映射到预算类目 | matched_category 字段 |
| **Consistency_Check** | 检查超支/无法匹配的项目 | discrepancies + suggestions |
| **Compliance_Audit** | 餐饮/会议类特殊审计规则 | 高风险项标记 |
| **Report_Generator** | 生成 JSON 和 Markdown 报告 | 完整审计报告 |

### 状态流转（AgentState）

```python
AgentState {
  # 输入
  budget_source → actual_source
  
  # 中间处理
  budget_data, actual_data      # 规范化列表
  budget_df, actual_df           # Pandas 数据框
  
  # 输出
  discrepancies → [{type, risk, message, details}]
  suggestions → [建议文本]
  extraction_warnings → [提取警告]
  report → {report_json, report_markdown}
}
```

### 核心特点

- ✅ **流程化** - LangGraph 声明式管道
- ✅ **有状态** - TypedDict 状态贯穿全程
- ✅ **可验证** - 严格的 JSON Schema 校验
- ✅ **智能匹配** - 支持类目别名和模糊匹配
- ✅ **双格式输出** - JSON + Markdown 报告
- ✅ **可扩展** - 知识库支持自定义规则

## 知识库（RAG）
若你已将报销制度文档放入 `docs/reimbursement`，可先构建本地知识库索引：

```bash
# 在项目根目录执行
python -m agent.kb.ingest --source docs/reimbursement --output data/kb/reimbursement_kb.json
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

### RAG Trace（JSONL）
可选开启 RAG 评估输入记录（默认开启），用于离线评估：

```bash
# 是否写入 RAG trace（默认 1）
AGENT_RAG_TRACE_ENABLED=1

# 输出目录（默认 data/eval/traces）
AGENT_RAG_TRACE_DIR=./data/eval/traces
```

输出文件按天分片，例如：

```text
data/eval/traces/rag_trace_20260402.jsonl
```

每行一条 JSON 记录，核心字段包含：
- `request_id`
- `timestamp`
- `status`（`ok`/`error`）
- `question`
- `contexts[]`（`source/title/content/score`）
- `answer`
- `latency_ms`
- `mode`（`llm_sync`/`llm_stream`）
- `error`（仅错误态）

## Agent 审计配置
可通过环境变量做“策略参数化”，避免把规则阈值硬编码在代码里：

```bash
# 单类目超支阈值（默认 0.10）
AGENT_CATEGORY_OVERRUN_THRESHOLD=0.10

# 高风险标签（默认 High Risk）
AGENT_HIGH_RISK_LABEL=High Risk

# 特殊审计类目关键字，英文逗号分隔（默认 餐饮,会议）
AGENT_SPECIAL_EXPENSE_KEYWORDS=餐饮,会议
```

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
