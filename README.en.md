# Finance Reimbursement Agent

An intelligent, local-first desktop assistant for reimbursement workflows, built with `LangGraph`, document parsers, rule-based QA, knowledge retrieval, template preview, and a secure sandbox subsystem.

[简体中文](./README.md) | English

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=node.js&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-Desktop_App-47848F?logo=electron&logoColor=white)
![React](https://img.shields.io/badge/React-18%2B-61DAFB?logo=react&logoColor=black)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent_Workflow-121212)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)

## Quick Links

- [Contributing](./CONTRIBUTING.md)
- [Changelog](./CHANGELOG.md)
- [Chinese README](./README.md)

## Table of Contents

- [Highlights](#highlights)
- [Screenshots](#screenshots)
- [Use Cases](#use-cases)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [FAQ](#faq)
- [Testing](#testing)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)

## Highlights

- `Desktop UI`: built with `Electron + React + Vite`, including the app panel, template preview, and bridge layer.
- `Workflow Agent`: built with `Python + LangGraph` to orchestrate QA, reimbursement, budgeting, and reporting flows.
- `Local-first`: knowledge base, database, generated files, and audit logs stay on local storage.
- `Multi-format parsing`: supports `Word / Excel / PDF / images / Markdown / HTML / PPT`.
- `Optional LLM integration`: runs with local rules only, or connects to OpenAI-compatible model endpoints.
- `Secure sandbox`: supports code scanning, isolated execution, and audit logging.

## Screenshots

> No official product screenshots are committed to the repository yet. You can place images under `docs/images/` and replace the placeholders below.

| Module | Description | Suggested file |
| --- | --- | --- |
| Dashboard | Main desktop panel and task entry points | `docs/images/dashboard.png` |
| Template Preview | Real-time preview for `docx/xlsx` templates | `docs/images/preview.png` |
| Desktop Pet | Floating pet window, bubble messages, drag-and-drop entry | `docs/images/pet.png` |
| QA or Report | Rule QA, audit output, or generated report view | `docs/images/qa-or-report.png` |

Example usage after screenshots are added:

```md
![Dashboard](docs/images/dashboard.png)
![Preview](docs/images/preview.png)
```

## Use Cases

- `Reimbursement QA`: answer policy questions, document requirements, and workflow issues.
- `Single reimbursement processing`: scan materials, extract structured data, validate rules, and generate outputs.
- `Annual final accounts and budgeting`: aggregate records and generate budget/final-account outputs.
- `Template preview`: locally preview `xlsx/xls/docx` files with auto refresh on changes.
- `Secure code execution`: run scan-and-execute workflows in a restricted environment.

## Architecture

### Tech Stack

**Backend**

- `Python`
- `LangGraph`
- `pandas`
- `jsonschema`
- `openpyxl`
- `python-docx`
- `python-pptx`
- `PyMuPDF`

**Desktop**

- `Electron`
- `React`
- `TypeScript`
- `Vite`
- `Ant Design`

### Core Flow

```text
Input Data
  -> Data_Extraction
  -> Category_Alignment
  -> Consistency_Check
  -> Compliance_Audit
  -> Report_Generator
  -> JSON / Markdown Report
```

### Module Layout

```text
desktop_app/          Electron desktop app and preview UI
agent/                Agent core, graph orchestration, tools, and subsystems
data/                 Local database, knowledge base, audit logs, templates
docs/                 Sample documents, design notes, output examples
tests/                Automated tests
```

## Quick Start

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd agent
```

### 2. Install backend dependencies

Recommended: `Python 3.10+`

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start the desktop app

Recommended: `Node.js 18+`

```bash
cd desktop_app
npm install
npm run dev
```

### 4. Run backend examples

```bash
python run_v2.py
```

Or run the minimal sample flow:

```bash
python agent.py
```

## Configuration

### LLM-powered QA

By default, the project can work with local rules only. If LLM environment variables are configured, general chat can switch to an LLM-backed mode.

```bash
# PowerShell example
$env:AGENT_LLM_API_KEY="your-key"
$env:AGENT_LLM_MODEL="gpt-4o-mini"
$env:AGENT_LLM_BASE_URL="https://api.openai.com/v1"
$env:AGENT_LLM_TIMEOUT="60"
```

Notes:

- If `AGENT_LLM_API_KEY` is not set, no cloud model request is sent.
- Both `AGENT_LLM_BASE_URL` and `AGENT_LLM_API_URL` are supported.
- If `/v1` is missing, the app appends it automatically.

### Connect to Paratera

```bash
$env:AGENT_LLM_API_KEY="<your-real-key>"
$env:AGENT_LLM_API_URL="https://llmapi.paratera.com"
$env:AGENT_LLM_MODEL="<supported-model-id>"
```

### Connect to LM Studio

```bash
$env:AGENT_LLM_BASE_URL="http://127.0.0.1:1234/v1"
$env:AGENT_LLM_MODEL="google/gemma-3-4b"
```

You can also put them in `desktop_app/.env`:

```bash
AGENT_LLM_BASE_URL=http://127.0.0.1:1234/v1
AGENT_LLM_MODEL=google/gemma-3-4b
```

### Knowledge Base

If your reimbursement policy files are placed in `docs/reimbursement`, build the local KB first:

```bash
python -m agent.kb.ingest --source docs/reimbursement --output data/kb/reimbursement_kb.json
```

Then configure `desktop_app/.env`:

```bash
AGENT_KB_PATH=../data/kb/reimbursement_kb.json
AGENT_KB_TOP_K=4
AGENT_KB_MAX_CHARS=1800
```

### Graph Policy

You can control SubGraph behavior through `graph_policy` in the task payload:

```json
{
  "graph_policy": {
    "reimburse_stop_on_rule_violation": true,
    "qa_allow_empty_query": false,
    "qa_kb_top_k": 4,
    "qa_kb_score_threshold": 0.75,
    "final_generate_when_empty": true,
    "budget_skip_calculate_when_empty": true
  }
}
```

Optional environment variables:

- `AGENT_GRAPH_REIMBURSE_STOP_ON_RULE_VIOLATION`
- `AGENT_GRAPH_QA_ALLOW_EMPTY_QUERY`
- `AGENT_GRAPH_QA_KB_TOP_K`
- `AGENT_GRAPH_QA_KB_SCORE_THRESHOLD`
- `AGENT_GRAPH_FINAL_GENERATE_WHEN_EMPTY`
- `AGENT_GRAPH_BUDGET_SKIP_CALCULATE_WHEN_EMPTY`

### Audit Thresholds

```bash
AGENT_CATEGORY_OVERRUN_THRESHOLD=0.10
AGENT_HIGH_RISK_LABEL=High Risk
AGENT_SPECIAL_EXPENSE_KEYWORDS=餐饮,会议
```

## Project Structure

```text
agent/
├── core/             Dispatcher, event bus, window management
├── graphs/           Main graph and task-specific subgraphs
├── kb/               Local knowledge-base build and retrieval
├── parser/           Multi-format document parsing
├── sandbox/          Sandbox and security policies
└── tools/            Tool wrappers used by workflows

desktop_app/
├── electron/         Electron main process and preload
├── src/              React routes and components
└── agent_bridge/     Desktop-to-Python bridge layer

data/
├── audit/            Audit logs
├── db/               Local database
├── kb/               Local knowledge-base files
└── templates/        Sample templates and outputs
```

## FAQ

### 1. Can I run this project without an LLM?

Yes. The project still works with local rules and existing workflow logic when `AGENT_LLM_API_KEY` is not configured.

### 2. Can I use a local model?

Yes. Any OpenAI-compatible local endpoint, such as `LM Studio`, can be connected.

### 3. What should I do after updating knowledge-base documents?

Run the `python -m agent.kb.ingest ...` command again to rebuild the local KB.

### 4. Why are there no screenshots in the repository yet?

Because no official screenshots are currently committed. Put them in `docs/images/` and replace the placeholders in the README.

### 5. Is there an open-source license already?

No explicit `LICENSE` file is present in the repository yet. If you plan to publish it, adding one is recommended.

## Testing

The current test suite mainly uses `unittest`:

```bash
python -m unittest discover -s tests
```

## Contributing

Issues and pull requests are welcome.

Suggested workflow:

1. Fork the repository and create a feature branch.
2. Implement the change locally and run relevant tests.
3. Update documentation if config, behavior, or usage changes.
4. Open a PR with context, implementation notes, and validation details.

Before submitting, please check:

- The change matches the existing project structure.
- New configuration is documented.
- Tests cover the critical path of the change.
- Sensitive information is not committed.

## Roadmap

- Add richer attachment preview support
- Improve performance for large file parsing and background tasks
- Expand templates, rules, and workflow configuration
- Improve desktop packaging and release workflow
- Add official screenshots, demo GIFs, and release notes

## License

No explicit `LICENSE` file is included at the moment. If this project is intended for open-source release, adding a license is strongly recommended.
