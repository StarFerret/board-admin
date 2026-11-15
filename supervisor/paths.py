import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTROL_PORT = 7411
DEFAULT_BOARD_PORT = 7410
# STARFERRET_DATA_DIR lets a test copy run beside the real one without sharing its databases.
DATA_DIR = Path(os.environ.get("STARFERRET_DATA_DIR") or ROOT / "data")
CONTROL_DB_PATH = DATA_DIR / "control.db"
# One time link secret for creating the first admin from another machine. Deleted once an admin exists.
SETUP_TOKEN_PATH = DATA_DIR / "control" / "setup-token"
# Lets tools on this Mac (the installer) call Control without an admin password. Mode 600, kept.
LOCAL_KEY_PATH = DATA_DIR / "control" / "local-key"
BOARD_DB_PATH = DATA_DIR / "board.db"  # the Board owns it; Control only reads it
STACK_DIR = DATA_DIR / "stack"
ENV_DIR = STACK_DIR / "env"
CATALOG_DIR = ROOT / "catalog"
COMPOSE_DIR = ROOT / "stacks"
INSTALLER_DIR = ROOT / "installer"
CONTROL_WEB_DIST = ROOT / "control-web" / "dist"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STACK_DIR.mkdir(parents=True, exist_ok=True)
