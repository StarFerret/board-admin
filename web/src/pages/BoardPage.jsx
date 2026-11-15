import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import AppShell from "../components/AppShell.jsx";
import ShareSheet from "../components/ShareSheet.jsx";
import {
  createWorkspace,
  deleteAgent,
  getControlUrl,
  getHost,
  getOllama,
  listAgents,
  listWorkspaces,
  restoreAgent,
  shareWorkspace,
} from "../api.js";
import PeopleHere from "../PeopleHere.jsx";
import { useAgentSocket } from "../useSocket.js";
import { useVisitorName } from "../visitorContext.js";

function workingAgents(workspaces) {
  const items = [];
  for (const ws of workspaces) {
    for (const agent of ws.agents || []) {
      if (agent.status === "running") {
        items.push({ ...agent, workspace_name: ws.name, workspace_id: ws.id });
      }
    }
  }
  return items;
}

export default function BoardPage() {
  const [ollama, setOllamaState] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [workspaces, setWorkspaces] = useState([]);
  const [archived, setArchived] = useState([]);
  const [folderName, setFolderName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [boardViewers, setBoardViewers] = useState(1);
  const [boardPeople, setBoardPeople] = useState([]);
  const [shareOrigin, setShareOrigin] = useState("");
  const [boardName, setBoardName] = useState("Workspaces");
  const [menu, setMenu] = useState(null);
  const [share, setShare] = useState(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [boardCopied, setBoardCopied] = useState(false);
  const visitorName = useVisitorName();
  const navigate = useNavigate();

  async function refresh() {
    setError("");
    try {
      const [status, listed, filed, hostInfo] = await Promise.all([
        getOllama().catch(() => null),
        listWorkspaces().catch(() => ({ workspaces: [] })),
        listAgents(true).catch(() => ({ agents: [] })),
        getHost().catch(() => ({ origin: window.location.origin })),
      ]);
      if (status) setOllamaState(status);
      setWorkspaces(listed.workspaces || []);
      setArchived(filed.agents || []);
      setShareOrigin(hostInfo.origin || window.location.origin);
      if (hostInfo.board_name) setBoardName(hostInfo.board_name);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    function closeMenu() {
      setMenu(null);
    }
    window.addEventListener("click", closeMenu);
    return () => window.removeEventListener("click", closeMenu);
  }, []);

  async function openShare(ws) {
    setMenu(null);
    setError("");
    try {
      const result = await shareWorkspace(ws.id);
      const url = result.url || `${shareOrigin || window.location.origin}/w/${ws.id}`;
      setShare({ name: ws.name, url });
      setShareCopied(false);
    } catch (err) {
      const url = `${shareOrigin || window.location.origin}/w/${ws.id}`;
      setShare({ name: ws.name, url, note: err.message });
    }
  }

  function copyShare() {
    if (!share?.url) return;
    navigator.clipboard.writeText(share.url);
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 1500);
  }

  function copyBoard() {
    const url = `${shareOrigin || window.location.origin}/`;
    navigator.clipboard.writeText(url);
    setBoardCopied(true);
    setTimeout(() => setBoardCopied(false), 1500);
  }

  useEffect(() => {
    refresh();
  }, []);

  useAgentSocket(
    null,
    {
      presence: ({ board, count, people }) => {
        if (board) {
          setBoardViewers(count || 1);
          setBoardPeople(people || []);
        }
      },
      board_name: ({ name }) => {
        if (name) setBoardName(name);
      },
      ollama_model: ({ to }) => {
        if (to) {
          window.dispatchEvent(new CustomEvent("starferret-ollama-model", { detail: { model: to } }));
          setOllamaState((current) => (current ? { ...current, model: to } : current));
        }
      },
      workspace: (folder) => {
        setWorkspaces((prev) => {
          if (prev.some((item) => item.id === folder.id)) {
            return prev.map((item) =>
              item.id === folder.id ? { ...item, ...folder, agents: folder.agents || item.agents } : item
            );
          }
          return [...prev, { ...folder, agents: folder.agents || [] }];
        });
      },
      workspace_deleted: ({ id }) => {
        setWorkspaces((prev) => prev.filter((item) => item.id !== id));
      },
      agent: (agent) => {
        setWorkspaces((prev) => {
          const stripped = prev.map((ws) => ({
            ...ws,
            agents: (ws.agents || []).filter((item) => item.id !== agent.id),
          }));
          if (agent.archived || !agent.workspace_id) return stripped;
          const index = stripped.findIndex((ws) => ws.id === agent.workspace_id);
          if (index < 0) {
            return [
              ...stripped,
              {
                id: agent.workspace_id,
                name: agent.workspace_name || "Shared",
                agents: [agent],
              },
            ];
          }
          const current = stripped[index];
          const next = stripped.slice();
          next[index] = {
            ...current,
            name: agent.workspace_name || current.name,
            agents: [agent, ...current.agents],
          };
          return next;
        });
        if (agent.archived) {
          setArchived((prev) => [agent, ...prev.filter((item) => item.id !== agent.id)]);
        } else {
          setArchived((prev) => prev.filter((item) => item.id !== agent.id));
        }
      },
      agent_deleted: ({ id }) => {
        setWorkspaces((prev) =>
          prev.map((ws) => ({ ...ws, agents: (ws.agents || []).filter((item) => item.id !== id) }))
        );
        setArchived((prev) => prev.filter((item) => item.id !== id));
      },
      status: ({ id, status }) => {
        setWorkspaces((prev) =>
          prev.map((ws) => ({
            ...ws,
            agents: (ws.agents || []).map((item) => (item.id === id ? { ...item, status } : item)),
          }))
        );
      },
    },
    null,
    visitorName
  );

  async function makeFolder(e) {
    e.preventDefault();
    const label = folderName.trim();
    if (!label) return;
    setBusy(true);
    setError("");
    try {
      const created = await createWorkspace(label);
      setFolderName("");
      setCreating(false);
      navigate(`/w/${created.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  async function onRestore(agent) {
    setError("");
    try {
      const updated = await restoreAgent(agent.id);
      setArchived((prev) => prev.filter((a) => a.id !== agent.id));
      setWorkspaces((prev) => {
        const index = prev.findIndex((ws) => ws.id === updated.workspace_id);
        if (index < 0) {
          return [
            ...prev,
            { id: updated.workspace_id, name: updated.workspace_name || "Shared", agents: [updated] },
          ];
        }
        const next = prev.slice();
        next[index] = {
          ...next[index],
          agents: [updated, ...(next[index].agents || []).filter((item) => item.id !== updated.id)],
        };
        return next;
      });
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDelete(agent) {
    if (!window.confirm(`Delete ${agent.name}? Shared workspace files stay for the other agents.`)) return;
    setError("");
    try {
      await deleteAgent(agent.id);
      setArchived((prev) => prev.filter((a) => a.id !== agent.id));
      setWorkspaces((prev) =>
        prev.map((ws) => ({ ...ws, agents: (ws.agents || []).filter((item) => item.id !== agent.id) }))
      );
    } catch (err) {
      setError(err.message);
    }
  }

  const offline = loaded && ollama && ollama.reachable === false;
  const active = workingAgents(workspaces);

  return (
    <AppShell
      title={boardName}
      actions={<PeopleHere count={boardViewers} people={boardPeople} />}
      banner={
        !offline && loaded && active.length > 0 ? (
          <div className="border-b bg-emerald-500/5">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-3 py-2 sm:px-4">
              <span className="text-xs text-emerald-300 sm:text-sm">Working now</span>
              {active.map((agent) => (
                <Link
                  key={agent.id}
                  className="text-xs underline-offset-4 hover:underline sm:text-sm"
                  to={`/a/${agent.id}`}
                >
                  {agent.emoji} {agent.name}
                  <span className="text-muted-foreground"> · {agent.workspace_name}</span>
                </Link>
              ))}
            </div>
          </div>
        ) : null
      }
    >
      {!loaded ? (
        <p className="py-16 text-center text-muted-foreground">Loading…</p>
      ) : (
        <div className="space-y-4">
          {offline && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Ollama offline</CardTitle>
                <CardDescription>Connect a host and pick a model in Control.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  type="button"
                  onClick={async () => {
                    window.location.href = await getControlUrl("/models");
                  }}
                >
                  Open Control
                </Button>
              </CardContent>
            </Card>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{boardName}</span>
            </nav>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" variant="secondary" onClick={copyBoard}>
                {boardCopied ? "Copied" : "Copy link"}
              </Button>
              {!creating ? (
                <Button type="button" size="sm" onClick={() => setCreating(true)}>
                  New folder
                </Button>
              ) : (
                <form className="flex flex-wrap items-center gap-2" onSubmit={makeFolder}>
                  <Input
                    autoFocus
                    value={folderName}
                    onChange={(e) => setFolderName(e.target.value)}
                    placeholder="Untitled folder"
                    disabled={busy}
                    className="h-9 w-48"
                  />
                  <Button type="submit" size="sm" disabled={busy || !folderName.trim()}>
                    {busy ? "…" : "Create"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => {
                      setCreating(false);
                      setFolderName("");
                    }}
                  >
                    Cancel
                  </Button>
                </form>
              )}
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {workspaces.length === 0 && !creating ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16 text-center">
              <div className="text-4xl opacity-60">📁</div>
              <p className="text-sm text-muted-foreground">No folders yet</p>
              <Button type="button" onClick={() => setCreating(true)}>
                New folder
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {workspaces.map((ws) => {
                const agents = ws.agents || [];
                const running = agents.some((item) => item.status === "running");
                return (
                  <Link
                    key={ws.id}
                    to={`/w/${ws.id}`}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setMenu({
                        id: ws.id,
                        name: ws.name,
                        x: e.clientX,
                        y: e.clientY,
                      });
                    }}
                    className={
                      running
                        ? "group relative flex flex-col items-start gap-2 rounded-lg border border-emerald-500/40 bg-card p-3 transition-colors hover:bg-accent"
                        : "group relative flex flex-col items-start gap-2 rounded-lg border bg-card p-3 transition-colors hover:bg-accent"
                    }
                  >
                    <span className="text-3xl leading-none" aria-hidden>
                      📁
                    </span>
                    <span className="w-full truncate text-sm font-medium">{ws.name}</span>
                    <span className="w-full truncate text-xs text-muted-foreground">
                      {agents.length === 0
                        ? "Folder"
                        : `${agents.length} ${agents.length === 1 ? "agent" : "agents"}`}
                    </span>
                    <button
                      type="button"
                      className="absolute right-2 top-2 rounded-md border bg-background/90 px-2 py-0.5 text-[11px] opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        openShare(ws);
                      }}
                    >
                      Share
                    </button>
                  </Link>
                );
              })}
            </div>
          )}

          {menu && (
            <div
              className="fixed z-50 min-w-[10rem] overflow-hidden rounded-md border bg-card py-1 shadow-md"
              style={{ left: menu.x, top: menu.y }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => {
                  setMenu(null);
                  navigate(`/w/${menu.id}`);
                }}
              >
                Open
              </button>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => openShare({ id: menu.id, name: menu.name })}
              >
                Share link…
              </button>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => {
                  const url = `${shareOrigin || window.location.origin}/w/${menu.id}`;
                  navigator.clipboard.writeText(url);
                  setMenu(null);
                }}
              >
                Copy link
              </button>
            </div>
          )}

          <ShareSheet
            open={Boolean(share)}
            title={share ? `Share ${share.name}` : "Share"}
            url={share?.url || ""}
            note={share?.note}
            copied={shareCopied}
            onCopy={copyShare}
            onClose={() => setShare(null)}
          />

          {archived.length > 0 && (
            <details className="rounded-lg border">
              <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
                Archive ({archived.length})
              </summary>
              <div className="space-y-2 border-t p-4">
                {archived.map((agent) => (
                  <div key={agent.id} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="truncate">
                      {agent.emoji} {agent.name}
                    </span>
                    <span className="flex gap-2">
                      <Button variant="ghost" size="sm" type="button" onClick={() => onRestore(agent)}>
                        Restore
                      </Button>
                      <Button variant="ghost" size="sm" type="button" onClick={() => onDelete(agent)}>
                        Delete
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </AppShell>
  );
}
