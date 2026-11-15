"""Built-in MCP tools. They run in-process so every agent has them without extra servers.

documents — read and edit uploaded text files in the shared workspace.
office — read and edit .docx, .xlsx, and .pptx files in that same workspace.
web — search the public web and read a page.
"""

import html
import ipaddress
import json
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

from . import sandbox

OFFICE_SUFFIXES = {".docx", ".xlsx", ".pptx"}

PACKS = [
    {
        "id": "web",
        "name": "Web search",
        "detail": "Search the public web and read a page.",
        "tools": ["web_search", "web_fetch"],
    },
    {
        "id": "office",
        "name": "Word and Office",
        "detail": "Read and edit Word, Excel, and PowerPoint files in this folder.",
        "tools": [
            "office_read",
            "office_create",
            "office_replace",
            "office_add_paragraph",
            "office_set_cell",
        ],
    },
    {
        "id": "documents",
        "name": "Text files",
        "detail": "Read and edit uploaded text files in this folder.",
        "tools": ["documents_read", "documents_edit"],
    },
]

PACK_BLURBS = {
    "documents": "documents_read and documents_edit modify uploaded text files in place.",
    "office": (
        "office_read reads .docx, .xlsx, and .pptx files. office_create makes a new .docx or .xlsx "
        "(use it for every new Word or Excel deliverable, never write_file). office_replace, "
        "office_add_paragraph, and office_set_cell change existing files."
    ),
    "web": "web_search queries the public web. web_fetch reads one public page.",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "documents_read",
            "description": "Read an uploaded file from the shared workspace. Office files return their text.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "documents_edit",
            "description": "Modify an uploaded text file in place by replacing every occurrence of find with replace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                },
                "required": ["path", "find", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_read",
            "description": "Read a .docx, .xlsx, or .pptx file from the shared workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_create",
            "description": (
                "Create a new Word (.docx) or Excel (.xlsx) file, or replace one you made. "
                "For .docx, content is plain text: '# ' starts a heading, '## ' a subheading, "
                "'- ' a bullet, other lines are paragraphs. For .xlsx, each line is a row and "
                "cells are separated by tabs or '|'. Save new work under outputs/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Like outputs/review.docx"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_replace",
            "description": "Replace text inside a .docx, .xlsx, or .pptx file. Other agents in the workspace see the change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "find": {"type": "string"},
                    "replace": {"type": "string"},
                },
                "required": ["path", "find", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_add_paragraph",
            "description": "Append a paragraph to a .docx file in the shared workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["path", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "office_set_cell",
            "description": "Set a cell in a .xlsx file. cell is like A1. sheet is the sheet name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "cell": {"type": "string"},
                    "value": {"type": "string"},
                    "sheet": {"type": "string"},
                },
                "required": ["path", "cell", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public web. Returns titles, URLs, and snippets. Use web_fetch to read a result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "description": "How many results to return, 1 to 8."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a public http or https page and return its readable text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

_NAMES = {tool["function"]["name"] for tool in TOOLS}
_BY_NAME = {tool["function"]["name"]: tool for tool in TOOLS}
_PACK_IDS = {pack["id"] for pack in PACKS}


def catalog() -> list[dict]:
    return [{k: pack[k] for k in ("id", "name", "detail")} for pack in PACKS]


def known_pack(pack_id: str) -> bool:
    return pack_id in _PACK_IDS


def tools_for(pack_ids: list[str]) -> list[dict]:
    wanted = []
    for pack in PACKS:
        if pack["id"] in pack_ids:
            wanted.extend(pack["tools"])
    return [_BY_NAME[name] for name in wanted if name in _BY_NAME]


def blurbs_for(pack_ids: list[str]) -> list[str]:
    return [PACK_BLURBS[pack["id"]] for pack in PACKS if pack["id"] in pack_ids and pack["id"] in PACK_BLURBS]


def handles(name: str) -> bool:
    return name in _NAMES


def call_tool(agent_id: str, name: str, args: dict) -> str:
    try:
        if name == "documents_read":
            return _documents_read(agent_id, args.get("path") or "")
        if name == "documents_edit":
            return _documents_edit(
                agent_id, args.get("path") or "", args.get("find") or "", args.get("replace") or ""
            )
        if name == "office_read":
            return _office_read(agent_id, args.get("path") or "")
        if name == "office_create":
            return _office_create(agent_id, args.get("path") or "", args.get("content") or "")
        if name == "office_replace":
            return _office_replace(
                agent_id, args.get("path") or "", args.get("find") or "", args.get("replace") or ""
            )
        if name == "office_add_paragraph":
            return _office_add_paragraph(agent_id, args.get("path") or "", args.get("text") or "")
        if name == "office_set_cell":
            return _office_set_cell(
                agent_id,
                args.get("path") or "",
                args.get("cell") or "",
                args.get("value") if args.get("value") is not None else "",
                args.get("sheet") or "",
            )
        if name == "web_search":
            return _web_search(args.get("query") or "", args.get("limit") or 5)
        if name == "web_fetch":
            return _web_fetch(args.get("url") or "")
        return json.dumps({"error": f"unknown mcp tool {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _path(agent_id: str, rel: str) -> Path:
    path = sandbox.jail(agent_id, rel)
    if not path.is_file():
        raise sandbox.SandboxError(f"not a file: {rel}")
    return path


def _documents_read(agent_id: str, rel: str) -> str:
    path = _path(agent_id, rel)
    if path.suffix.lower() in OFFICE_SUFFIXES:
        return _office_read(agent_id, rel)
    return sandbox.read_file(agent_id, rel)


def _documents_edit(agent_id: str, rel: str, find: str, replace: str) -> str:
    if not find:
        return json.dumps({"error": "find is empty"})
    path = _path(agent_id, rel)
    if path.suffix.lower() in OFFICE_SUFFIXES:
        return _office_replace(agent_id, rel, find, replace)
    text = path.read_text(encoding="utf-8")
    count = text.count(find)
    if count == 0:
        return json.dumps({"ok": False, "replacements": 0, "path": rel})
    path.write_text(text.replace(find, replace), encoding="utf-8")
    return json.dumps({"ok": True, "replacements": count, "path": rel})


def _office_read(agent_id: str, rel: str) -> str:
    path = _path(agent_id, rel)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from docx import Document

        doc = Document(path)
        lines = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                lines.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(lines)[:20000]
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(path, data_only=True)
        chunks = []
        for ws in wb.worksheets:
            chunks.append(f"# {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    chunks.append("\t".join("" if cell is None else str(cell) for cell in row))
        return "\n".join(chunks)[:20000]
    if suffix == ".pptx":
        from pptx import Presentation

        prs = Presentation(path)
        chunks = []
        for index, slide in enumerate(prs.slides, start=1):
            chunks.append(f"# slide {index}")
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    text = shape.text_frame.text.strip()
                    if text:
                        chunks.append(text)
        return "\n".join(chunks)[:20000]
    return json.dumps({"error": "office_read supports .docx, .xlsx, and .pptx"})


def _replace_docx(path: Path, find: str, replace: str) -> int:
    from docx import Document

    doc = Document(path)
    count = 0

    def rewrite(paragraph) -> None:
        nonlocal count
        if find in paragraph.text:
            count += paragraph.text.count(find)
            paragraph.text = paragraph.text.replace(find, replace)

    for paragraph in doc.paragraphs:
        rewrite(paragraph)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    rewrite(paragraph)
    doc.save(path)
    return count


def _replace_xlsx(path: Path, find: str, replace: str) -> int:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    count = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and find in cell.value:
                    count += cell.value.count(find)
                    cell.value = cell.value.replace(find, replace)
    wb.save(path)
    return count


def _replace_pptx(path: Path, find: str, replace: str) -> int:
    from pptx import Presentation

    prs = Presentation(path)
    count = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    if find in run.text:
                        count += run.text.count(find)
                        run.text = run.text.replace(find, replace)
    prs.save(path)
    return count


def _office_replace(agent_id: str, rel: str, find: str, replace: str) -> str:
    if not find:
        return json.dumps({"error": "find is empty"})
    path = _path(agent_id, rel)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        count = _replace_docx(path, find, replace)
    elif suffix == ".xlsx":
        count = _replace_xlsx(path, find, replace)
    elif suffix == ".pptx":
        count = _replace_pptx(path, find, replace)
    else:
        return json.dumps({"error": "office_replace supports .docx, .xlsx, and .pptx"})
    return json.dumps({"ok": count > 0, "replacements": count, "path": rel})


def _office_create(agent_id: str, rel: str, content: str) -> str:
    if not rel:
        return json.dumps({"error": "path is empty. Try outputs/<name>.docx"})
    path = sandbox.jail(agent_id, rel)
    suffix = path.suffix.lower()
    if suffix not in {".docx", ".xlsx"}:
        return json.dumps({"error": "office_create makes .docx or .xlsx files. Pick one of those."})
    if not content.strip():
        return json.dumps({"error": "content is empty. Put the text of the file in content."})
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [line.rstrip() for line in content.replace("\r\n", "\n").split("\n")]
    if suffix == ".docx":
        from docx import Document

        doc = Document()
        for line in lines:
            text = line.strip().replace("**", "")
            if not text:
                continue
            if text.startswith("## "):
                doc.add_heading(text[3:].strip(), level=2)
            elif text.startswith("# "):
                doc.add_heading(text[2:].strip(), level=1)
            elif text[:2] in {"- ", "* "}:
                doc.add_paragraph(text[2:].strip(), style="List Bullet")
            else:
                doc.add_paragraph(text)
        doc.save(path)
        return json.dumps({"ok": True, "path": rel, "paragraphs": len(doc.paragraphs)})
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    rows = 0
    for line in lines:
        if not line.strip():
            continue
        if "\t" in line:
            cells = line.split("\t")
        elif "|" in line:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(set(cell) <= set("-: ") for cell in cells):
                continue  # markdown table divider
        else:
            cells = [line]
        ws.append([_cell_value(cell.strip()) for cell in cells])
        rows += 1
    wb.save(path)
    return json.dumps({"ok": True, "path": rel, "rows": rows})


def _cell_value(text: str):
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _office_add_paragraph(agent_id: str, rel: str, text: str) -> str:
    path = _path(agent_id, rel)
    if path.suffix.lower() != ".docx":
        return json.dumps({"error": "office_add_paragraph supports .docx"})
    from docx import Document

    doc = Document(path)
    doc.add_paragraph(text)
    doc.save(path)
    return json.dumps({"ok": True, "path": rel})


def _office_set_cell(agent_id: str, rel: str, cell: str, value, sheet: str) -> str:
    path = _path(agent_id, rel)
    if path.suffix.lower() != ".xlsx":
        return json.dumps({"error": "office_set_cell supports .xlsx"})
    if not cell:
        return json.dumps({"error": "cell is empty"})
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active
    ws[cell] = value
    wb.save(path)
    return json.dumps({"ok": True, "path": rel, "sheet": ws.title, "cell": cell})


_WEB_UA = "StarFerret/1.0"
_WEB_MAX = 12000


def _web_search(query: str, limit) -> str:
    query = query.strip()
    if not query:
        return json.dumps({"error": "query is empty"})
    try:
        count = max(1, min(int(limit), 8))
    except (TypeError, ValueError):
        count = 5
    resp = requests.get(
        "https://www.bing.com/search",
        params={"q": query, "format": "rss", "count": count},
        headers={"User-Agent": _WEB_UA},
        timeout=20,
    )
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    results = []
    for item in root.findall("./channel/item")[:count]:
        results.append(
            {
                "title": html.unescape((item.findtext("title") or "").strip()),
                "url": (item.findtext("link") or "").strip(),
                "snippet": html.unescape((item.findtext("description") or "").strip())[:500],
            }
        )
    return json.dumps({"query": query, "results": results})


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)


def _public_host(host: str) -> None:
    host = (host or "").strip().rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("only public web addresses can be fetched")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError(f"could not resolve {host}") from exc
        addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses or any(not ip.is_global for ip in addresses):
        raise ValueError("only public web addresses can be fetched")


def _web_fetch(url: str) -> str:
    url = url.strip()
    if not url:
        return json.dumps({"error": "url is empty"})
    current = url
    resp = None
    for _ in range(5):
        parsed = urlparse(current)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return json.dumps({"error": "url must be http or https"})
        _public_host(parsed.hostname)
        resp = requests.get(
            current,
            headers={"User-Agent": _WEB_UA},
            timeout=20,
            allow_redirects=False,
            stream=True,
        )
        if resp.is_redirect:
            loc = resp.headers.get("Location") or ""
            resp.close()
            if not loc:
                return json.dumps({"error": "redirect with no location"})
            current = requests.compat.urljoin(current, loc)
            continue
        break
    else:
        return json.dumps({"error": "too many redirects"})
    try:
        chunks = []
        size = 0
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            size += len(chunk)
            chunks.append(chunk)
            if size >= 500_000:
                break
        raw = b"".join(chunks)
    finally:
        resp.close()
    encoding = resp.encoding or "utf-8"
    text = raw.decode(encoding, errors="replace")
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" in content_type or text.lstrip().lower().startswith("<!doctype") or "<html" in text[:500].lower():
        parser = _PageText()
        parser.feed(text)
        text = " ".join("".join(parser.parts).split())
    else:
        text = text.strip()
    return json.dumps({"url": current, "status": resp.status_code, "text": text[:_WEB_MAX]})
