# Error Resolver

AI-powered error analysis and step-by-step resolution tool.

## Features

- **Screenshot or text input** — paste an error/stack trace or upload a screenshot
- **GitHub MCP Server** — searches your repository for code context relevant to the error
- **AWS RDS Oracle** — queries your Oracle DB error logs for historical occurrences
- **AWS Bedrock (Claude)** — multimodal AI that synthesizes all context and generates step-by-step fixes
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
│  (Bedrock Claude) │
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
- AWS account with Bedrock access (Claude 3.5 Sonnet model enabled)
- AWS RDS Oracle instance (optional)
- GitHub Personal Access Token with `repo` read scope

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

### 4. Enable Claude model in AWS Bedrock

1. Open [AWS Bedrock Console](https://console.aws.amazon.com/bedrock)
2. Go to **Model access**
3. Enable **Claude 3.5 Sonnet v2** (`anthropic.claude-3-5-sonnet-20241022-v2:0`)

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

## GitHub Copilot Integration

This project is designed to work well with **GitHub Copilot**:

1. Open the project in VS Code or JetBrains with the GitHub Copilot extension
2. Copilot provides inline suggestions as you extend `error_analyzer.py`,
   `github_client.py`, or `oracle_client.py`
3. Use **Copilot Chat** (`Ctrl+Shift+I`) to ask questions about the codebase
4. The `.mcp.json` file registers the GitHub MCP server for Claude Code sessions

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
