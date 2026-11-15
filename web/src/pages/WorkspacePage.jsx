import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import AppShell from "../components/AppShell.jsx";
import ShareSheet from "../components/ShareSheet.jsx";
import {
  addWorkspaceTool,
  browseWorkspace,
  createAgent,
  deleteWorkspace,
  deleteWorkspaceFile,
  getHost,
  getWorkspace,
  listTools,
  listWorkspaces,
  mkdirWorkspace,
  moveAgent,
  removeWorkspaceTool,
  renameWorkspace,
  shareWorkspace,
  uploadWorkspaceFiles,
} from "../api.js";
import PeopleHere from "../PeopleHere.jsx";
import { useAgentSocket } from "../useSocket.js";
import { useVisitorName } from "../visitorContext.js";
import WorkState from "../WorkState.jsx";

function parentPath(path) {
  if (!path) return "";
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function breadcrumbs(path) {
  const parts = (path || "").split("/").filter(Boolean);
  const crumbs = [{ label: "root", path: "" }];
  let acc = "";
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part;
    crumbs.push({ label: part, path: acc });
  }
  return crumbs;
}

function formatSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function WorkspacePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [folder, setFolder] = useState(null);
  const [folders, setFolders] = useState([]);
  const [missing, setMissing] = useState(false);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [addingAgent, setAddingAgent] = useState(false);
  const [addingDir, setAddingDir] = useState(false);
  const [browsePath, setBrowsePath] = useState("");
  const [entries, setEntries] = useState([]);
  const [newDir, setNewDir] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [catalog, setCatalog] = useState([]);
  const [shareOrigin, setShareOrigin] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState("");
  const [shareNote, setShareNote] = useState("");
  const [shareCopied, setShareCopied] = useState(false);
  const [boardName, setBoardName] = useState("Workspaces");
  const [viewers, setViewers] = useState(1);
  const [roomPeople, setRoomPeople] = useState([]);
  const visitorName = useVisitorName();

  async function loadBrowse(path = browsePath) {
    const listing = await browseWorkspace(id, path || "");
    setBrowsePath(listing.path || "");
    setEntries(listing.entries || []);
    return listing;
  }

  async function load() {
    const [current, listed, listedTools, hostInfo] = await Promise.all([
      getWorkspace(id),
      listWorkspaces(),
      listTools(),
      getHost().catch(() => ({ origin: window.location.origin })),
    ]);
    setFolder(current);
    setCatalog(listedTools);
    setTitle(current.name || "");
    setFolders(listed.workspaces || []);
    setShareOrigin(hostInfo.origin || window.location.origin);
    if (hostInfo.board_name) setBoardName(hostInfo.board_name);
    setMissing(false);
    await loadBrowse("");
  }

  async function onShare() {
    setError("");
    try {
      const result = await shareWorkspace(id);
      setShareUrl(result.url || `${shareOrigin}/w/${id}`);
      setShareNote("");
      setShareOpen(true);
      setShareCopied(false);
    } catch (err) {
      setShareUrl(`${shareOrigin || window.location.origin}/w/${id}`);
      setShareNote(err.message);
      setShareOpen(true);
    }
  }

  function copyShare() {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 1500);
  }

  useEffect(() => {
    load().catch(() => setMissing(true));
  }, [id]);

  useAgentSocket(
    null,
    {
      agent: (agent) => {
        setFolder((current) => {
          if (!current) return current;
          const agents = (current.agents || []).filter((item) => item.id !== agent.id);
          if (!agent.archived && agent.workspace_id === current.id) agents.unshift(agent);
          return { ...current, agents };
        });
      },
      agent_deleted: ({ id: agentId }) => {
        setFolder((current) =>
          current
            ? { ...current, agents: (current.agents || []).filter((item) => item.id !== agentId) }
            : current
        );
      },
      status: ({ id: agentId, status }) => {
        setFolder((current) =>
          current
            ? {
                ...current,
                agents: (current.agents || []).map((item) =>
                  item.id === agentId ? { ...item, status } : item
                ),
              }
            : current
        );
      },
      files: () => {
        loadBrowse(browsePath).catch(() => {});
        getWorkspace(id)
          .then(setFolder)
          .catch(() => {});
      },
      workspace: (next) => {
        if (next && next.id === id) {
          setFolder((current) => (current ? { ...current, ...next } : next));
          setTitle(next.name || "");
          loadBrowse(browsePath).catch(() => {});
        }
      },
      workspace_deleted: ({ id: folderId }) => {
        if (folderId === id) setMissing(true);
      },
      presence: ({ workspace, count, people }) => {
        if (workspace === id) {
          setViewers(count || 1);
          setRoomPeople(people || []);
        }
      },
      board_name: ({ name }) => {
        if (name) setBoardName(name);
      },
    },
    id,
    visitorName
  );

  async function spawn(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      const agent = await createAgent(name.trim(), { workspace_id: id });
      setName("");
      setAddingAgent(false);
      navigate(`/a/${agent.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  async function onMove(agent, workspaceId) {
    if (!workspaceId || workspaceId === id) return;
    setError("");
    try {
      await moveAgent(agent.id, workspaceId);
      setFolder((current) =>
        current
          ? { ...current, agents: (current.agents || []).filter((item) => item.id !== agent.id) }
          : current
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function onRename(e) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      const renamed = await renameWorkspace(id, title.trim());
      setFolder((current) => (current ? { ...current, name: renamed.name } : current));
      setTitle(renamed.name);
      setEditingName(false);
    } catch (err) {
      setError(err.message);
    }
  }

  async function openEntry(entry) {
    setError("");
    if (entry.type === "dir") {
      try {
        await loadBrowse(entry.path);
      } catch (err) {
        setError(err.message);
      }
      return;
    }
    window.open(`/api/workspaces/${id}/files/${encodeURIComponent(entry.path)}`, "_blank");
  }

  async function onUpload(e) {
    const picked = e.target.files;
    if (!picked?.length) return;
    setError("");
    try {
      await uploadWorkspaceFiles(id, picked, browsePath);
      await loadBrowse(browsePath);
      const current = await getWorkspace(id);
      setFolder(current);
    } catch (err) {
      setError(err.message);
    } finally {
      e.target.value = "";
    }
  }

  async function onMkdir(e) {
    e.preventDefault();
    if (!newDir.trim()) return;
    setError("");
    const rel = browsePath ? `${browsePath}/${newDir.trim()}` : newDir.trim();
    try {
      await mkdirWorkspace(id, rel);
      setNewDir("");
      setAddingDir(false);
      await loadBrowse(browsePath);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDeleteEntry(path) {
    setError("");
    try {
      await deleteWorkspaceFile(id, path);
      await loadBrowse(browsePath);
      const current = await getWorkspace(id);
      setFolder(current);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onAddTool(packId) {
    setError("");
    try {
      const updated = await addWorkspaceTool(id, packId);
      setFolder((current) => (current ? { ...current, tools: updated.tools } : current));
    } catch (err) {
      setError(err.message);
    }
  }

  async function onRemoveTool(packId) {
    setError("");
    try {
      const updated = await removeWorkspaceTool(id, packId);
      setFolder((current) => (current ? { ...current, tools: updated.tools } : current));
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDeleteFolder() {
    if (!window.confirm(`Delete the folder ${folder.name}?`)) return;
    try {
      await deleteWorkspace(id);
      window.location.assign("/");
    } catch (err) {
      setError(err.message);
    }
  }

  if (missing) {
    return (
      <AppShell title="Folder">
        <p className="text-muted-foreground">That folder is gone.</p>
        <Link to="/" className="mt-3 inline-block text-sm text-primary">
          Back to {boardName}
        </Link>
      </AppShell>
    );
  }

  if (!folder) {
    return (
      <AppShell title="Folder">
        <p className="text-muted-foreground">Opening folder…</p>
      </AppShell>
    );
  }

  const agents = folder.agents || [];
  const crumbs = breadcrumbs(browsePath);
  const otherFolders = folders.filter((item) => item.id !== id);
  const atRoot = !browsePath;
  const empty = entries.length === 0 && !(atRoot && agents.length > 0) && !addingAgent && !addingDir;

  return (
    <AppShell
      title={folder.name}
      actions={<PeopleHere count={viewers} people={roomPeople} />}
      back={
        <Link to="/" className="shrink-0 text-xs text-muted-foreground hover:text-foreground sm:text-sm">
          {boardName}
        </Link>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex min-w-0 flex-wrap items-center gap-1 text-sm">
            <Link to="/" className="text-muted-foreground hover:text-foreground">
              {boardName}
            </Link>
            <span className="text-muted-foreground">/</span>
            {editingName ? (
              <form className="flex flex-wrap items-center gap-2" onSubmit={onRename}>
                <Input
                  autoFocus
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="h-8 max-w-[12rem]"
                />
                <Button type="submit" size="sm">
                  Save
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setTitle(folder.name);
                    setEditingName(false);
                  }}
                >
                  Cancel
                </Button>
              </form>
            ) : (
              <button
                type="button"
                className="truncate font-medium hover:underline"
                onClick={() => {
                  setAddingAgent(false);
                  setAddingDir(false);
                  loadBrowse("");
                }}
              >
                {folder.name}
              </button>
            )}
            {crumbs.slice(1).map((crumb) => (
              <span key={crumb.path} className="flex items-center gap-1">
                <span className="text-muted-foreground">/</span>
                <button
                  type="button"
                  className="truncate text-muted-foreground hover:text-foreground"
                  onClick={() => loadBrowse(crumb.path)}
                >
                  {crumb.label}
                </button>
              </span>
            ))}
          </nav>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={onShare}>
              Share
            </Button>
            {!editingName && (
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditingName(true)}>
                Rename
              </Button>
            )}
            {agents.length === 0 && (
              <Button type="button" size="sm" variant="ghost" onClick={onDeleteFolder}>
                Delete
              </Button>
            )}
            {atRoot && !addingAgent && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  setAddingDir(false);
                  setAddingAgent(true);
                }}
              >
                New agent
              </Button>
            )}
            {!addingDir && (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => {
                  setAddingAgent(false);
                  setAddingDir(true);
                }}
              >
                New folder
              </Button>
            )}
            <label className="inline-flex h-9 cursor-pointer items-center rounded-md border px-3 text-sm hover:bg-accent">
              Upload
              <input type="file" multiple hidden onChange={onUpload} />
            </label>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="overflow-hidden rounded-lg border">
          <div className="grid grid-cols-[minmax(0,1fr)_7rem_6rem] gap-2 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground sm:grid-cols-[minmax(0,1fr)_8rem_7rem_5rem]">
            <span>Name</span>
            <span className="hidden sm:inline">Type</span>
            <span>Status</span>
            <span className="text-right"> </span>
          </div>

          {addingAgent && atRoot && (
            <form
              className="flex flex-wrap items-center gap-2 border-b px-3 py-2"
              onSubmit={spawn}
            >
              <span className="text-lg" aria-hidden>
                🤖
              </span>
              <Input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Agent name"
                disabled={busy}
                className="h-8 max-w-xs"
              />
              <Button type="submit" size="sm" disabled={busy || !name.trim()}>
                {busy ? "…" : "Create"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setName("");
                  setAddingAgent(false);
                }}
              >
                Cancel
              </Button>
            </form>
          )}

          {addingDir && (
            <form className="flex flex-wrap items-center gap-2 border-b px-3 py-2" onSubmit={onMkdir}>
              <span className="text-lg" aria-hidden>
                📁
              </span>
              <Input
                autoFocus
                value={newDir}
                onChange={(e) => setNewDir(e.target.value)}
                placeholder="Folder name"
                className="h-8 max-w-xs"
              />
              <Button type="submit" size="sm" disabled={!newDir.trim()}>
                Create
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setNewDir("");
                  setAddingDir(false);
                }}
              >
                Cancel
              </Button>
            </form>
          )}

          {atRoot &&
            agents.map((agent) => (
              <div
                key={agent.id}
                className="group grid grid-cols-[minmax(0,1fr)_7rem_6rem] items-center gap-2 border-b px-3 py-2 last:border-b-0 hover:bg-accent/50 sm:grid-cols-[minmax(0,1fr)_8rem_7rem_5rem]"
              >
                <Link to={`/a/${agent.id}`} className="flex min-w-0 items-center gap-3">
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm text-white"
                    style={{ background: agent.color || "#3b82f6" }}
                  >
                    {agent.emoji}
                  </span>
                  <span className="truncate text-sm font-medium">{agent.name}</span>
                </Link>
                <span className="hidden text-xs text-muted-foreground sm:inline">Agent</span>
                <div className="text-xs">
                  <WorkState status={agent.status} />
                </div>
                <div className="flex justify-end opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  {otherFolders.length > 0 ? (
                    <select
                      aria-label={`Move ${agent.name}`}
                      className="h-7 max-w-[6rem] rounded-md border border-input bg-background px-1 text-xs"
                      defaultValue=""
                      onChange={(e) => onMove(agent, e.target.value)}
                    >
                      <option value="" disabled>
                        Move
                      </option>
                      {otherFolders.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span />
                  )}
                </div>
              </div>
            ))}

          {!atRoot && (
            <button
              type="button"
              className="grid w-full grid-cols-[minmax(0,1fr)_7rem_6rem] items-center gap-2 border-b px-3 py-2 text-left hover:bg-accent/50 sm:grid-cols-[minmax(0,1fr)_8rem_7rem_5rem]"
              onClick={() => loadBrowse(parentPath(browsePath))}
            >
              <span className="flex items-center gap-3 text-sm">
                <span className="text-lg" aria-hidden>
                  ⬆
                </span>
                ..
              </span>
              <span className="hidden text-xs text-muted-foreground sm:inline"> </span>
              <span />
              <span />
            </button>
          )}

          {entries.map((entry) => (
            <div
              key={entry.path}
              className="group grid grid-cols-[minmax(0,1fr)_7rem_6rem] items-center gap-2 border-b px-3 py-2 last:border-b-0 hover:bg-accent/50 sm:grid-cols-[minmax(0,1fr)_8rem_7rem_5rem]"
            >
              <button
                type="button"
                className="flex min-w-0 items-center gap-3 text-left"
                onClick={() => openEntry(entry)}
              >
                <span className="text-lg" aria-hidden>
                  {entry.type === "dir" ? "📁" : "📄"}
                </span>
                <span className="truncate text-sm font-medium">{entry.name}</span>
              </button>
              <span className="hidden text-xs text-muted-foreground sm:inline">
                {entry.type === "dir" ? "Folder" : "File"}
              </span>
              <span className="text-xs text-muted-foreground">
                {entry.type === "file" ? formatSize(entry.size) : "—"}
              </span>
              <div className="flex justify-end opacity-0 transition-opacity group-hover:opacity-100">
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  className="h-7 px-2"
                  onClick={() => onDeleteEntry(entry.path)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}

          {empty && (
            <div className="px-3 py-12 text-center text-sm text-muted-foreground">
              {atRoot
                ? "Empty folder. Create an agent or drop files into outputs/, rules/, or skills/."
                : "Nothing here yet."}
            </div>
          )}
        </div>

        <details className="rounded-lg border">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium">Tools</summary>
          <div className="space-y-2 border-t p-4">
            <p className="text-xs text-muted-foreground">
              Built-in packs for this folder. MCP servers are managed in{" "}
              <Link to="/settings" className="underline">
                Settings
              </Link>{" "}
              and shared across folders. Deliverables go in{" "}
              <button type="button" className="underline" onClick={() => loadBrowse("outputs")}>
                outputs/
              </button>
              .
            </p>
            {(folder.mcp_servers || []).length > 0 && (
              <div className="rounded-md border px-3 py-2 text-sm">
                <div className="mb-1 text-xs text-muted-foreground">MCP linked here</div>
                <div className="flex flex-wrap gap-2">
                  {(folder.mcp_servers || []).map((server) => (
                    <Badge key={server.id} variant="outline">
                      {server.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {catalog.map((pack) => {
              const inside = (folder.tools || []).includes(pack.id);
              return (
                <div
                  key={pack.id}
                  className="flex items-center justify-between gap-4 rounded-md border px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{pack.name}</div>
                    <div className="text-xs text-muted-foreground">{pack.detail}</div>
                  </div>
                  {inside ? (
                    <Badge variant="outline" className="shrink-0 gap-2">
                      On
                      <button type="button" className="text-muted-foreground" onClick={() => onRemoveTool(pack.id)}>
                        Remove
                      </button>
                    </Badge>
                  ) : (
                    <Button size="sm" type="button" onClick={() => onAddTool(pack.id)}>
                      Enable
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </details>

        <ShareSheet
          open={shareOpen}
          title={`Share ${folder.name}`}
          url={shareUrl}
          note={shareNote}
          copied={shareCopied}
          onCopy={copyShare}
          onClose={() => setShareOpen(false)}
        />
      </div>
    </AppShell>
  );
}
