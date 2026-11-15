import { useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import ModelSelect from "../ModelSelect.jsx";
import {
  deleteControlModel,
  getBoardOllama,
  listControlModels,
  listControlPulls,
  pullControlModel,
  setBoardDefaultModel,
  setBoardOllama,
} from "../controlApi.js";

function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${(bytes / (1024 ** 2)).toFixed(0)} MB`;
}

// Ollama's status words, said plainly.
function pullStep(pull) {
  if (pull.state === "done") return "Ready";
  if (pull.state === "failed") return "Download stopped";
  const status = pull.status || "";
  if (status.startsWith("pulling manifest") || status === "starting") return "Starting";
  if (status.startsWith("pulling")) return "Downloading";
  if (status.startsWith("verifying")) return "Checking the download";
  if (status.startsWith("writing") || status.startsWith("removing")) return "Finishing";
  if (status.startsWith("downloading")) return "Downloading";
  return "Working";
}

function PullRow({ pull }) {
  const percent = pull.total > 0 ? pull.percent : null;
  const running = pull.state === "running";
  return (
    <div className="space-y-1.5 rounded-md border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="truncate font-medium">{pull.name}</span>
        <span className={pull.state === "failed" ? "text-destructive" : "text-muted-foreground"}>
          {pullStep(pull)}
          {running && percent !== null ? ` · ${percent}%` : ""}
        </span>
      </div>
      {running && (
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-secondary"
          role="progressbar"
          aria-label={`Downloading ${pull.name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
        >
          <div
            className={percent === null ? "h-full w-1/3 animate-pulse rounded-full bg-primary" : "h-full rounded-full bg-primary"}
            style={percent === null ? undefined : { width: `${percent}%` }}
          />
        </div>
      )}
      {running && pull.total > 0 && (
        <p className="text-xs text-muted-foreground">
          {formatSize(pull.completed)} of {formatSize(pull.total)}. You can leave this page; the download keeps going.
        </p>
      )}
      {pull.state === "failed" && pull.error && (
        <p className="text-xs text-muted-foreground">{pull.error}</p>
      )}
    </div>
  );
}

export default function ModelsPage() {
  const { user } = useOutletContext();
  const [ollama, setOllamaState] = useState(null);
  const [host, setHost] = useState("localhost");
  const [models, setModels] = useState([]);
  const [pullName, setPullName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [pulls, setPulls] = useState([]);
  const runningRef = useRef(new Set());
  const canWrite = user?.role === "admin" || user?.role === "operator";
  const canDelete = user?.role === "admin";

  async function refresh() {
    setError("");
    try {
      const [status, listed] = await Promise.all([
        getBoardOllama().catch((err) => {
          setError(err.message || "Board is not answering.");
          return null;
        }),
        listControlModels().catch((err) => {
          throw err;
        }),
      ]);
      if (status) {
        setOllamaState(status);
        if (status.base_url) setHost(status.base_url);
      }
      setModels(listed.models || []);
      if (!listed.ok && listed.error) setError(listed.error);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  // Poll downloads: every 1.5 s while one runs, every 10 s otherwise (so a pull
  // started elsewhere, such as by the installer, still shows up).
  useEffect(() => {
    let stopped = false;
    let timer;
    async function tick() {
      let next = [];
      try {
        const data = await listControlPulls();
        next = data.pulls || [];
        if (!stopped) setPulls(next);
        const running = new Set(next.filter((p) => p.state === "running").map((p) => p.name));
        const finished = [...runningRef.current].some((name) => !running.has(name));
        runningRef.current = running;
        if (finished && !stopped) refresh();
      } catch {
        /* Control blipped; try again on the next tick */
      }
      if (!stopped) {
        const anyRunning = next.some((p) => p.state === "running");
        timer = setTimeout(tick, anyRunning ? 1500 : 10000);
      }
    }
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  async function connect(e) {
    e.preventDefault();
    if (!canWrite) return;
    setBusy("host");
    setError("");
    try {
      const status = await setBoardOllama({ base_url: host });
      setOllamaState(status);
      await refresh();
    } catch (err) {
      setError(err.message || "Board is not answering.");
    } finally {
      setBusy("");
    }
  }

  async function onPull(e) {
    e.preventDefault();
    if (!pullName.trim()) return;
    setBusy("pull");
    setError("");
    try {
      const result = await pullControlModel(pullName.trim());
      setPullName("");
      if (result?.pull) {
        runningRef.current = new Set([...runningRef.current, result.pull.name]);
        setPulls((current) => [result.pull, ...current.filter((p) => p.name !== result.pull.name)]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function onDelete(name) {
    if (!window.confirm(`Delete model ${name}?`)) return;
    setBusy(`del:${name}`);
    setError("");
    try {
      await deleteControlModel(name);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function onDefault(name) {
    setBusy(`def:${name}`);
    setError("");
    try {
      await setBoardDefaultModel(name);
      const status = await getBoardOllama();
      setOllamaState(status);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            Ollama
            {ollama && (
              <Badge variant={ollama.reachable ? "success" : "destructive"}>
                {ollama.reachable ? "Connected" : "Offline"}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Model library for Board and catalog apps. Host stays native; Control does not put Docker around Ollama.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={connect} className="space-y-3">
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">Host</span>
              <Input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="localhost or https://ollama.example.com"
                disabled={!canWrite}
              />
            </label>
            {canWrite && (
              <Button disabled={busy === "host"}>{busy === "host" ? "Checking…" : "Save host"}</Button>
            )}
          </form>
          {ollama?.reachable && (
            <div className="space-y-2 rounded-md border p-3">
              <div className="text-xs text-muted-foreground break-all">{ollama.base_url}</div>
              <ModelSelect />
              {Array.isArray(ollama.failover_ladder) && ollama.failover_ladder.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Failover: {ollama.failover_ladder.join(" → ")}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {canWrite && (
        <Card>
          <CardHeader>
            <CardTitle>Pull model</CardTitle>
            <CardDescription>Downloads in the background. Large models take a while on office Wi-Fi.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <form className="flex flex-col gap-2 sm:flex-row" onSubmit={onPull}>
              <Input
                value={pullName}
                onChange={(e) => setPullName(e.target.value)}
                placeholder="e.g. gemma4:latest"
              />
              <Button type="submit" disabled={busy === "pull" || !pullName.trim()}>
                {busy === "pull" ? "Starting…" : "Pull"}
              </Button>
            </form>
            {pulls.map((pull) => (
              <PullRow key={pull.name} pull={pull} />
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Installed</CardTitle>
          <CardDescription>{models.length} model{models.length === 1 ? "" : "s"} on Ollama</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {models.length === 0 && <p className="text-sm text-muted-foreground">No models listed.</p>}
          {models.map((model) => (
            <div key={model.name} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{model.name}</div>
                <div className="text-xs text-muted-foreground">{formatSize(model.size)}</div>
              </div>
              <div className="flex flex-wrap gap-1">
                {canWrite && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={Boolean(busy)}
                    onClick={() => onDefault(model.name)}
                  >
                    Use on Board
                  </Button>
                )}
                {canDelete && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={Boolean(busy)}
                    onClick={() => onDelete(model.name)}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
