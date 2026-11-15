import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Textarea } from "@/components/ui/textarea.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import PeopleHere from "../PeopleHere.jsx";
import { useAgentSocket } from "../useSocket.js";
import { useVisitorName } from "../visitorContext.js";
import WorkState from "../WorkState.jsx";
import { cn } from "../utils/cn.js";
import {
  archiveAgent,
  createSchedule,
  deleteAgent,
  deleteFile,
  deleteSchedule,
  getAgent,
  getHost,
  listSchedules,
  patchAgent,
  restoreAgent,
  sendMessage,
  uploadFiles,
  stopAgent,
} from "../api.js";

function whenLabel(iso) {
  if (!iso) return "done";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function toolSummary(group) {
  const names = group.map((msg) => (msg.meta && msg.meta.name) || "tool");
  const unique = [...new Set(names)];
  if (unique.length === 1) return `Tool · ${unique[0]}`;
  if (unique.length <= 3) return `Tools · ${unique.join(", ")}`;
  return `Tools · ${unique.slice(0, 2).join(", ")} +${unique.length - 2}`;
}

function ChatTranscript({ messages, thinking, stream, agentStatus, liveTool, bottomRef }) {
  const nodes = [];
  let index = 0;
  while (index < messages.length) {
    const msg = messages[index];
    if (msg.role === "tool") {
      const group = [];
      while (index < messages.length && messages[index].role === "tool") {
        group.push(messages[index]);
        index += 1;
      }
      nodes.push(
        <details key={`tools-${group[0].id}`} className="fold tool-fold rounded-md border bg-muted/30 p-2 mb-2">
          <summary className="cursor-pointer font-medium text-sm">{toolSummary(group)}</summary>
          {group.map((toolMsg) => (
            <div key={toolMsg.id} className="bubble tool p-3 rounded-lg bg-secondary/50 border-l-4 border-l-primary">
              <div className="text-sm font-medium mb-1 text-muted-foreground">{(toolMsg.meta && toolMsg.meta.name) || ""}</div>
        <pre className="whitespace-pre-wrap font-mono text-xs">{toolMsg.content}</pre>
            </div>
          ))}
        </details>
      );
      continue;
    }
    nodes.push(
      <div
        key={msg.id}
        className={cn(
          "max-w-[min(100%,42rem)] rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap",
          msg.role === "user" ? "ml-auto bg-primary/15" : "bg-card"
        )}
      >
        {msg.role === "user" && msg.meta?.author && (
          <div className="mb-1 text-xs font-medium text-muted-foreground">{msg.meta.author}</div>
        )}
        {msg.role === "user" && msg.meta?.steer && <Badge className="mb-1" variant="outline">Steer</Badge>}
        {msg.role === "user" && msg.meta?.interrupt && <Badge className="mb-1" variant="destructive">Interrupt</Badge>}
        {msg.meta?.thinking && (
          <details className="mb-2 text-xs text-muted-foreground">
            <summary>Thinking</summary>
            <p className="mt-1 whitespace-pre-wrap">{msg.meta.thinking}</p>
          </details>
        )}
        {msg.content}
      </div>
    );
    index += 1;
  }

  return (
    <div className={cn("messages space-y-2 mb-4", {
      "flex": true,
      "flex-col": true
    })}>
      {nodes}
      {liveTool && (
        <details className="fold tool-fold rounded-md border bg-muted/30 p-2">
          <summary className="cursor-pointer font-medium text-sm">Tool · {liveTool.name}…</summary>
          <div className="bubble tool p-3 rounded-lg bg-secondary/50 border-l-4 border-l-primary">
            <div className="mb-1 text-sm text-muted-foreground">{liveTool.name}</div>
            {liveTool.status === "done" && liveTool.output ? liveTool.output.slice(0, 200) : "Running…"}
          </div>
        </details>
      )}
      {thinking && (
        <details className="thinking rounded-md border bg-muted/30 p-2 my-2">
          <summary className="cursor-pointer font-medium">Thinking</summary>
          {thinking}
        </details>
      )}
      {stream && <div className={cn("bubble assistant token text-xs overflow-x-auto whitespace-pre-wrap", {
        "font-mono": true,
        "bg-accent/30": true
      })}>{stream}</div>}
      {agentStatus === "running" && !stream && (
        <div className="bubble assistant token">
          <WorkState status="running" />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

export default function AgentPage() {
  const { id } = useParams();
  const [agent, setAgent] = useState(null);
  const [messages, setMessages] = useState([]);
  const [files, setFiles] = useState([]);
  const [draft, setDraft] = useState("");
  const [notes, setNotes] = useState("");
  const [prompt, setPrompt] = useState("");
  const [stream, setStream] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [missing, setMissing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [viewers, setViewers] = useState(1);
  const [roomPeople, setRoomPeople] = useState([]);
  const visitorName = useVisitorName();
  const [thinking, setThinking] = useState("");
  const [goalState, setGoalState] = useState(null);
  const [effort, setEffort] = useState(12);
  const [schedules, setSchedules] = useState([]);
  const [jobText, setJobText] = useState("");
  const [jobMode, setJobMode] = useState("once");
  const [jobWhen, setJobWhen] = useState("");
  const [jobEvery, setJobEvery] = useState(60);
  const [shareOrigin, setShareOrigin] = useState("");
  const [sideOpen, setSideOpen] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(min-width: 768px)").matches : false
  );
  const [liveTool, setLiveTool] = useState(null);
  const [uploadFolder, setUploadFolder] = useState("");
  const bottom = useRef(null);

  useEffect(() => {
    setLoadError("");
    setMissing(false);
    setAgent(null);
    getHost()
      .then((host) => setShareOrigin(host.origin || window.location.origin))
      .catch(() => setShareOrigin(window.location.origin));
    getAgent(id)
      .then((data) => {
        setAgent(data.agent);
        setMessages(data.messages || []);
        setFiles(data.files || []);
        setNotes(data.agent.notes || "");
        setPrompt(data.agent.system_prompt || "");
        setEffort(data.agent.effort || 12);
        document.title = `${data.agent.name} · StarFerret`;
        const link = document.querySelector("link[rel='icon']") || document.createElement("link");
        link.rel = "icon";
        link.href = `/api/agents/${id}/favicon.svg`;
        document.head.appendChild(link);
      })
      .catch((err) => {
        const msg = err.message || "";
        if (msg.includes("Not found") || msg.includes("404")) {
          setMissing(true);
        } else {
          setLoadError(msg || "Could not load this agent.");
        }
      });
    listSchedules(id).then(setSchedules).catch(() => {});
  }, [id]);

  useAgentSocket(id, {
    token: ({ text, reset }) => setStream((current) => (reset ? "" : current + (text || ""))),
    thinking: ({ text, reset }) => setThinking((current) => (reset ? text || "" : current + (text || ""))),
    goal: (payload) =>
      setGoalState((current) =>
        payload.status === "stopping" ? { ...(current || {}), status: "stopping" } : payload
      ),
    message: (msg) => {
      setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]));
      if (msg.role === "assistant") {
        setStream("");
        setThinking("");
      }
    },
    files: ({ files: next }) => setFiles(next || []),
    agent: (next) => {
      setAgent(next);
      setNotes(next.notes || "");
      setPrompt(next.system_prompt || "");
      if (next.effort) setEffort(next.effort);
    },
    workspace: (next) => {
      setAgent((a) => (a && a.workspace_id === next.id ? { ...a, workspace_name: next.name } : a));
    },
    agent_deleted: () => setMissing(true),
    status: ({ status }) => {
      setAgent((a) => (a ? { ...a, status } : a));
      if (status !== "running") setGoalState((current) => (current ? { ...current, status: "done" } : current));
    },
    presence: ({ board, count, people }) => {
      if (!board) {
        setViewers(count || 1);
        setRoomPeople(people || []);
      }
    },
    error: ({ message }) => {
      const text = String(message || "");
      if (/harness|traceback|ollama|500|11434|internal server/i.test(text)) return;
      setError(text);
    },
    ollama_model: ({ to }) => {
      if (to) {
        window.dispatchEvent(new CustomEvent("starferret-ollama-model", { detail: { model: to } }));
      }
    },
    schedules: (items) => setSchedules(items || []),
    tool: (payload) => {
      if (payload.status === "running") {
        setLiveTool(payload);
      } else if (payload.status === "done") {
        setLiveTool(null);
      }
    },
  }, agent?.workspace_id, visitorName);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stream, thinking, liveTool]);

  async function onStop() {
    setError("");
    setGoalState((current) => ({ ...(current || {}), status: "stopping" }));
    try {
      await stopAgent(id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function submitDraft(mode) {
    if (!draft.trim()) return;
    const text = draft.trim();
    setDraft("");
    setError("");
    const running = agent?.status === "running";
    if (mode === "send" || mode === "interrupt" || !running) {
      setStream("");
      setThinking("");
    }
    if (mode === "send" || mode === "interrupt" || !running) {
      setGoalState({ goal: "Reading the request…", step: 0, max: Number(effort) || 12, status: "extracting" });
    }
    if (mode === "send" || mode === "interrupt" || !running) {
      setAgent((current) => (current ? { ...current, status: "running" } : current));
    }
    try {
      await sendMessage(id, text, visitorName, mode);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onSend(e) {
    e.preventDefault();
    await submitDraft("send");
  }

  async function onUpload(e) {
    const picked = e.target.files;
    if (!picked?.length) return;
    try {
      const result = await uploadFiles(id, picked, uploadFolder.trim());
      setFiles(result.files || []);
    } catch (err) {
      setError(err.message);
    } finally {
      e.target.value = "";
    }
  }

  async function saveEffort(value) {
    const next = Math.max(1, Math.min(50, Number(value) || 12));
    setEffort(next);
    try {
      const updated = await patchAgent(id, { effort: next });
      setAgent(updated);
    } catch (err) {
      setError(err.message);
    }
  }

  async function addSchedule(e) {
    e.preventDefault();
    const instruction = jobText.trim();
    if (!instruction) return;
    const body = { instruction, mode: jobMode };
    if (jobMode === "once") {
      if (!jobWhen) {
        setError("Pick a time.");
        return;
      }
      body.run_at = new Date(jobWhen).toISOString();
    } else {
      body.every_minutes = Number(jobEvery) || 60;
    }
    try {
      await createSchedule(id, body);
      setJobText("");
      setSchedules(await listSchedules(id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeSchedule(scheduleId) {
    try {
      await deleteSchedule(id, scheduleId);
      setSchedules(await listSchedules(id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveContext(e) {
    e.preventDefault();
    try {
      const updated = await patchAgent(id, { notes, system_prompt: prompt });
      setAgent(updated);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDelete(path) {
    try {
      const result = await deleteFile(id, path);
      setFiles(result.files || []);
    } catch (err) {
      setError(err.message);
    }
  }

  const shareUrl = `${shareOrigin || window.location.origin}/a/${id}`;

  async function onArchive() {
    try {
      const updated = await archiveAgent(id);
      setAgent(updated);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onRestore() {
    try {
      const updated = await restoreAgent(id);
      setAgent(updated);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDeleteAgent() {
    if (!window.confirm(`Delete ${agent.name}? Shared workspace files stay for the other agents.`)) return;
    try {
      await deleteAgent(id);
      window.location.assign("/");
    } catch (err) {
      setError(err.message);
    }
  }

  function copyLink() {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (loadError) {
    return (
      <div className="page">
        <p className={cn("error text-destructive", {
          "font-medium": true
        })}>{loadError}</p>
        <p className={cn("muted mt-2 text-sm", {
          "text-muted-foreground": true,
          "text-center": true
        })}>
          On another device on the same Wi‑Fi, open this Mac&apos;s LAN address (shown as the LAN button on
          the board) — not 127.0.0.1. Allow Python through the firewall for port 7410.
        </p>
        <Link to="/" className={cn("underline hover:text-primary mt-4 inline-block", {
          "text-sm": true
        })}>Back to board</Link>
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <p>No agent at this link.</p>
        <Link to="/" className={cn("underline hover:text-primary mt-4 inline-block", {
          "text-sm": true
        })}>Back to board</Link>
      </div>
    );
  }

  if (!agent) return <div className="page">Loading…</div>;

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col overflow-hidden bg-background">
      <header className="sticky top-0 z-10 shrink-0 border-b bg-card/95 backdrop-blur">
        <div className="flex items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4 sm:py-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <Link to="/" className="shrink-0 text-xs text-muted-foreground hover:text-foreground sm:text-sm">
              Board
            </Link>
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm"
              style={{ background: agent.color }}
            >
              {agent.emoji}
            </div>
            <strong className="truncate text-sm sm:text-base">{agent.name}</strong>
            <WorkState status={agent.status} />
          </div>
          <div className="flex shrink-0 items-center gap-1 sm:gap-2">
            <PeopleHere count={viewers} people={roomPeople} />
            {shareOrigin && (
              <Button variant="outline" size="sm" type="button" onClick={copyLink}>
                {copied ? "Copied" : "Share"}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              type="button"
              className="md:hidden"
              onClick={() => setSideOpen((open) => !open)}
            >
              {sideOpen ? "Chat" : "More"}
            </Button>
            <Link
              to="/settings"
              className="hidden rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground sm:inline"
            >
              Settings
            </Link>
          </div>
        </div>
        <div className="flex items-center gap-2 overflow-x-auto border-t px-3 py-1.5 text-xs sm:px-4">
          <Link
            className="shrink-0 rounded-full bg-secondary px-2.5 py-1 text-muted-foreground"
            to={agent.workspace_id ? `/w/${agent.workspace_id}` : "/"}
          >
            {agent.workspace_name || "Folder"}
          </Link>
          {agent.archived ? (
            <>
              <Button variant="ghost" size="sm" type="button" onClick={onRestore}>
                Restore
              </Button>
              <Button variant="ghost" size="sm" type="button" onClick={onDeleteAgent}>
                Delete
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="sm" type="button" onClick={onArchive}>
              Archive
            </Button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <section
          className={cn(
            "flex min-h-0 min-w-0 flex-1 flex-col border-border bg-muted/20 md:border-r",
            sideOpen ? "hidden md:flex" : "flex"
          )}
        >
          <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
            <ChatTranscript
              messages={messages}
              thinking={thinking}
              stream={stream}
              agentStatus={agent.status}
              liveTool={liveTool}
              bottomRef={bottom}
            />
            {goalState && goalState.status !== "done" && (
              <div className="my-2 rounded-md border-l-4 border-l-primary bg-accent/20 p-3 text-sm">
                <div>
                  {goalState.status === "extracting"
                    ? "Reading the request…"
                    : goalState.status === "stopping"
                    ? "Stopping…"
                    : `Goal, try ${goalState.step || 0} of ${goalState.max || effort}: ${goalState.status}`}
                </div>
                <div className="font-medium break-words">{goalState.goal}</div>
              </div>
            )}
            {error && (
              <div className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}
          </div>
          {agent.archived ? (
            <div className="shrink-0 border-t p-4 text-center text-sm text-muted-foreground">
              Archived. Restore it to send another message.
            </div>
          ) : (
            <form className="shrink-0 border-t bg-background p-3" onSubmit={onSend}>
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={`Message ${agent.name}…`}
                className="min-h-[64px] text-sm"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend(e);
                  }
                }}
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button type="submit">Send</Button>
                {agent.status === "running" && (
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={goalState?.status === "stopping"}
                    onClick={onStop}
                  >
                    Stop
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={agent.status !== "running"}
                  onClick={() => submitDraft("steer")}
                >
                  Steer
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={agent.status !== "running"}
                  onClick={() => submitDraft("interrupt")}
                >
                  Interrupt
                </Button>
              </div>
            </form>
          )}
        </section>

        <aside
          className={cn(
            "min-h-0 w-full flex-col overflow-y-auto border-border bg-card md:w-[min(20rem,34vw)] md:border-l",
            sideOpen ? "flex flex-1 md:flex-none" : "hidden md:flex"
          )}
        >
          <div className="flex items-center justify-between gap-2 border-b p-3">
            <div className="truncate text-sm text-muted-foreground">{agent.tagline}</div>
            <Button
              variant="ghost"
              size="sm"
              type="button"
              className="hidden md:inline-flex"
              onClick={() => setSideOpen((open) => !open)}
            >
              {sideOpen ? "Fold" : "Side"}
            </Button>
          </div>

          <div className="space-y-6 p-3 sm:p-4">
            <p className="text-sm leading-relaxed text-muted-foreground">
              Share this agent with anyone on your Wi‑Fi. Uploads land in{" "}
              <Link className="text-primary hover:underline" to={agent.workspace_id ? `/w/${agent.workspace_id}` : "/"}>
                {agent.workspace_name || "this folder"}
              </Link>
              .
            </p>

            <div className="space-y-6">
                <div className="space-y-2">
                  <strong className="text-sm font-medium">How hard</strong>
                  <span className="muted text-xs">Each reply and each tool call uses one try. Hard is 50.</span>
                  <div className="row flex gap-2 mt-2">
                    <Button variant="ghost" size="sm" onClick={() => saveEffort(8)}>Light 8</Button>
                    <Button variant="ghost" size="sm" onClick={() => saveEffort(20)}>Medium 20</Button>
                    <Button variant="ghost" size="sm" onClick={() => saveEffort(50)}>Hard 50</Button>
                  </div>
                  <Input
                    className="plain text-xs"
                    type="number"
                    min="1"
                    max="50"
                    value={effort}
                    onChange={(e) => setEffort(e.target.value)}
                    onBlur={() => saveEffort(effort)}
                  />
                </div>

                <form className="space-y-2" onSubmit={addSchedule}>
                  <strong className="text-sm font-medium">Schedule</strong>
                  <span className="muted text-xs">It reads the request, extracts a goal, and works until the try limit.</span>
                  <Input
                    className="plain text-xs min-h-[60px] resize-none"
                    value={jobText}
                    onChange={(e) => setJobText(e.target.value)}
                    placeholder="What should it do?"
                  />
                  <div className="row flex gap-2">
                    <label className="text-xs">
                      <input type="radio" checked={jobMode === "once"} onChange={() => setJobMode("once")} /> Once
                    </label>
                    <label className="text-xs">
                      <input type="radio" checked={jobMode === "every"} onChange={() => setJobMode("every")} /> Every
                    </label>
                  </div>
                  {jobMode === "once" ? (
                    <Input
                      className="plain text-xs"
                      type="datetime-local"
                      value={jobWhen}
                      onChange={(e) => setJobWhen(e.target.value)}
                    />
                  ) : (
                    <Input
                      className="plain text-xs"
                      type="number"
                      min="1"
                      max="10080"
                      value={jobEvery}
                      onChange={(e) => setJobEvery(e.target.value)}
                      placeholder="Minutes between runs"
                    />
                  )}
                  <Button variant="default" size="sm" className="w-full" type="submit">Schedule</Button>
                  {schedules.length === 0 && <div className="muted text-xs">Nothing scheduled.</div>}
                  {schedules.map((item) => (
                    <div key={item.id} className="file p-2 rounded-md border bg-secondary/30">
                      <div>
                        <div className="text-xs">{item.instruction}</div>
                        <div className="muted text-[10px]">
                          {item.mode === "every" ? `Every ${item.every_minutes} min` : "Once"}
                          {item.enabled ? ` · ${whenLabel(item.next_run_at)}` : " · finished"}
                        </div>
                      </div>
                      <Button variant="ghost" size="sm" type="button" onClick={() => removeSchedule(item.id)}>×</Button>
                    </div>
                  ))}
                </form>

                <details className="fold">
                  <summary className="cursor-pointer font-medium text-sm">Context</summary>
                  <div className="space-y-3 p-3 border-t mt-4">
                    <div className="space-y-2">
                      <label className="text-xs font-medium">System prompt</label>
                      <Input
                        className="plain text-xs min-h-[80px] resize-none"
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-xs font-medium">Pinned notes</label>
                      <Input
                        className="plain text-xs min-h-[80px] resize-none"
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                      />
                    </div>
                    <Button variant="default" size="sm" className="w-full" type="submit" form="#saveContextForm">Save context</Button>
                  </div>
                </details>

                <div className="folder-files space-y-3 border-t pt-4">
                  <div className="row flex justify-between items-center">
                    <strong className="text-sm font-medium">Folder files</strong>
                    <label className="ghost cursor-pointer px-2 py-1 rounded-md border hover:bg-accent transition-colors text-xs border-dashed border-2">
                      Upload
                      <input type="file" multiple hidden onChange={onUpload} />
                    </label>
                  </div>
                  <p className="muted text-xs leading-relaxed">
                    Like a Google Drive folder: upload here and every agent in{" "}
                    <Link to={agent.workspace_id ? `/w/${agent.workspace_id}` : "/"}>
                      {agent.workspace_name || "this folder"}
                    </Link>{" "}
                    can read and edit the same files.
                  </p>
                  <Input
                    className="plain text-xs"
                    value={uploadFolder}
                    onChange={(e) => setUploadFolder(e.target.value)}
                    placeholder="Subfolder inside this folder, optional"
                  />
                  <div className="files space-y-1">
                    {files.filter((f) => f.type === "file").length === 0 && (
                      <div className="muted text-xs">No files yet. Upload to fill this folder.</div>
                    )}
                    {files
                      .filter((f) => f.type === "file")
                      .map((f) => (
                        <div key={f.path} className="file p-2 rounded-md border flex justify-between items-center">
                          <a href={`/api/agents/${id}/files/${encodeURIComponent(f.path)}`} className="text-xs text-primary hover:underline truncate">{f.path}</a>
                          <Button variant="ghost" size="sm" onClick={() => onDelete(f.path)}>×</Button>
                        </div>
                      ))}
                  </div>
                </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}