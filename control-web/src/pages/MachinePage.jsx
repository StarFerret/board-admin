import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import {
  getBoardLogs,
  getControlMachine,
  startBoardProcess,
  stopBoardProcess,
} from "../controlApi.js";

export default function MachinePage() {
  const { user } = useOutletContext();
  const [snap, setSnap] = useState(null);
  const [log, setLog] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const isAdmin = user?.role === "admin";

  async function refresh() {
    setError("");
    try {
      const data = await getControlMachine();
      setSnap(data);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function loadLogs() {
    try {
      const data = await getBoardLogs();
      setLog(data.log || "(empty)");
    } catch (err) {
      setError(err.message);
    }
  }

  if (!snap && !error) {
    return <p className="text-sm text-muted-foreground">Loading machine…</p>;
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Board
              <Badge variant={snap?.board?.running ? "success" : "destructive"}>
                {snap?.board?.running ? "Up" : "Down"}
              </Badge>
            </CardTitle>
            <CardDescription>
              Board is a sibling process. Control can start/stop a managed instance without sharing Docker
              privileges with agents.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="break-all text-xs text-muted-foreground">{snap?.board?.url}</div>
            <div className="text-xs text-muted-foreground">
              managed={String(Boolean(snap?.board?.managed))} · pid={snap?.board?.pid || "—"} · port=
              {snap?.board?.port}
            </div>
            {isAdmin && (
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={busy === "start"}
                  onClick={async () => {
                    setBusy("start");
                    try {
                      await startBoardProcess();
                      await refresh();
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setBusy("");
                    }
                  }}
                >
                  Start Board
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy === "stop"}
                  onClick={async () => {
                    setBusy("stop");
                    try {
                      await stopBoardProcess();
                      await refresh();
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setBusy("");
                    }
                  }}
                >
                  Stop managed Board
                </Button>
                <Button size="sm" variant="ghost" onClick={loadLogs}>
                  Tail log
                </Button>
              </div>
            )}
            {log && (
              <pre className="max-h-48 overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-[10px]">
                {log}
              </pre>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Ollama
              <Badge variant={snap?.ollama?.reachable ? "success" : "destructive"}>
                {snap?.ollama?.reachable ? "Reachable" : "Offline"}
              </Badge>
            </CardTitle>
            <CardDescription>{snap?.ollama?.base_url}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {snap?.ollama?.models?.length || 0} models · {snap?.ollama?.error || "OK"}
          </CardContent>
        </Card>


        <Card>
          <CardHeader>
            <CardTitle>Machine</CardTitle>
            <CardDescription>Best-effort host facts (Apple Silicon first)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-muted-foreground">
            <div>LAN IP: {snap?.lan_ip}</div>
            <div>CPU: {snap?.machine?.cpu || "—"}</div>
            <div>RAM: {snap?.machine?.ram_gb ? `${snap.machine.ram_gb} GB` : "—"}</div>
            <div>
              Docker: {snap?.docker?.available ? "yes" : "no"} · Compose:{" "}
              {snap?.docker?.compose ? "yes" : "no"}
            </div>
          </CardContent>
        </Card>
      </div>
      <Button type="button" variant="secondary" size="sm" onClick={refresh}>
        Refresh
      </Button>
    </div>
  );
}
