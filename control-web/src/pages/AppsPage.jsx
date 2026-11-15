import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { listControlApps, startControlApp, stopControlApp, updateControlApp } from "../controlApi.js";

function AppCard({ app, docker, busy, canWrite, canUpdate, onRun }) {
  const running = Boolean(app.runtime?.running);
  const native = Boolean(app.runtime?.native);
  const planned = app.status === "planned";
  const blocked = !native && !docker;
  const host = typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
  const port = (app.ports || [])[0];
  const openUrl = port ? `http://${host}:${port}` : null;

  return (
    <Card className={planned ? "opacity-70" : undefined}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {app.name}
          {planned ? (
            <Badge variant="secondary">Coming soon</Badge>
          ) : (
            <Badge variant={running ? "success" : "secondary"}>{running ? "Running" : "Stopped"}</Badge>
          )}
          {app.status === "beta" && <Badge variant="outline">Not yet verified</Badge>}
        </CardTitle>
        <CardDescription>{app.description || app.error || "—"}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {app.note && <p className="text-xs text-muted-foreground">{app.note}</p>}
        {app.runtime?.error && <p className="text-xs text-destructive">{app.runtime.error}</p>}
        {!planned && (
          <div className="flex flex-wrap items-center gap-2">
            {running && openUrl && (
              <Button asChild size="sm">
                <a href={openUrl} target="_blank" rel="noreferrer">
                  Open
                </a>
              </Button>
            )}
            {canWrite && !running && (
              <Button size="sm" disabled={Boolean(busy) || blocked} onClick={() => onRun(app.id, "start")}>
                {busy === `start:${app.id}` ? "Starting…" : "Start"}
              </Button>
            )}
            {canWrite && running && (
              <Button size="sm" variant="outline" disabled={Boolean(busy)} onClick={() => onRun(app.id, "stop")}>
                {busy === `stop:${app.id}` ? "Stopping…" : "Stop"}
              </Button>
            )}
            {canUpdate && !native && (
              <Button size="sm" variant="secondary" disabled={Boolean(busy) || blocked} onClick={() => onRun(app.id, "update")}>
                {busy === `update:${app.id}` ? "Updating…" : "Update"}
              </Button>
            )}
            {app.homepage && (
              <a className="text-xs text-muted-foreground hover:underline" href={app.homepage} target="_blank" rel="noreferrer">
                About {app.name}
              </a>
            )}
          </div>
        )}
        {busy === `start:${app.id}` && (
          <p className="text-xs text-muted-foreground">The first start downloads the app. This can take several minutes.</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function AppsPage() {
  const { user } = useOutletContext();
  const [apps, setApps] = useState(null);
  const [categories, setCategories] = useState([]);
  const [dockerState, setDockerState] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState(null);
  const canWrite = user?.role === "admin" || user?.role === "operator";
  const canUpdate = user?.role === "admin";

  async function refresh() {
    try {
      const data = await listControlApps();
      setApps(data.apps || []);
      setCategories(data.categories || []);
      setDockerState(data.docker_state || { running: Boolean(data.docker) });
    } catch (err) {
      setError("Could not load the app list. Refresh to try again.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function run(id, action) {
    const app = (apps || []).find((a) => a.id === id) || { id, name: id };
    setBusy(`${action}:${id}`);
    setProblem(null);
    try {
      if (action === "start") await startControlApp(id);
      if (action === "stop") await stopControlApp(id);
      if (action === "update") await updateControlApp(id);
    } catch (err) {
      const verb = { start: "start", stop: "stop", update: "update" }[action];
      setProblem({
        id,
        text: `${app.name} did not ${verb}. Try again, or contact StarFerret support.`,
        detail: err.message,
      });
    } finally {
      setBusy("");
      await refresh();
    }
  }

  if (!apps) {
    return <p className="text-sm text-muted-foreground">{error || "Loading apps…"}</p>;
  }

  const docker = Boolean(dockerState?.running);
  const groups = [...categories, ...new Set(apps.map((a) => a.category).filter((c) => !categories.includes(c)))]
    .map((name) => ({ name, items: apps.filter((a) => a.category === name) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Three apps on this Mac: Board, LibreChat, and n8n. Start them here, open them, and see if they are up.
        We install them. We do not rebuild them.
      </p>
      {!docker && dockerState?.message && apps.some((a) => !a.runtime?.native) && (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <span>
              {apps.filter((a) => !a.runtime?.native).map((a) => a.name).join(" and ")} was not set up by the
              StarFerret installer on this Mac, so it needs Docker to start. {dockerState.message}
            </span>
            <Button size="sm" variant="secondary" onClick={refresh}>
              Check again
            </Button>
          </CardContent>
        </Card>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {problem && (
        <p className="text-sm text-destructive">
          {problem.text}
          {problem.detail ? ` (${problem.detail})` : ""}
        </p>
      )}
      {apps.length === 0 && <p className="text-sm text-muted-foreground">No apps are in the catalog yet.</p>}
      {groups.map((group) => (
        <section key={group.name} className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">{group.name}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {group.items.map((app) => (
              <AppCard
                key={app.id}
                app={app}
                docker={docker}
                busy={busy}
                canWrite={canWrite}
                canUpdate={canUpdate}
                onRun={run}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
