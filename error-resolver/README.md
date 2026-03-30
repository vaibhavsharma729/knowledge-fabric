# Error Resolver

AI-powered error analysis and step-by-step resolution — built as an **MCP server** so it works directly inside **GitHub Copilot Chat** in VS Code.

No hosting, no web UI needed. Just open Copilot Chat, paste an error (or attach a screenshot), and get a full resolution.

## How it works

```
VS Code Copilot Chat
        │  (stdio MCP)
        ▼
┌──────────────────────┐
│  mcp_server.py       │  ← local MCP server
│  (3 tools exposed)   │
└──┬───────────────────┘
   │
   ├── resolve_error ──────────────────────────────────────────────────┐
   │       │                                                            │
   │  Web search (Tavily)   GitHub repo search   Oracle DB error logs  │
   │       │                      │                      │             │
   │       └──────────────────────┴──────────────────────┘             │
   │                              │                                     │
   │                    gpt-4o via GitHub Models API                    │
   │                              │                                     │
   │                    Step-by-step resolution ◄───────────────────────┘
   │
   ├── search_github_code   (standalone repo search)
   └── query_error_logs     (standalone Oracle DB lookup)
```

## Features

- **Paste an error or attach a screenshot** — gpt-4o vision reads screenshots automatically
- **Web research** — Tavily searches for known solutions
- **GitHub repo search** — scans your repository for code related to the error
- **Oracle DB logs** — queries historical `APP_ERROR_LOGS` for matching errors
- **Step-by-step fix** — AI synthesizes everything into an actionable resolution

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the GitHub MCP server subprocess)
- VS Code with the **GitHub Copilot** extension
- A GitHub account with Copilot access (individual or org subscription)
- GitHub Personal Access Token with `models:read` + `repo` scopes
- AWS RDS Oracle instance (optional — for DB error log context)

## Setup

### 1. Install Python dependencies

```bash
cd error-resolver
pip install -r requirements.txt
```

### 2. Install Node.js (for GitHub MCP server)

```bash
# macOS
brew install node

# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and set your values. Minimum required for local dev:

```bash
GITHUB_PAT=ghp_xxxx                  # GitHub PAT — models:read + repo scopes
GITHUB_REPO_OWNER=your-org-or-username
GITHUB_REPO_NAME=your-repository

# Optional — web search (get a free key at tavily.com)
# TAVILY_API_KEY=tvly-xxxx

# Optional — Oracle DB (leave blank to skip)
# ORACLE_HOST=your-instance.xxxx.rds.amazonaws.com
```

> **Note**: For AWS-based deployments you can use AWS Secrets Manager instead of setting secrets in `.env`. See the comments in `.env.example` for details.

### 4. Connect the MCP server to VS Code Copilot Chat

The file `.vscode/mcp.json` at the workspace root already configures VS Code to run this MCP server. It is picked up automatically when you open the workspace.

**Verify it is active:**
1. Open VS Code
2. Open the Copilot Chat panel (`Ctrl+Alt+I` / `Cmd+Alt+I`)
3. Click the **Tools** icon (plug/wrench) — you should see `error-resolver` listed with its three tools

### 5. Use it

In Copilot Chat, simply describe your error:

```
Fix this error: NullPointerException in UserService.java line 142
```

Or attach a screenshot of the error and ask:

```
What's wrong in this screenshot and how do I fix it?
```

Copilot will call the `resolve_error` tool automatically and return a full resolution.

## MCP Tools

The MCP server (`mcp_server.py`) exposes three tools to Copilot Chat:

| Tool | What it does |
|------|-------------|
| `resolve_error` | Full pipeline: web search + GitHub code search + Oracle DB + gpt-4o resolution |
| `search_github_code` | Standalone search of your GitHub repo for code related to keywords |
| `query_error_logs` | Standalone query of Oracle `APP_ERROR_LOGS` table for matching errors |

### How Copilot picks the right tool

Copilot reads the tool descriptions and decides which to call based on your question:
- Paste a stack trace → `resolve_error`
- "Show me the code for UserService" → `search_github_code`
- "Have we seen this error before in prod?" → `query_error_logs`

## Internal GitHub MCP Server

The `resolve_error` tool internally uses the
[GitHub MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/github)
as a subprocess to search your repository. The configuration is in `.mcp.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PAT}"
      }
    }
  }
}
```

## Oracle DB Schema

The app queries a table named `APP_ERROR_LOGS` by default. Adjust the table name
in `oracle_client.py → get_recent_error_logs()` to match your schema.

Expected columns:

| Column        | Type          | Description                     |
|---------------|---------------|---------------------------------|
| ERROR_ID      | NUMBER        | Primary key                     |
| ERROR_CODE    | VARCHAR2(50)  | Application error code          |
| ERROR_MESSAGE | VARCHAR2(4000)| Error message text              |
| STACK_TRACE   | CLOB          | Full stack trace                |
| CREATED_AT    | TIMESTAMP     | When the error occurred         |
| MODULE_NAME   | VARCHAR2(200) | Application module              |
| USER_ID       | VARCHAR2(100) | User who triggered the error    |

## AI Engine — GitHub Models API

`error_analyzer.py` calls gpt-4o through the **GitHub Models API** —
an OpenAI-compatible endpoint authenticated with your GitHub PAT:

```
POST https://models.inference.ai.azure.com/chat/completions
Authorization: Bearer <GITHUB_PAT>
Model: gpt-4o
```

- **Text errors** → sends error text directly
- **Screenshots** → gpt-4o vision reads the image (base64-encoded)
- No Azure subscription or separate OpenAI account required

### Available models

| Model | Supports images | Notes |
|-------|----------------|-------|
| `gpt-4o` | Yes | Best for screenshots; default |
| `gpt-4o-mini` | Yes | Faster / lower rate-limit usage |
| `o1` | No | Best for complex reasoning errors |

Change the model via `COPILOT_MODEL` in `.env`.

## File Structure

```
knowledge-fabric/
├── .vscode/
│   └── mcp.json             # VS Code MCP server config (Copilot Chat integration)
└── error-resolver/
    ├── mcp_server.py        # MCP server — exposes tools to Copilot Chat
    ├── error_analyzer.py    # gpt-4o analysis engine (extract + resolve)
    ├── github_client.py     # GitHub MCP server subprocess client
    ├── oracle_client.py     # AWS RDS Oracle client
    ├── web_search.py        # Tavily web search client
    ├── config.py            # Configuration (env vars + Secrets Manager)
    ├── secrets.py           # AWS Secrets Manager loader
    ├── requirements.txt     # Python dependencies
    ├── .mcp.json            # Internal GitHub MCP server config
    ├── .env.example         # Environment variable template
    └── README.md            # This file
```
