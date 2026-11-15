import { useEffect, useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { cn } from "../utils/cn.js";
import { getControlCapacity, measureControlCapacity } from "../controlApi.js";

const REFRESH_MS = 5000;

function busyWords(percent, aiOn) {
  if (!aiOn) return "Switched off";
  if (percent == null) return "Unknown";
  if (percent >= 85) return "Flat out";
  if (percent >= 40) return "Busy";
  if (percent >= 8) return "Answering";
  return "Idle";
}

function Sparkline({ values }) {
  const points = values.filter((v) => v != null);
  if (points.length < 2) return <div className="h-12" />;
  const w = 300;
  const h = 48;
  const step = w / (points.length - 1);
  const path = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - (Math.min(100, v) / 100) * (h - 2) - 1).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-12 w-full text-primary" aria-hidden="true">
      <path d={`${path} L${w},${h} L0,${h} Z`} fill="currentColor" opacity="0.12" />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function hourLabel(epoch) {
  return new Date(epoch * 1000).toLocaleTimeString(undefined, { hour: "numeric" });
}

function dayHourLabel(epoch) {
  return new Date(epoch * 1000).toLocaleString(undefined, { weekday: "short", hour: "numeric" });
}

function LoadWindow({ title, data }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{title}</div>
      {data ? (
        <>
          <div className="text-2xl font-semibold tabular-nums">Busy {Math.round(data.average_busy_percent)}% of the time</div>
          <div className="text-xs text-muted-foreground">
            {data.busiest_percent >= 1
              ? `Busiest hour: ${dayHourLabel(data.busiest_hour)}, busy ${Math.round(data.busiest_percent)}% of that hour. `
              : "Quiet so far. "}
            Most people on at once: {data.most_people}.
          </div>
        </>
      ) : (
        <div className="text-sm text-muted-foreground">Nothing recorded yet.</div>
      )}
    </div>
  );
}

