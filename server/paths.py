import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 7410
# STARFERRET_DATA_DIR lets a test copy run beside the real one without sharing its databases.
DATA_DIR = Path(os.environ.get("STARFERRET_DATA_DIR") or ROOT / "data")
DB_PATH = DATA_DIR / "board.db"
AGENTS_DIR = DATA_DIR / "agents"
WORKSPACES_DIR = DATA_DIR / "workspaces"
WEB_DIST = ROOT / "web" / "dist"


def shared_workspace_dir(workspace_id: str) -> Path:
    path = WORKSPACES_DIR / workspace_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_dir(agent_id: str) -> Path:
    return AGENTS_DIR / agent_id


def workspace_dir(agent_id: str) -> Path:
    return agent_dir(agent_id) / "workspace"


def logs_dir(agent_id: str) -> Path:
    return agent_dir(agent_id) / "logs"


def ensure_agent_dirs(agent_id: str) -> Path:
    ws = workspace_dir(agent_id)
    ws.mkdir(parents=True, exist_ok=True)
    logs_dir(agent_id).mkdir(parents=True, exist_ok=True)
    return ws
