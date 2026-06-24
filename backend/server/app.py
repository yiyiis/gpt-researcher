import json
import os
from typing import Dict, List, Any
import time
import logging
import sys
import warnings
from pathlib import Path

# Suppress Pydantic V2 migration warnings
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, File, UploadFile, BackgroundTasks, HTTPException
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict

# Add the parent directory to sys.path to make sure we can import from server
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from server.websocket_manager import WebSocketManager
from server.server_utils import (
    get_config_dict, sanitize_filename,
    update_environment_variables, handle_file_upload, handle_file_deletion,
    execute_multi_agents, handle_websocket_communication
)
from server.agent_discovery import build_agent_discovery_document

from server.websocket_manager import run_agent
from utils import write_md_to_word, write_md_to_pdf
from gpt_researcher.utils.enum import Tone
from chat.chat import ChatAgentWithMemory

from server.report_store import ReportStore
from server.db import WorkspaceStore
from server import migrate as migrate_module

# MongoDB services removed - no database persistence needed

# Setup logging
logger = logging.getLogger(__name__)

# Don't override parent logger settings
logger.propagate = True

# Silence uvicorn reload logs
logging.getLogger("uvicorn.supervisors.ChangeReload").setLevel(logging.WARNING)

# Models


class ResearchRequest(BaseModel):
    task: str
    report_type: str
    report_source: str
    tone: str
    headers: dict | None = None
    repo_name: str
    branch_name: str
    generate_in_background: bool = True


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # Allow extra fields in the request
    
    report: str
    messages: List[Dict[str, Any]]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs("outputs", exist_ok=True)
    app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
    
    # Mount frontend static files
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
    if os.path.exists(frontend_path):
        app.mount("/site", StaticFiles(directory=frontend_path), name="frontend")
        logger.debug(f"Frontend mounted from: {frontend_path}")
        
        # Also mount the static directory directly for assets referenced as /static/
        static_path = os.path.join(frontend_path, "static")
        if os.path.exists(static_path):
            app.mount("/static", StaticFiles(directory=static_path), name="static")
            logger.debug(f"Static assets mounted from: {static_path}")
    else:
        logger.warning(f"Frontend directory not found: {frontend_path}")
    
    logger.info("GPT Researcher API ready - local mode (no database persistence)")
    # 初始化 SQLite 工作区存储 + 迁移旧数据
    await migrate_module.migrate_if_needed(workspace_store)
    logger.info("Workspace storage ready")
    yield
    # Shutdown
    logger.info("Research API shutting down")

# App initialization
app = FastAPI(lifespan=lifespan)

# Configure allowed origins for CORS
allowed_origins_env = os.getenv("CORS_ALLOW_ORIGINS")
ALLOWED_ORIGINS = (
    [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    if allowed_origins_env
    else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://app.gptr.dev",
    ]
)

# Standard JSON response - no custom MongoDB encoding needed

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use default JSON response class

# Mount static files for frontend
# Get the absolute path to the frontend directory
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

# Mount static directories
app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")
app.mount("/site", StaticFiles(directory=frontend_dir), name="site")

# WebSocket manager
manager = WebSocketManager()

report_store = ReportStore(Path(os.getenv('REPORT_STORE_PATH', os.path.join('data', 'reports.json'))))

# SQLite 工作区存储（主存储，替代 reports.json 的全量重写）
workspace_store = WorkspaceStore(Path(os.getenv('WORKSPACE_DB_PATH', os.path.join('data', 'workspace.db'))))

# Constants
DOC_PATH = os.getenv("DOC_PATH", "./my-docs")

# Startup event


# Lifespan events now handled in the lifespan context manager above


