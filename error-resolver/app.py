"""
Error Resolver — Streamlit Application

Upload an error screenshot or paste error text to get AI-powered,
step-by-step resolution backed by your GitHub source code and Oracle DB logs.
"""
import logging
import os
from io import BytesIO
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from config import AppConfig
from error_analyzer import ErrorAnalyzer, ResolutionResult
from github_client import GitHubMCPClient
from oracle_client import OracleClient
from web_search import WebSearchClient

load_dotenv()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Error Resolver",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Session state helpers
# ------------------------------------------------------------------

def _init_state():
    defaults = {
        "config": None,
        "analyzer": None,
        "github_client": None,
        "oracle_client": None,
        "web_search_client": None,
        "oracle_connected": False,
        "resolution": None,
        "history": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _build_clients(cfg: AppConfig):
    st.session_state.config = cfg
    st.session_state.analyzer = ErrorAnalyzer(cfg.copilot)
    st.session_state.web_search_client = WebSearchClient(tavily_api_key=cfg.tavily_api_key)
    if cfg.github.personal_access_token:
        st.session_state.github_client = GitHubMCPClient(cfg.github)
    if cfg.oracle.host:
        oc = OracleClient(cfg.oracle)
        connected = oc.connect()
        st.session_state.oracle_client = oc
        st.session_state.oracle_connected = connected


# ------------------------------------------------------------------
# Sidebar — configuration
# ------------------------------------------------------------------

def _render_sidebar():
    st.sidebar.title("Configuration")

    with st.sidebar.expander("GitHub Copilot", expanded=True):
        st.caption(
            "Uses the GitHub Models API (OpenAI-compatible). "
            "Your GitHub PAT is shared with the MCP server below."
        )
        copilot_model = st.text_input(
            "Model",
            value=os.environ.get("COPILOT_MODEL", "gpt-4o"),
            key="copilot_model",
            help="gpt-4o supports screenshot analysis. Use gpt-4o-mini to reduce cost.",
        )
        copilot_endpoint = st.text_input(
            "Endpoint",
            value=os.environ.get(
                "COPILOT_ENDPOINT", "https://models.inference.ai.azure.com"
            ),
            key="copilot_endpoint",
        )

    with st.sidebar.expander("Web Search", expanded=False):
        st.caption(
            "Used to research the error before looking at your codebase. "
            "DuckDuckGo is used by default (free). "
            "Add a Tavily key for richer AI-optimised results."
        )
        tavily_key = st.text_input(
            "Tavily API Key (optional)",
            value=os.environ.get("TAVILY_API_KEY", ""),
            type="password",
            key="tavily_key",
            help="Leave blank to use DuckDuckGo (free, no key needed).",
        )

    with st.sidebar.expander("GitHub (MCP Server + Copilot)", expanded=True):
        aws_secret_github = st.text_input(
            "AWS Secret Name",
            value=os.environ.get("AWS_SECRET_GITHUB", "error-resolver/github"),
            key="aws_secret_github",
            help="Secrets Manager secret containing {\"pat\": \"ghp_xxx\"}. "
                 "Leave blank to use the GITHUB_PAT OS environment variable.",
        )
        github_owner = st.text_input(
            "Repo Owner / Org",
            value=os.environ.get("GITHUB_REPO_OWNER", ""),
            key="github_owner",
        )
        github_repo = st.text_input(
            "Repository Name",
            value=os.environ.get("GITHUB_REPO_NAME", ""),
            key="github_repo",
        )

    with st.sidebar.expander("Oracle RDS (AWS)", expanded=False):
        aws_secret_oracle = st.text_input(
            "AWS Secret Name",
            value=os.environ.get("AWS_SECRET_ORACLE", "error-resolver/oracle"),
            key="aws_secret_oracle",
            help="Secrets Manager secret containing {\"username\": \"...\", \"password\": \"...\"}. "
                 "Leave blank to use ORACLE_USERNAME / ORACLE_PASSWORD OS environment variables.",
        )
        oracle_host = st.text_input(
            "RDS Endpoint",
            value=os.environ.get("ORACLE_HOST", ""),
            key="oracle_host",
            placeholder="mydb.xxxx.rds.amazonaws.com",
        )
        oracle_port = st.text_input(
            "Port", value=os.environ.get("ORACLE_PORT", "1521"), key="oracle_port"
        )
        oracle_svc = st.text_input(
            "Service Name",
            value=os.environ.get("ORACLE_SERVICE_NAME", ""),
            key="oracle_svc",
        )

    if st.sidebar.button("Connect / Refresh", use_container_width=True):
        os.environ["COPILOT_MODEL"] = copilot_model
        os.environ["COPILOT_ENDPOINT"] = copilot_endpoint
        os.environ["AWS_SECRET_GITHUB"] = aws_secret_github
        os.environ["GITHUB_REPO_OWNER"] = github_owner
        os.environ["GITHUB_REPO_NAME"] = github_repo
        os.environ["TAVILY_API_KEY"] = tavily_key
        os.environ["AWS_SECRET_ORACLE"] = aws_secret_oracle
        os.environ["ORACLE_HOST"] = oracle_host
        os.environ["ORACLE_PORT"] = oracle_port
        os.environ["ORACLE_SERVICE_NAME"] = oracle_svc

        cfg = AppConfig.from_env()
        with st.spinner("Connecting..."):
            _build_clients(cfg)
        st.sidebar.success("Clients initialized.")
        if st.session_state.oracle_connected:
            st.sidebar.success("Oracle DB connected.")
        elif oracle_host:
            st.sidebar.warning("Oracle DB connection failed. Check credentials.")

    # Status indicators
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Status**")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.session_state.analyzer:
            st.success("Copilot ✓")
        else:
            st.info("Copilot –")
    with col2:
        if st.session_state.github_client:
            st.success("GitHub ✓")
        else:
            st.info("GitHub –")

    col3, col4 = st.sidebar.columns(2)
    with col3:
        if st.session_state.oracle_connected:
            st.success("Oracle ✓")
        else:
            st.info("Oracle –")
    with col4:
        pass

    # History
    if st.session_state.history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Recent Analyses**")
        for i, h in enumerate(reversed(st.session_state.history[-5:])):
            if st.sidebar.button(f"{h['error_type']} — {h['confidence']}", key=f"hist_{i}"):
                st.session_state.resolution = h["result"]


# ------------------------------------------------------------------
# Main content
# ------------------------------------------------------------------

def _render_input_section():
    st.title("Error Resolver")
    st.markdown(
        "Upload an error screenshot **or** paste error text. "
        "The AI will identify the root cause and provide step-by-step resolution "
        "using your GitHub source code and Oracle database logs as context."
    )

    input_tab, settings_tab = st.tabs(["Analyze Error", "Advanced Options"])

    with input_tab:
        input_mode = st.radio(
            "Input type",
            ["Paste Error Text", "Upload Screenshot"],
            horizontal=True,
        )

        error_text: Optional[str] = None
        image_bytes: Optional[bytes] = None
        image_media_type: str = "image/png"

        if input_mode == "Paste Error Text":
            error_text = st.text_area(
                "Error Message / Stack Trace",
                height=250,
                placeholder="Paste your full error message or stack trace here...",
            )
        else:
            uploaded = st.file_uploader(
                "Upload error screenshot",
                type=["png", "jpg", "jpeg", "webp", "gif"],
                help="Supports PNG, JPG, JPEG, WebP, GIF",
            )
            if uploaded:
                image_bytes = uploaded.read()
                image_media_type = uploaded.type or "image/png"
                img = Image.open(BytesIO(image_bytes))
                st.image(img, caption="Uploaded screenshot", use_column_width=True)

        # Options row
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            use_web = st.checkbox(
                "Search web for error context",
                value=True,
                help="Research the error online before looking at your code.",
            )
        with col_b:
            use_github = st.checkbox(
                "Search GitHub repository",
                value=bool(st.session_state.github_client),
                disabled=not bool(st.session_state.github_client),
                help="Find where the error occurs in your application code.",
            )
        with col_c:
            use_oracle = st.checkbox(
                "Query Oracle DB logs",
                value=st.session_state.oracle_connected,
                disabled=not st.session_state.oracle_connected,
                help="Check historical error occurrences in your RDS database.",
            )

        if st.button("Analyze & Resolve", type="primary", use_container_width=True):
            if not st.session_state.analyzer:
                st.error(
                    "GitHub Copilot client not initialized. "
                    "Add your GitHub PAT in the sidebar and click **Connect / Refresh**."
                )
                return

            if not error_text and not image_bytes:
                st.warning("Please provide an error message or screenshot.")
                return

            _run_analysis(
                error_text=error_text,
                image_bytes=image_bytes,
                image_media_type=image_media_type,
                use_web=use_web,
                use_github=use_github,
                use_oracle=use_oracle,
            )

    with settings_tab:
        st.markdown("### MCP Server Configuration")
        st.markdown(
            "The GitHub MCP server is launched automatically when GitHub context is enabled. "
            "It requires **Node.js** and runs: `npx -y @modelcontextprotocol/server-github`"
        )
        mcp_json_path = os.path.join(os.path.dirname(__file__), ".mcp.json")
        if os.path.exists(mcp_json_path):
            with open(mcp_json_path) as f:
                st.code(f.read(), language="json")

        st.markdown("### Environment Variables")
        st.markdown(
            "You can also configure the app via a `.env` file in this directory. "
            "See `.env.example` for all supported variables."
        )


def _run_analysis(
    error_text: Optional[str],
    image_bytes: Optional[bytes],
    image_media_type: str,
    use_web: bool,
    use_github: bool,
    use_oracle: bool,
):
    analyzer: ErrorAnalyzer = st.session_state.analyzer
    web_client: Optional[WebSearchClient] = st.session_state.web_search_client
    github_client: Optional[GitHubMCPClient] = st.session_state.github_client
    oracle_client: Optional[OracleClient] = st.session_state.oracle_client

    with st.status("Analyzing error...", expanded=True) as status:

        # ── Step 1: Extract error info from text or screenshot ──────────
        st.write("**Step 1/4** — Extracting error details from input...")
        if image_bytes:
            error_info = analyzer.extract_error_info_from_image(image_bytes, image_media_type)
        else:
            error_info = analyzer.extract_error_info_from_text(error_text)

        label = error_info.error_type
        if error_info.error_code:
            label += f" ({error_info.error_code})"
        st.write(f"Identified: **{label}**")

        # ── Step 2: Web search — understand the error before touching code ──
        web_context = ""
        if use_web and web_client:
            st.write("**Step 2/4** — Researching error on the web...")
            web_result = web_client.research_error(
                error_type=error_info.error_type,
                error_message=error_info.error_message,
                error_code=error_info.error_code,
                stack_trace=error_info.stack_trace,
            )
            web_context = web_result.formatted
            st.write(f"Found {len(web_result.results)} web sources.")
        else:
            st.write("**Step 2/4** — Web search skipped.")

        # ── Step 3: GitHub — find where the error lives in the codebase ──
        github_context = ""
        if use_github and github_client:
            st.write("**Step 3/4** — Deriving repository search terms...")
            # Let Copilot pick smarter terms informed by web knowledge
            search_terms = analyzer.derive_repo_search_terms(error_info, web_context)
            st.write(f"Searching GitHub for: `{', '.join(search_terms[:4])}`...")
            github_context = github_client.get_relevant_code_context(search_terms)
            st.write(f"Retrieved {len(github_context)} characters of repository code.")
        else:
            st.write("**Step 3/4** — GitHub search skipped.")

        # ── Step 4 (optional): Oracle DB error logs ──────────────────────
        db_context = ""
        if use_oracle and oracle_client:
            st.write("**Step 4/4** — Querying Oracle DB for error logs...")
            db_context = oracle_client.get_db_context_for_error(error_info.keywords)
            st.write("Database context retrieved.")
        else:
            st.write("**Step 4/4** — Oracle DB query skipped.")

        # ── Generate resolution ───────────────────────────────────────────
        st.write("Synthesising resolution with GitHub Copilot...")
        resolution = analyzer.generate_resolution(
            error_info=error_info,
            web_context=web_context,
            github_context=github_context,
            db_context=db_context,
        )

        status.update(label="Analysis complete!", state="complete", expanded=False)

    # Store result
    st.session_state.resolution = resolution
    st.session_state.history.append(
        {
            "error_type": error_info.error_type,
            "confidence": resolution.confidence,
            "result": resolution,
        }
    )


# ------------------------------------------------------------------
# Resolution display
# ------------------------------------------------------------------

def _render_resolution(result: ResolutionResult):
    st.markdown("---")
    st.subheader("Analysis Results")

    # Error summary card
    ei = result.error_info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Error Type", ei.error_type or "Unknown")
    with col2:
        st.metric("Error Code", ei.error_code or "—")
    with col3:
        confidence_color = {"high": "green", "medium": "orange", "low": "red"}.get(
            result.confidence, "grey"
        )
        st.markdown(
            f"**Confidence:** :{confidence_color}[{result.confidence.upper()}]"
        )

    if ei.error_message:
        st.info(f"**Error Message:** {ei.error_message}")

    if ei.stack_trace:
        with st.expander("Stack Trace"):
            st.code(ei.stack_trace, language="text")

    # Root cause
    st.markdown("### Root Cause")
    st.markdown(result.root_cause or "_Not determined._")

    # Resolution steps
    st.markdown("### Resolution Steps")
    if result.resolution_steps:
        for i, step in enumerate(result.resolution_steps, 1):
            st.markdown(f"**{i}.** {step}")
    else:
        st.warning("No resolution steps generated.")

    # Code references
    if result.code_references:
        st.markdown("### Code References")
        for ref in result.code_references:
            st.markdown(f"- `{ref}`")

    # Prevention tips
    if result.prevention_tips:
        st.markdown("### Prevention Tips")
        for tip in result.prevention_tips:
            st.markdown(f"- {tip}")

    # Web sources used
    if result.web_sources:
        st.markdown("### Web Sources Referenced")
        for url in result.web_sources:
            st.markdown(f"- {url}")

    # Download
    import json as _json

    report = _json.dumps(
        {
            "error_type": ei.error_type,
            "error_code": ei.error_code,
            "error_message": ei.error_message,
            "root_cause": result.root_cause,
            "resolution_steps": result.resolution_steps,
            "code_references": result.code_references,
            "prevention_tips": result.prevention_tips,
            "web_sources": result.web_sources,
            "confidence": result.confidence,
        },
        indent=2,
    )
    st.download_button(
        "Download Report (JSON)",
        data=report,
        file_name="error_resolution_report.json",
        mime="application/json",
    )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    _init_state()

    # No auto-init on startup — avoids blocking on Secrets Manager / Oracle calls.
    # Use the "Connect / Refresh" button in the sidebar to initialize clients.

    _render_sidebar()
    _render_input_section()

    if st.session_state.resolution:
        _render_resolution(st.session_state.resolution)


if __name__ == "__main__":
    main()
