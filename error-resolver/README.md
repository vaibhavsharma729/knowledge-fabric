# Error Resolver

AI-powered error analysis and step-by-step resolution tool.

## Features

- **Screenshot or text input** — paste an error/stack trace or upload a screenshot
- **GitHub MCP Server** — searches your repository for code context relevant to the error
- **AWS RDS Oracle** — queries your Oracle DB error logs for historical occurrences
- **GitHub Copilot (GitHub Models API)** — multimodal AI (gpt-4o) that synthesizes all context and generates step-by-step fixes
- **Downloadable report** — export the resolution as JSON

## Architecture

```
User Input (text or screenshot)
        │
        ▼
┌───────────────────┐
│  Streamlit UI     │ ◄─── app.py
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Error Analyzer   │ ◄─── error_analyzer.py
│  (GitHub Copilot) │
└──┬────────────────┘
   │
   ├──────────────────────────────────────┐
   ▼                                      ▼
┌──────────────────┐          ┌───────────────────────┐
│  GitHub MCP      │          │  Oracle RDS Client    │
│  Server Client   │          │  (python-oracledb)    │
│  github_client.py│          │  oracle_client.py     │
└──────────────────┘          └───────────────────────┘
         │                                │
         ▼                                ▼
  GitHub API (via            AWS RDS Oracle DB
  MCP server subprocess)     (APP_ERROR_LOGS table)
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the GitHub MCP server)
- GitHub Personal Access Token with `models:read` + `repo:read` scopes
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

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 4. Enable GitHub Models access

1. Sign in to github.com with a Copilot-enabled account (individual or org)
2. Create a PAT at **Settings → Developer settings → Personal access tokens**
3. Grant scopes: `models:read` (for Copilot API) and `repo` (for MCP server)
4. Set `GITHUB_PAT` in your `.env` file

### 5. Run the application

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## GitHub MCP Server

The app uses the [GitHub MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/github)
to search your repository for code context.

The MCP server configuration is in `.mcp.json`:

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

The server is launched as a subprocess when GitHub context is requested.

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

## GitHub Copilot — How It's Used

### As the AI engine (GitHub Models API)

`error_analyzer.py` calls GitHub Copilot through the **GitHub Models API** —
an OpenAI-compatible endpoint that uses your GitHub PAT for authentication:

```
POST https://models.inference.ai.azure.com/chat/completions
Authorization: Bearer <GITHUB_PAT>
Model: gpt-4o
```

- **Text errors** → sends the error text in a chat message
- **Screenshot errors** → encodes the image as base64 and uses gpt-4o's vision capability
- No Azure subscription or OpenAI account needed — just a GitHub PAT

### Available models

| Model | Supports images | Notes |
|-------|----------------|-------|
| `gpt-4o` | Yes | Best for screenshots; default |
| `gpt-4o-mini` | Yes | Faster / cheaper |
| `o1` | No | Best reasoning for complex errors |

Change the model via `COPILOT_MODEL` in `.env` or the sidebar.

## File Structure

```
error-resolver/
├── app.py               # Streamlit UI
├── error_analyzer.py    # Bedrock Claude analysis engine
├── github_client.py     # GitHub MCP server client
├── oracle_client.py     # AWS RDS Oracle client
├── config.py            # Configuration (env vars)
├── requirements.txt     # Python dependencies
├── .mcp.json            # MCP server configuration
├── .env.example         # Environment variable template
└── README.md            # This file
```