# Routes
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main frontend HTML page."""
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
    index_path = os.path.join(frontend_dir, "index.html")
    
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    return HTMLResponse(content=content)


@app.get("/.well-known/agent-discovery.json")
async def agent_discovery(request: Request):
    """Advertise GPT Researcher services via the Agent Discovery Protocol."""
    origin = str(request.base_url).rstrip("/")
    domain = request.url.hostname or request.headers.get("host", "")
    contact = os.getenv("AGENT_DISCOVERY_CONTACT")

    document = build_agent_discovery_document(origin=origin, domain=domain, contact=contact)
    response = JSONResponse(content=document)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

@app.get("/report/{research_id}")
async def read_report(request: Request, research_id: str):
    docx_path = os.path.join('outputs', f"{research_id}.docx")
    if not os.path.exists(docx_path):
        return {"message": "Report not found."}
    return FileResponse(docx_path)


# API routes — 报告（SQLite 主存储，JSON 兼容双写）
@app.get("/api/reports")
async def get_all_reports(report_ids: str = None, workspace_id: str = None):
    report_ids_list = report_ids.split(",") if report_ids else None
    # 优先从 SQLite 读取（支持 workspace_id 过滤）
    reports = await workspace_store.list_reports(
        workspace_id=workspace_id, report_ids=report_ids_list
    )
    return {"reports": reports}


@app.get("/api/reports/{research_id}")
async def get_report_by_id(research_id: str):
    report = await workspace_store.get_report(research_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": report}


@app.post("/api/reports")
async def create_or_update_report(request: Request):
    try:
        data = await request.json()
        research_id = data.get("id", "temp_id")

        now_ms = int(time.time() * 1000)
        existing = await workspace_store.get_report(research_id)
        incoming_timestamp = data.get("timestamp")
        timestamp = incoming_timestamp if isinstance(incoming_timestamp, int) else now_ms
        if existing and isinstance(existing.get("timestamp"), int):
            timestamp = max(timestamp, existing["timestamp"])

        # 确定归属工作区：新报告用传入值或默认工作区；已存在则保留原归属
        workspace_id = (
            data.get("workspace_id")
            or data.get("workspaceId")
            or (existing.get("workspaceId") if existing else None)
            or migrate_module.DEFAULT_WORKSPACE_ID
        )

        report = {
            "id": research_id,
            "workspace_id": workspace_id,
            "question": data.get("question"),
            "answer": data.get("answer"),
            "orderedData": data.get("orderedData") or [],
            "chatMessages": data.get("chatMessages") or [],
            "timestamp": timestamp,
        }

        # 写 SQLite（主）
        await workspace_store.upsert_report(research_id, report)

        # 兼容：同时写旧 JSON store（不带 workspace_id，保持原格式）
        compat_report = {
            k: v for k, v in report.items() if k != "workspace_id"
        }
        await report_store.upsert_report(research_id, compat_report)

        return {"success": True, "id": research_id}
    except Exception as e:
        logger.error(f"Error processing report creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/reports/{research_id}")
async def update_report(research_id: str, request: Request):
    existing = await workspace_store.get_report(research_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Report not found")

    data = await request.json()
    now_ms = int(time.time() * 1000)

    updated = {
        **existing,
        **{k: v for k, v in data.items() if v is not None},
        "id": research_id,
        "timestamp": now_ms,
    }

    await workspace_store.upsert_report(research_id, updated)
    # 兼容写
    compat_report = {k: v for k, v in updated.items() if k != "workspace_id"}
    await report_store.upsert_report(research_id, compat_report)
    return {"success": True, "id": research_id}


@app.delete("/api/reports/{research_id}")
async def delete_report(research_id: str):
    existed = await workspace_store.delete_report(research_id)
    await report_store.delete_report(research_id)  # 兼容删
    if not existed:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"success": True}


@app.get("/api/reports/{research_id}/chat")
async def get_report_chat(research_id: str):
    report = await workspace_store.get_report(research_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"chatMessages": report.get("chatMessages") or []}


@app.post("/api/reports/{research_id}/chat")
async def add_report_chat_message(research_id: str, request: Request):
    report = await workspace_store.get_report(research_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    message = await request.json()
    chat_messages = report.get("chatMessages") or []
    if isinstance(chat_messages, list):
        chat_messages = [*chat_messages, message]
    else:
        chat_messages = [message]

    now_ms = int(time.time() * 1000)
    updated = {
        **report,
        "chatMessages": chat_messages,
        "timestamp": now_ms,
    }

    await workspace_store.upsert_report(research_id, updated)
    return {"success": True, "id": research_id}


async def write_report(research_request: ResearchRequest, research_id: str = None):
    report_information = await run_agent(
        task=research_request.task,
        report_type=research_request.report_type,
        report_source=research_request.report_source,
        source_urls=[],
        document_urls=[],
        tone=Tone[research_request.tone],
        websocket=None,
        stream_output=None,
        headers=research_request.headers,
        query_domains=[],
        config_path="",
        return_researcher=True
    )

    docx_path = await write_md_to_word(report_information[0], research_id)
    pdf_path = await write_md_to_pdf(report_information[0], research_id)
    if research_request.report_type != "multi_agents":
        report, researcher = report_information
        response = {
            "research_id": research_id,
            "research_information": {
                "source_urls": researcher.get_source_urls(),
                "research_costs": researcher.get_costs(),
                "visited_urls": list(researcher.visited_urls),
                "research_images": researcher.get_research_images(),
                # "research_sources": researcher.get_research_sources(),  # Raw content of sources may be very large
            },
            "report": report,
            "docx_path": docx_path,
            "pdf_path": pdf_path
        }
    else:
        response = { "research_id": research_id, "report": "", "docx_path": docx_path, "pdf_path": pdf_path }

    return response

@app.post("/report/")
async def generate_report(research_request: ResearchRequest, background_tasks: BackgroundTasks):
    research_id = sanitize_filename(f"task_{int(time.time())}_{research_request.task}")

    if research_request.generate_in_background:
        background_tasks.add_task(write_report, research_request=research_request, research_id=research_id)
        return {"message": "Your report is being generated in the background. Please check back later.",
                "research_id": research_id}
    else:
        response = await write_report(research_request, research_id)
        return response


@app.get("/files/")
async def list_files():
    if not os.path.exists(DOC_PATH):
        os.makedirs(DOC_PATH, exist_ok=True)
    files = os.listdir(DOC_PATH)
    print(f"Files in {DOC_PATH}: {files}")
    return {"files": files}


@app.post("/api/multi_agents")
async def run_multi_agents():
    return await execute_multi_agents(manager)


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    return await handle_file_upload(file, DOC_PATH)


@app.delete("/files/{filename}")
async def delete_file(filename: str):
    return await handle_file_deletion(filename, DOC_PATH)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await handle_websocket_communication(websocket, manager)
    except WebSocketDisconnect as e:
        # Disconnect with more detailed logging about the WebSocket disconnect reason
        logger.info(f"WebSocket disconnected with code {e.code} and reason: '{e.reason}'")
        await manager.disconnect(websocket)
    except Exception as e:
        # More general exception handling
        logger.error(f"Unexpected WebSocket error: {str(e)}")
        await manager.disconnect(websocket)

@app.post("/api/chat")
async def chat(chat_request: ChatRequest):
    """Process a chat request with a report and message history.

    Args:
        chat_request: ChatRequest object containing report text and message history

    Returns:
        JSON response with the assistant's message and any tool usage metadata
    """
    try:
        logger.info(f"Received chat request with {len(chat_request.messages)} messages")

        # Create chat agent with the report
        chat_agent = ChatAgentWithMemory(
            report=chat_request.report,
            config_path="default",
            headers=None
        )

        # Process the chat and get response with metadata
        response_content, tool_calls_metadata = await chat_agent.chat(chat_request.messages, None)
        logger.info(f"response_content: {response_content}")
        logger.info(f"Got chat response of length: {len(response_content) if response_content else 0}")
        
        if tool_calls_metadata:
            logger.info(f"Tool calls used: {json.dumps(tool_calls_metadata)}")

        # Format response as a ChatMessage object with role, content, timestamp and metadata
        response_message = {
            "role": "assistant",
            "content": response_content,
            "timestamp": int(time.time() * 1000),  # Current time in milliseconds
            "metadata": {
                "tool_calls": tool_calls_metadata
            } if tool_calls_metadata else None
        }

        logger.info(f"Returning formatted response: {json.dumps(response_message)[:100]}...")
        return {"response": response_message}
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return {"error": str(e)}

@app.post("/api/reports/{research_id}/chat")
async def research_report_chat(research_id: str, request: Request):
    """Handle chat requests for a specific research report.
    Directly processes the raw request data to avoid validation errors.
    """
    try:
        # Get raw JSON data from request
        data = await request.json()
        
        # Create chat agent with the report
        chat_agent = ChatAgentWithMemory(
            report=data.get("report", ""),
            config_path="default",
            headers=None
        )

        # Process the chat and get response with metadata
        response_content, tool_calls_metadata = await chat_agent.chat(data.get("messages", []), None)
        
        if tool_calls_metadata:
            logger.info(f"Tool calls used: {json.dumps(tool_calls_metadata)}")

        # Format response as a ChatMessage object
        response_message = {
            "role": "assistant",
            "content": response_content,
            "timestamp": int(time.time() * 1000),
            "metadata": {
                "tool_calls": tool_calls_metadata
            } if tool_calls_metadata else None
        }

        return {"response": response_message}
    except Exception as e:
        logger.error(f"Error in research report chat: {str(e)}", exc_info=True)
        return {"error": str(e)}


# ======================== 工作区（Workspace）API ========================
import uuid as _uuid


@app.get("/api/workspaces")
async def list_workspaces():
    workspaces = await workspace_store.list_workspaces()
    return {"workspaces": workspaces}


@app.post("/api/workspaces")
async def create_workspace(request: Request):
    try:
        data = await request.json()
        ws_id = data.get("id") or str(_uuid.uuid4())
        name = data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="工作区名称不能为空")
        description = data.get("description", "")
        ws = await workspace_store.create_workspace(ws_id, name, description)
        return {"success": True, "workspace": ws}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/workspaces/{ws_id}")
async def update_workspace(ws_id: str, request: Request):
    data = await request.json()
    updated = await workspace_store.update_workspace(
        ws_id,
        name=data.get("name"),
        description=data.get("description"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    return {"success": True, "workspace": updated}


@app.delete("/api/workspaces/{ws_id}")
async def delete_workspace(ws_id: str):
    # 不允许删除默认工作区
    if ws_id == migrate_module.DEFAULT_WORKSPACE_ID:
        raise HTTPException(status_code=400, detail="默认工作区不可删除")
    existed = await workspace_store.delete_workspace(ws_id)
    if not existed:
        raise HTTPException(status_code=404, detail="工作区不存在")
    # 清理该工作区的文件目录
    import shutil
    ws_file_dir = Path("data/workspace_files") / ws_id
    if ws_file_dir.exists():
        shutil.rmtree(ws_file_dir, ignore_errors=True)
    return {"success": True}


# 工作区文档管理
@app.get("/api/workspaces/{ws_id}/documents")
async def list_workspace_documents(ws_id: str):
    if await workspace_store.get_workspace(ws_id) is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    docs = await workspace_store.list_documents(ws_id)
    return {"documents": docs}


@app.post("/api/workspaces/{ws_id}/documents")
async def upload_workspace_document(ws_id: str, file: UploadFile = File(...)):
    if await workspace_store.get_workspace(ws_id) is None:
        raise HTTPException(status_code=404, detail="工作区不存在")

    # 存到 data/workspace_files/{ws_id}/documents/
    doc_dir = Path("data/workspace_files") / ws_id / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(_uuid.uuid4())
    safe_name = sanitize_filename(file.filename or doc_id)
    file_path = doc_dir / f"{doc_id}_{safe_name}"
    content = await file.read()
    file_path.write_bytes(content)

    doc = await workspace_store.add_document(
        doc_id, ws_id, file.filename, str(file_path), len(content)
    )
    return {"success": True, "document": doc}


@app.delete("/api/workspaces/{ws_id}/documents/{doc_id}")
async def delete_workspace_document(ws_id: str, doc_id: str):
    file_path = await workspace_store.delete_document(doc_id)
    if file_path is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    # 删实际文件
    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception:
        pass
    return {"success": True}


def _load_mcp_servers_from_config():
    """Load MCP server configs from config.json, resolving ${ENV_VAR} references."""
    import re
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config.json"
    )
    if not os.path.exists(config_path):
        return []

    with open(config_path, "r") as f:
        config = json.load(f)

    mcp_servers = config.get("MCP_SERVERS", [])
    braced_var_re = re.compile(r"\$\{([^}]+)\}")

    def expand_env_vars(value):
        if isinstance(value, str):
            return braced_var_re.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
        elif isinstance(value, dict):
            return {k: expand_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [expand_env_vars(v) for v in value]
        return value

    return [expand_env_vars(server) for server in mcp_servers]


@app.get("/api/mcp-servers")
async def get_mcp_servers():
    """Return available MCP servers from config.json for the frontend to display.
    Only returns display-safe info (name, description, enabled).
    Full configs with credentials are NEVER exposed to the frontend.
    """
    servers = _load_mcp_servers_from_config()

    # Build display-safe list - NO credentials exposed
    display_servers = []
    for server in servers:
        display_servers.append({
            "name": server.get("name", ""),
            "description": server.get("description", ""),
            "enabled": server.get("enabled", True),
        })

    return {"servers": display_servers}
