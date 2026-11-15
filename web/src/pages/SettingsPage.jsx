import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Textarea } from "@/components/ui/textarea.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import AppShell from "../components/AppShell.jsx";
import {
  deleteMcpServer,
  getControlUrl,
  getHost,
  importMcpServers,
  listMcpServers,
  listWorkspaces,
  probeMcpServer,
  setMcpWorkspaces,
  setBoardName,
} from "../api.js";
import { useAgentSocket } from "../useSocket.js";
import { useVisitorName } from "../visitorContext.js";

const DEFAULT_JSON = `{
  "mcpServers": {
    "example": {
      "url": "https://mcp.example.com/sse",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}`;

export default function SettingsPage() {
  const [shareOrigin, setShareOrigin] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [mcpError, setMcpError] = useState("");
  const [mcpBusy, setMcpBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [servers, setServers] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [mcpJson, setMcpJson] = useState(DEFAULT_JSON);
  const [probeNote, setProbeNote] = useState("");
  const [boardName, setBoardNameState] = useState("Workspaces");
  const [nameBusy, setNameBusy] = useState(false);
  const [nameSaved, setNameSaved] = useState(false);
  const visitorName = useVisitorName();

  async function refresh() {
    setError("");
    try {
      const [hostInfo, mcp, listed] = await Promise.all([
        getHost().catch(() => ({ origin: window.location.origin, lan_ip: "" })),
        listMcpServers().catch(() => ({ servers: [], example: null })),
        listWorkspaces().catch(() => ({ workspaces: [] })),
      ]);
      const origin =
        hostInfo.origin ||
        (hostInfo.lan_ip ? `http://${hostInfo.lan_ip}:${window.location.port || "7410"}` : "") ||
        window.location.origin;
      setShareOrigin(origin);
      if (hostInfo.board_name) setBoardNameState(hostInfo.board_name);
      setServers(mcp.servers || []);
      if (mcp.example) setMcpJson(JSON.stringify(mcp.example, null, 2));
      setWorkspaces(listed.workspaces || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useAgentSocket(
    null,
    {
      ollama_model: ({ to }) => {
        if (to) {
          window.dispatchEvent(new CustomEvent("starferret-ollama-model", { detail: { model: to } }));
        }
      },
    },
    null,
    visitorName
  );

  async function saveBoardName(e) {
    e.preventDefault();
    const cleaned = boardName.trim();
    if (!cleaned) return;
    setNameBusy(true);
    setError("");
    setNameSaved(false);
    try {
      const saved = await setBoardName(cleaned);
      setBoardNameState(saved.name || cleaned);
      setNameSaved(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setNameBusy(false);
    }
  }

  function copyLan() {
    if (!shareOrigin) return;
    navigator.clipboard.writeText(shareOrigin);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function onImportMcp(e) {
    e.preventDefault();
    setMcpBusy(true);
    setMcpError("");
    setProbeNote("");
    try {
      const parsed = JSON.parse(mcpJson);
      const result = await importMcpServers(parsed);
      setServers(result.servers || []);
      const listed = await listMcpServers();
      setServers(listed.servers || []);
    } catch (err) {
      setMcpError(err.message || "Could not import MCP JSON");
    } finally {
      setMcpBusy(false);
    }
  }

  async function toggleWorkspace(server, workspaceId) {
    setMcpError("");
    const current = new Set(server.workspaces || []);
    if (current.has("*")) {
      current.clear();
      for (const ws of workspaces) current.add(ws.id);
    }
    if (current.has(workspaceId)) current.delete(workspaceId);
    else current.add(workspaceId);
    try {
      const updated = await setMcpWorkspaces(server.id, [...current]);
      setServers((prev) => prev.map((item) => (item.id === server.id ? updated : item)));
    } catch (err) {
      setMcpError(err.message);
    }
  }

  async function toggleAll(server) {
    setMcpError("");
    const all = (server.workspaces || []).includes("*");
    try {
      const updated = await setMcpWorkspaces(server.id, all ? [] : ["*"]);
      setServers((prev) => prev.map((item) => (item.id === server.id ? updated : item)));
    } catch (err) {
      setMcpError(err.message);
    }
  }

  async function onProbe(serverId) {
    setMcpError("");
    setProbeNote("Probing…");
    try {
      const result = await probeMcpServer(serverId);
      const names = (result.tools || []).map((t) => t.name).filter(Boolean);
      setProbeNote(
        names.length
          ? `OK — ${names.length} tools: ${names.slice(0, 8).join(", ")}${names.length > 8 ? "…" : ""}`
          : "OK — connected, but no tools listed"
      );
    } catch (err) {
      setProbeNote("");
      setMcpError(err.message);
    }
  }

  async function onDelete(serverId) {
    if (!window.confirm(`Remove MCP server ${serverId}?`)) return;
    setMcpError("");
    try {
      await deleteMcpServer(serverId);
      setServers((prev) => prev.filter((item) => item.id !== serverId));
    } catch (err) {
      setMcpError(err.message);
    }
  }

  return (
    <AppShell title="Settings">
      {!loaded ? (
        <p className="py-16 text-center text-muted-foreground">Loading settings…</p>
      ) : (
        <div className="mx-auto max-w-2xl space-y-6">
          <div>
            <h1 className="text-2xl font-semibold">Settings</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Board name, Wi‑Fi share link, and MCP servers.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Name</CardTitle>
              <CardDescription>
                What the home page is called. Shows in the header and breadcrumbs.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="flex flex-col gap-2 sm:flex-row" onSubmit={saveBoardName}>
                <Input
                  value={boardName}
                  maxLength={48}
                  onChange={(e) => {
                    setBoardNameState(e.target.value);
                    setNameSaved(false);
                  }}
                  placeholder="Workspaces"
                />
                <Button type="submit" className="shrink-0" disabled={nameBusy || !boardName.trim()}>
                  {nameBusy ? "Saving…" : nameSaved ? "Saved" : "Save name"}
                </Button>
              </form>
              {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Share on Wi‑Fi</CardTitle>
              <CardDescription>
                Folders use <code className="text-xs">/w/…</code>, agents use{" "}
                <code className="text-xs">/a/…</code>. Prefer this LAN origin — not 127.0.0.1.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs break-all">
                {shareOrigin || "…"}
              </div>
              <Button type="button" variant="secondary" className="w-full sm:w-auto" onClick={copyLan}>
                {copied ? "Copied" : "Copy LAN link"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>MCP servers</CardTitle>
              <CardDescription>
                Paste Cursor-style JSON. Servers are saved as files under{" "}
                <code className="text-xs">data/mcp/servers/</code> and can be shared with any folder.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form className="space-y-3" onSubmit={onImportMcp}>
                <Textarea
                  value={mcpJson}
                  onChange={(e) => setMcpJson(e.target.value)}
                  className="min-h-[10rem] font-mono text-xs"
                  spellCheck={false}
                />
                <Button type="submit" disabled={mcpBusy}>
                  {mcpBusy ? "Saving…" : "Add from JSON"}
                </Button>
              </form>

              {mcpError && <p className="text-sm text-destructive">{mcpError}</p>}
              {probeNote && <p className="text-sm text-muted-foreground">{probeNote}</p>}

              {servers.length === 0 ? (
                <p className="text-sm text-muted-foreground">No MCP servers yet.</p>
              ) : (
                <div className="space-y-3">
                  {servers.map((server) => {
                    const all = (server.workspaces || []).includes("*");
                    return (
                      <div key={server.id} className="space-y-3 rounded-md border p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-medium">{server.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {server.transport === "url"
                                ? server.url
                                : `${server.command} ${(server.args || []).join(" ")}`}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            <Button type="button" size="sm" variant="secondary" onClick={() => onProbe(server.id)}>
                              Test
                            </Button>
                            <Button type="button" size="sm" variant="ghost" onClick={() => onDelete(server.id)}>
                              Remove
                            </Button>
                          </div>
                        </div>
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            Share with folders
                            <Button type="button" size="sm" variant="outline" onClick={() => toggleAll(server)}>
                              {all ? "All folders ✓" : "All folders"}
                            </Button>
                          </div>
                          {!all && (
                            <div className="flex flex-wrap gap-2">
                              {workspaces.length === 0 ? (
                                <span className="text-xs text-muted-foreground">No folders yet</span>
                              ) : (
                                workspaces.map((ws) => {
                                  const on = (server.workspaces || []).includes(ws.id);
                                  return (
                                    <Button
                                      key={ws.id}
                                      type="button"
                                      size="sm"
                                      variant={on ? "default" : "outline"}
                                      onClick={() => toggleWorkspace(server, ws.id)}
                                    >
                                      {ws.name}
                                    </Button>
                                  );
                                })
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <p className="text-sm text-muted-foreground">
            <a
              className="text-primary hover:underline"
              href="#manage"
              onClick={async (e) => {
                e.preventDefault();
                window.location.href = await getControlUrl("/");
              }}
            >
              Manage this Mac
            </a>
            {" · "}
            <Link to="/" className="text-primary hover:underline">
              ← Back to board
            </Link>
          </p>
        </div>
      )}
    </AppShell>
  );
}
