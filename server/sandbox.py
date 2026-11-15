import json
import os
import shutil
import subprocess
from pathlib import Path

from .paths import shared_workspace_dir

CMD_TIMEOUT = int(os.environ.get("STARFERRET_CMD_TIMEOUT", "120"))
SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist"}
RULE_EXTENSIONS = {".md", ".txt", ".markdown"}


class SandboxError(Exception):
    pass


def docker_available() -> bool:
    """Legacy API field; agents use the host folder, not Docker."""
    return False


def _drive_path_for(workspace_id: str) -> str:
    from . import db

    with db.cursor() as cur:
        row = cur.execute(
            "SELECT drive_path FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
    if not row:
        return ""
    return (row["drive_path"] or "").strip()


def folder_root(workspace_id: str) -> Path:
    """One real folder on the machine. Agents and the UI are jailed here."""
    drive = _drive_path_for(workspace_id)
    if drive:
        path = Path(drive).expanduser().resolve()
        if path.is_dir():
            return path
    root = shared_workspace_dir(workspace_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_layout(workspace_id: str) -> Path:
    """Seed standard dirs inside the jailed folder."""
    root = folder_root(workspace_id)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(parents=True, exist_ok=True)
    (root / "outputs").mkdir(parents=True, exist_ok=True)
    return root


def workspace_dir(agent_id: str) -> Path:
    from . import store

    agent = store.get_agent(agent_id)
    if not agent or not agent.get("workspace_id"):
        raise SandboxError("agent has no workspace")
    return folder_root(agent["workspace_id"])


def files_room(agent_id: str) -> str:
    from . import store

    agent = store.get_agent(agent_id)
    if agent and agent.get("workspace_id"):
        return f"workspace:{agent['workspace_id']}"
    return f"agent:{agent_id}"


def _jail(root: Path, rel: str | None) -> Path:
    rel = (rel or ".").replace("\\", "/").lstrip("/")
    if rel in {"", "."}:
        return root
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SandboxError("path escapes workspace") from exc
    return target


def jail(agent_id: str, rel: str | None) -> Path:
    root = workspace_dir(agent_id)
    return _jail(root, rel)


def workspace_jail(workspace_id: str, rel: str | None) -> Path:
    return _jail(folder_root(workspace_id), rel)


def _skip_path(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    for part in rel.parts:
        if part in SKIP_DIR_NAMES:
            return True
    return False


def list_dir(workspace_id: str, rel: str = ".") -> dict:
    """One-level browse of the jailed machine folder."""
    root = ensure_layout(workspace_id)
    current = workspace_jail(workspace_id, rel)
    if not current.exists():
        raise SandboxError("Not found")
    if current.is_file():
        raise SandboxError("Not a folder")
    rel_norm = str(current.relative_to(root)).replace("\\", "/")
    if rel_norm == ".":
        rel_norm = ""
    entries = []
    for path in sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if _skip_path(path, root):
            continue
        child_rel = str(path.relative_to(root)).replace("\\", "/")
        entries.append(
            {
                "name": path.name,
                "path": child_rel,
                "type": "dir" if path.is_dir() else "file",
                "size": path.stat().st_size if path.is_file() else 0,
            }
        )
    return {
        "root_path": str(root),
        "path": rel_norm,
        "entries": entries[:1000],
    }


def mkdir(workspace_id: str, rel: str) -> dict:
    path = workspace_jail(workspace_id, rel)
    path.mkdir(parents=True, exist_ok=True)
    parent = str(Path(rel.replace("\\", "/")).parent).replace("\\", "/")
    if parent in {".", ""}:
        parent = ""
    return list_dir(workspace_id, parent)


def list_workspace_files(workspace_id: str) -> list[dict]:
    root = folder_root(workspace_id)
    if not root.exists():
        return []
    items = []
    for path in sorted(root.rglob("*")):
        if _skip_path(path, root) or not path.is_file():
            continue
        items.append(
            {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "size": path.stat().st_size,
                "type": "file",
            }
        )
    return items[:500]


def discover_rules(workspace_id: str) -> list[dict]:
    """Rules are markdown/text files dropped in rules/."""
    ensure_layout(workspace_id)
    rules_dir = folder_root(workspace_id) / "rules"
    items = []
    if not rules_dir.is_dir():
        return items
    for path in sorted(rules_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in RULE_EXTENSIONS:
            continue
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            text = ""
        rel = str(path.relative_to(folder_root(workspace_id))).replace("\\", "/")
        items.append(
            {
                "name": path.name,
                "path": rel,
                "preview": (text[:240] + ("…" if len(text) > 240 else "")),
                "body": text,
            }
        )
    return items


def discover_skills(workspace_id: str) -> list[dict]:
    """Skills are skills/<name>/SKILL.md folders on disk."""
    ensure_layout(workspace_id)
    skills_dir = folder_root(workspace_id) / "skills"
    items = []
    if not skills_dir.is_dir():
        return items
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            text = ""
        description = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped:
                description = stripped[:200]
                break
        rel = str(skill_md.relative_to(folder_root(workspace_id))).replace("\\", "/")
        items.append(
            {
                "id": child.name,
                "name": child.name.replace("-", " ").replace("_", " ").strip() or child.name,
                "description": description,
                "path": rel,
                "enabled": True,
            }
        )
    return items


def list_files(agent_id: str, rel: str = ".") -> list[dict]:
    root = jail(agent_id, rel)
    if not root.exists():
        return []
    if root.is_file():
        stat = root.stat()
        return [{"path": rel.replace("\\", "/"), "size": stat.st_size, "type": "file"}]
    items = []
    workspace = workspace_dir(agent_id)
    # One level for tools; recursive still ok for agents that ask for deep trees.
    for path in sorted(root.rglob("*")):
        if _skip_path(path, workspace):
            continue
        rel_path = str(path.relative_to(workspace)).replace("\\", "/")
        items.append(
            {
                "path": rel_path,
                "size": path.stat().st_size if path.is_file() else 0,
                "type": "file" if path.is_file() else "dir",
            }
        )
    return items[:500]


def read_file(agent_id: str, rel: str, max_bytes: int = 200_000) -> str:
    path = jail(agent_id, rel)
    if not path.is_file():
        raise SandboxError(f"not a file: {rel}")
    data = path.read_bytes()
    if len(data) > max_bytes:
        return data[:max_bytes].decode("utf-8", errors="replace") + "\n...[truncated]"
    return data.decode("utf-8", errors="replace")


def write_file(agent_id: str, rel: str, content: str) -> str:
    path = jail(agent_id, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel.replace("\\", "/")


def delete_file(agent_id: str, rel: str) -> None:
    path = jail(agent_id, rel)
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
    else:
        raise SandboxError(f"not found: {rel}")


def delete_workspace_entry(workspace_id: str, rel: str) -> None:
    path = workspace_jail(workspace_id, rel)
    root = folder_root(workspace_id)
    if path.resolve() == root.resolve():
        raise SandboxError("Cannot delete the workspace root")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
    else:
        raise SandboxError(f"not found: {rel}")


def run_command(agent_id: str, command: str) -> dict:
    if not command or not command.strip():
        raise SandboxError("empty command")
    root = workspace_dir(agent_id)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"Command timed out after {CMD_TIMEOUT}s",
        }
    stdout = (proc.stdout or "")[-20_000:]
    stderr = (proc.stderr or "")[-20_000:]
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "cwd": str(root),
    }


def tool_list_files(agent_id: str, path: str = ".") -> str:
    return json.dumps(list_files(agent_id, path), indent=2)


def tool_read_file(agent_id: str, path: str) -> str:
    return read_file(agent_id, path)


def tool_write_file(agent_id: str, path: str, content: str) -> str:
    if Path(path or "").suffix.lower() in {".docx", ".xlsx", ".pptx"}:
        # Plain text in a .docx makes a file Word cannot open.
        return json.dumps(
            {
                "error": "write_file writes plain text, which breaks Word, Excel, and PowerPoint "
                "files. Use office_create for a new .docx or .xlsx, or office_replace, "
                "office_add_paragraph, or office_set_cell to change one."
            }
        )
    written = write_file(agent_id, path, content)
    return json.dumps({"ok": True, "path": written})


def tool_run_command(agent_id: str, command: str) -> str:
    return json.dumps(run_command(agent_id, command))
