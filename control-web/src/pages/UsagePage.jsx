import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { cn } from "../utils/cn.js";
import { getControlMeta, getControlUsage } from "../controlApi.js";
import { boardUrl } from "../ports.js";

const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

const number = new Intl.NumberFormat();
const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

function dayLabel(iso) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function lastActive(iso) {
  if (!iso) return "—";
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Stat({ label, value, hint }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function DailyBars({ days }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...days.map((d) => d.messages));
  const shown = hover ?? days[days.length - 1];
  return (
    <div>
      <div className="mb-3 text-sm tabular-nums">
        <span className="font-medium">{dayLabel(shown.day)}</span>
        <span className="text-muted-foreground">
          {" · "}
          {number.format(shown.messages)} {shown.messages === 1 ? "message" : "messages"}
          {" · "}
          {number.format(shown.tokens)} tokens
        </span>
      </div>
      <div
        className="flex h-32 items-stretch gap-[2px] border-b"
        role="img"
        aria-label={`Messages per day for the last ${days.length} days`}
        onMouseLeave={() => setHover(null)}
      >
        {days.map((d) => (
          <div
            key={d.day}
            className="group flex min-w-0 flex-1 cursor-default flex-col justify-end"
            onMouseEnter={() => setHover(d)}
            onClick={() => setHover(d)}
          >
            <div
              className={cn(
                "mx-auto w-full max-w-6 rounded-t bg-primary/70 group-hover:bg-primary",
                hover?.day === d.day && "bg-primary"
              )}
              style={{ height: d.messages ? `${Math.max(3, (d.messages / max) * 100)}%` : 0 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-muted-foreground">
        <span>{dayLabel(days[0].day)}</span>
        <span>{dayLabel(days[days.length - 1].day)}</span>
      </div>
    </div>
  );
}

function Table({ columns, rows, rowKey }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {columns.map((c) => (
              <th key={c.label} className={cn("px-2 py-2 font-normal", c.right && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b last:border-0">
              {columns.map((c) => (
                <td key={c.label} className={cn("px-2 py-2.5", c.right && "text-right tabular-nums")}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function UsagePage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [boardHref, setBoardHref] = useState(() => boardUrl(7410));

  async function load(range) {
    setLoading(true);
    setFailed(false);
    try {
      setData(await getControlUsage(range));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(days);
  }, [days]);

  useEffect(() => {
    getControlMeta()
      .then((meta) => setBoardHref(boardUrl(meta.board_port)))
      .catch(() => {});
  }, []);

  const totals = data?.totals;
  const empty = data && totals.messages === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center rounded-md border p-0.5 text-sm">
          {RANGES.map((r) => (
            <button
              key={r.days}
              type="button"
              onClick={() => setDays(r.days)}
              className={cn(
                "min-h-9 rounded px-3",
                days === r.days ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
        <Button type="button" size="sm" variant="outline" disabled={loading} onClick={() => load(days)}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>

      {failed ? (
        <Card>
          <CardHeader>
            <CardTitle>Usage could not be loaded</CardTitle>
            <CardDescription>
              StarFerret did not answer. Nothing is lost: usage is still being recorded. Try again in a moment.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => load(days)}>
              Try again
            </Button>
          </CardContent>
        </Card>
      ) : !data ? (
        <p className="py-8 text-sm text-muted-foreground">Loading usage…</p>
      ) : empty ? (
        <Card>
          <CardHeader>
            <CardTitle>No usage in the last {days} days</CardTitle>
            <CardDescription>
              When someone messages an agent on the Board, it shows up here: who asked, how often, and how much
              the AI worked.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <a href={boardHref}>Open the Board</a>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="People" value={number.format(totals.people)} hint="Used AI in this period" />
            <Stat label="Messages" value={number.format(totals.messages)} hint="Requests sent to agents" />
            <Stat
              label="Tokens"
              value={compact.format(totals.tokens)}
              hint="What a cloud AI service bills by"
            />
            <Stat
              label="Per person"
              value={number.format(Math.round(totals.messages / Math.max(1, totals.people)))}
              hint="Average messages each"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Messages per day</CardTitle>
            </CardHeader>
            <CardContent>
              <DailyBars days={data.by_day} />
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>People</CardTitle>
                <CardDescription>
                  Names are what each person typed when they opened the Board. They are not verified accounts.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table
                  rowKey={(p) => p.name}
                  rows={data.people}
                  columns={[
                    { label: "Name", render: (p) => p.name },
                    { label: "Messages", right: true, render: (p) => number.format(p.messages) },
                    { label: "Tokens", right: true, render: (p) => compact.format(p.tokens) },
                    { label: "Last active", right: true, render: (p) => lastActive(p.last_active) },
                  ]}
                />
              </CardContent>
            </Card>

            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Folders</CardTitle>
                  <CardDescription>Where the work is happening.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table
                    rowKey={(f) => f.id || f.name}
                    rows={data.folders}
                    columns={[
                      {
                        label: "Folder",
                        render: (f) =>
                          f.id && f.name !== "Deleted folder" ? (
                            <Link className="text-primary hover:underline" to={`/w/${f.id}`}>
                              {f.name}
                            </Link>
                          ) : (
                            f.name
                          ),
                      },
                      { label: "People", right: true, render: (f) => number.format(f.people) },
                      { label: "Messages", right: true, render: (f) => number.format(f.messages) },
                    ]}
                  />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>AI models</CardTitle>
                  <CardDescription>Which model answered. All of them run on your own Macs.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table
                    rowKey={(m) => m.name}
                    rows={data.models}
                    columns={[
                      { label: "Model", render: (m) => m.name },
                      { label: "Messages", right: true, render: (m) => number.format(m.messages) },
                      { label: "Tokens", right: true, render: (m) => compact.format(m.tokens) },
                    ]}
                  />
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}

      <p className="text-xs text-muted-foreground">
        This counts the Board only. Usage from the chat and automation apps is not counted yet.
      </p>
    </div>
  );
}
