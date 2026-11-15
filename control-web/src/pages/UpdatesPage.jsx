import { useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { applyControlUpdate, checkControlUpdates, getControlUpdates, undoControlUpdate } from "../controlApi.js";

const RESULT_WORDS = {
  updated: (r) => `Updated to version ${r.to}.`,
  went_back: (r) => `Version ${r.to} did not start, so StarFerret went back to ${r.from} on its own. Nothing was lost.`,
  restored: (r) => `Went back to version ${r.to}.`,
  failed: () => "The last update did not finish. StarFerret support can help.",
};

export default function UpdatesPage() {
  const { user } = useOutletContext();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  // Set when this browser started an update, so we keep watching while the services restart.
  const [waitingSince, setWaitingSince] = useState(0);
  const timer = useRef(null);
  const isAdmin = user?.role === "admin";
  const canCheck = isAdmin || user?.role === "operator";

  async function load() {
    try {
      const data = await getControlUpdates();
      setInfo(data);
      return data;
    } catch {
      return null; // expected for a few seconds while StarFerret restarts
    }
  }

  useEffect(() => {
    load().then((d) => !d && setError("Could not reach this Mac. Refresh to try again."));
    return () => clearTimeout(timer.current);
  }, []);

  useEffect(() => {
    if (!waitingSince) return undefined;
    let alive = true;
    async function tick() {
      const data = await load();
      const finished = data?.last?.at && data.last.at * 1000 >= waitingSince - 5000;
      const stopped = data && !data.busy.running && data.busy.error;
      if (!alive) return;
      if (finished || stopped) setWaitingSince(0);
      else timer.current = setTimeout(tick, 2000);
    }
    tick();
    return () => {
      alive = false;
      clearTimeout(timer.current);
    };
  }, [waitingSince]);

  async function onCheck() {
    setChecking(true);
    setError("");
    try {
      setInfo(await checkControlUpdates());
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  }

  async function start(action) {
    setError("");
    try {
      setInfo(await action());
      setWaitingSince(Date.now());
    } catch (err) {
      setError(err.message);
    }
  }

  if (!info) return <p className="text-sm text-muted-foreground">{error || "Checking this Mac…"}</p>;

  const working = Boolean(waitingSince);
  const last = info.last && RESULT_WORDS[info.last.result] ? RESULT_WORDS[info.last.result](info.last) : null;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            StarFerret
            {info.update_ready && !working && <Badge variant="success">Update ready</Badge>}
          </CardTitle>
          <CardDescription>
            You are on version {info.version}.
            {info.update_ready ? ` Version ${info.available.version} is available.` : ""}
            {info.available && !info.update_ready ? " That is the newest one." : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {working ? (
            <div className="space-y-1">
              <p className="font-medium">{info.busy.running ? `${info.busy.step}…` : "Restarting StarFerret…"}</p>
              <p className="text-muted-foreground">
                This takes about a minute. People are disconnected for a moment. Keep this page open.
              </p>
            </div>
          ) : !info.can_update ? (
            <p className="text-muted-foreground">
              This copy runs from source code, so it is updated by whoever set it up. A Mac set up with the StarFerret
              installer gets a one button update here.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {info.update_ready && isAdmin ? (
                  <Button onClick={() => start(applyControlUpdate)}>Update now</Button>
                ) : (
                  canCheck && (
                    <Button variant={info.available ? "secondary" : "default"} disabled={checking} onClick={onCheck}>
                      {checking ? "Checking…" : "Check for updates"}
                    </Button>
                  )
                )}
              </div>
              {info.update_ready && (
                <p className="text-muted-foreground">
                  Takes about a minute. People are disconnected for a moment. Your files, chats, people, and models are
                  kept. If the new version does not start, StarFerret goes back to this one on its own.
                </p>
              )}
              {info.update_ready && info.available.notes && (
                <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-sans text-xs text-muted-foreground">
                  {info.available.notes}
                </pre>
              )}
            </>
          )}
          {info.busy.error && !working && <p className="text-destructive">{info.busy.error}</p>}
          {error && <p className="text-destructive">{error}</p>}
          {last && !working && <p className="text-muted-foreground">{last}</p>}
        </CardContent>
      </Card>

      {info.can_go_back && isAdmin && !working && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <span>
              Something wrong after an update? Go back to version {info.previous || "before"}. Your data is kept.
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (window.confirm("Go back to the earlier version? StarFerret restarts.")) start(undoControlUpdate);
              }}
            >
              Go back
            </Button>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        LibreChat and n8n are updated by running the StarFerret installer again. Models update from the Models page.
      </p>
    </div>
  );
}