function HourBars({ hours }) {
  if (!hours.length) return null;
  return (
    <div>
      <div className="flex h-20 items-end gap-1" role="img" aria-label="Share of each hour the AI spent answering, last 24 hours">
        {hours.map((h) => (
          <div
            key={h.hour}
            title={`${hourLabel(h.hour)}: answering ${Math.round(h.busy_percent)}% of the hour`}
            className={cn("min-w-0 flex-1 rounded-sm", h.busy_percent >= 80 ? "bg-red-400" : h.busy_percent >= 50 ? "bg-amber-400" : "bg-primary")}
            style={{ height: `${Math.max(3, h.busy_percent)}%` }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground">
        <span>{hourLabel(hours[0].hour)}</span>
        <span>{hourLabel(hours[hours.length - 1].hour)}</span>
      </div>
    </div>
  );
}

function niceName(name) {
  return (name || "").replace(/:latest$/, "");
}

// Plain size from how big the model is on disk. Owner asked for no technical terms here.
function sizeWord(d) {
  if (!d) return "unknown size";
  if (d.file_gb < 6) return "small";
  if (d.file_gb < 12) return "medium";
  return "large";
}

function atOnce(t) {
  return `${t.at_once}${t.at_ceiling ? "+" : ""}`;
}

function problemWords(t) {
  if (t.status === "too_big") return "Too big for this Mac";
  if (t.status === "too_slow") return "Too slow on this Mac";
  return "Test did not finish";
}

function plainStep(step) {
  const name = niceName((step || "").split(": ")[0]);
  if (/asking at once/.test(step)) return `Testing ${name}: ${step.split(": ")[1].split(",")[0]}.`;
  if (/loading it/.test(step)) return `Testing ${name}: checking it fits.`;
  return "Getting ready.";
}

function when(epoch) {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function OverviewPage() {
  const { user } = useOutletContext();
  const [cap, setCap] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);
  const canMeasure = user?.role === "admin" || user?.role === "operator";

  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const data = await getControlCapacity();
        if (alive) {
          setCap(data);
          setError((e) => (e.startsWith("Could not reach") ? "" : e));
        }
      } catch {
        if (alive) setError("Could not reach this Mac. Trying again in a few seconds.");
      }
      if (alive) timer.current = setTimeout(tick, REFRESH_MS);
    }
    tick();
    return () => {
      alive = false;
      clearTimeout(timer.current);
    };
  }, []);

  async function onMeasure(models) {
    setError("");
    try {
      setCap(await measureControlCapacity(models));
    } catch (err) {
      setError(err.message);
    }
  }

  if (!cap) return <p className="text-sm text-muted-foreground">{error || "Checking your AI…"}</p>;

  const measuring = Boolean(cap.test?.running);
  const m = cap.measured;
  const minutes = Math.max(1, Math.round((cap.busy_history.length * cap.sample_seconds) / 60));

  return (
    <div className="space-y-4">
      {cap.warnings.map((w) => (
        <Card key={w} className="border-amber-400/40">
          <CardContent className="p-4 text-sm text-amber-200">{w}</CardContent>
        </Card>
      ))}
      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="text-sm text-muted-foreground">How many people your AI can answer at the same time</div>
          {m && m.status === "ok" ? (
            <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
              <span className="text-6xl font-semibold tabular-nums">{atOnce(m)}</span>
              <span className="pb-2 text-lg text-muted-foreground">{m.at_once === 1 && !m.at_ceiling ? "person" : "people"} at once</span>
            </div>
          ) : m ? (
            <div className="text-3xl font-semibold text-amber-300">{problemWords(m)}</div>
          ) : (
            <div className="text-3xl font-semibold">Not tested yet</div>
          )}
          <p className="text-sm text-muted-foreground">
            {cap.model ? `Using ${niceName(cap.model)}, a ${sizeWord(cap.model_details)} model. ` : "No model yet. "}
            {m && m.status === "ok" && m.at_ceiling && "It may handle more. The test stops at 8. "}
            {m && m.status !== "ok" && "Pick a smaller model below. "}
            {cap.people_using} {cap.people_using === 1 ? "person has" : "people have"} used it in the last {cap.active_days} days.
          </p>
          {cap.model_details && cap.model_details.engine !== "MLX" && (
            <p className="text-sm text-amber-300">This model is not one we recommend. Pick another below.</p>
          )}
          {cap.test?.error && <p className="text-sm text-destructive">{cap.test.error}</p>}
          {canMeasure && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant={m ? "secondary" : "default"} disabled={measuring || !cap.ai_on} onClick={() => onMeasure("default")}>
                {measuring ? "Testing…" : m ? "Test again" : "Test this Mac"}
              </Button>
              {cap.models.length > 1 && (
                <Button size="sm" variant="secondary" disabled={measuring || !cap.ai_on} onClick={() => onMeasure("all")}>
                  Test every model
                </Button>
              )}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            {measuring
              ? `${plainStep(cap.test.step)} The AI will be slow for everyone until this finishes.`
              : m
                ? `Tested on this Mac ${when(m.measured_at)} by having people ask at the same time.`
                : "The test has people ask at the same time and takes a few minutes."}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your models</CardTitle>
          <CardDescription>Bigger models give better answers and serve fewer people.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {cap.models.length === 0 && <p className="text-sm text-muted-foreground">No models yet. Add one under Models.</p>}
          {cap.models.map((model) => {
            const t = model.test;
            return (
              <div key={model.name} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
                <div>
                  <div className="flex flex-wrap items-center gap-1.5 font-medium">
                    {niceName(model.name)}
                    {model.default && <Badge variant="success">In use</Badge>}
                    {model.engine !== "MLX" && <Badge variant="outline">Not recommended</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground first-letter:uppercase">{sizeWord(model)} model</div>
                </div>
                <div className="text-right">
                  {!t ? (
                    <span className="text-sm text-muted-foreground">Not tested</span>
                  ) : t.status === "ok" ? (
                    <>
                      <span className="text-2xl font-semibold tabular-nums">{atOnce(t)}</span>
                      <span className="ml-1.5 text-sm text-muted-foreground">at once</span>
                    </>
                  ) : (
                    <span className="text-sm text-amber-300">{problemWords(t)}</span>
                  )}
                </div>
              </div>
            );
          })}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button asChild size="sm" variant="secondary">
              <Link to="/models">Change model</Link>
            </Button>
            <Button asChild size="sm" variant="secondary">
              <Link to="/users">See people</Link>
            </Button>
            <Button asChild size="sm" variant="secondary">
              <Link to="/apps">Apps</Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="space-y-1 p-4">
            <div className="text-sm text-muted-foreground">On the Board right now</div>
            <div className="text-3xl font-semibold tabular-nums">{cap.online_now}</div>
            <div className="text-xs text-muted-foreground">{cap.online_now === 1 ? "person has" : "people have"} it open</div>
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardContent className="space-y-1 p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-muted-foreground">How busy the AI is</div>
              <div className="text-xs text-muted-foreground">last {minutes} min</div>
            </div>
            <div className="text-3xl font-semibold">{busyWords(cap.busy_percent, cap.ai_on)}</div>
            <Sparkline values={cap.busy_history} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>How busy it has been</CardTitle>
          <CardDescription>
            How much of the time your AI was answering people. If the busiest hour gets close to 100%, people are
            waiting and it is time for another Mac.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <LoadWindow title="Last 24 hours" data={cap.load.day} />
            <LoadWindow title="Last 7 days" data={cap.load.week} />
          </div>
          <HourBars hours={cap.load.hours} />
        </CardContent>
      </Card>
    </div>
  );
}
