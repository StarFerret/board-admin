import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Badge } from "@/components/ui/badge.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import { getControlPeople } from "../controlApi.js";
import UsersPage from "./UsersPage.jsx";

function ago(iso) {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

function Stat({ value, label }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function PersonRow({ name, sub, right, badges }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 font-medium">
          <span className="truncate">{name}</span>
          {badges}
        </div>
        {sub && <div className="truncate text-xs text-muted-foreground">{sub}</div>}
      </div>
      <div className="text-xs text-muted-foreground">{right}</div>
    </div>
  );
}

export default function PeoplePage() {
  const { user } = useOutletContext();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    getControlPeople()
      .then(setData)
      .catch(() => setError("Could not load the people list. Refresh to try again."));
  }, [isAdmin]);

  if (!isAdmin) {
    return <p className="text-sm text-muted-foreground">Only admins can see who is using this Mac.</p>;
  }
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading people…</p>;

  const board = data.board.people;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Stat value={data.active_people} label={`people in the last ${data.active_days} days`} />
        <Stat value={data.online_now.length} label="on the Board right now" />
        <Stat value={board.length} label="names seen on the Board" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Board</CardTitle>
          <CardDescription>
            People on the Board type a name instead of signing in, so this list is by name. Company sign in is part of
            the paid plan and is not built yet.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.board.error && <p className="text-sm text-destructive">The Board's history could not be read.</p>}
          {board.length === 0 && !data.board.error && (
            <p className="text-sm text-muted-foreground">
              Nobody has sent a message yet. Share the Board address with your team to get started.
            </p>
          )}
          {board.map((p) => (
            <PersonRow
              key={p.name}
              name={p.name}
              badges={
                <>
                  {p.online && <Badge variant="success">Here now</Badge>}
                  {!p.active && <Badge variant="secondary">Quiet</Badge>}
                </>
              }
              sub={`${p.messages} ${p.messages === 1 ? "message" : "messages"} to ${p.agents} ${p.agents === 1 ? "agent" : "agents"}`}
              right={`Last active ${ago(p.last_active)}`}
            />
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>LibreChat</CardTitle>
          <CardDescription>
            People who chat in LibreChat sign in there, and their accounts are managed on LibreChat's own admin
            screen. They are not listed or counted on this page yet.
          </CardDescription>
        </CardHeader>
      </Card>

      <div>
        <h2 className="mb-2 text-lg font-semibold">Admins</h2>
        <p className="mb-3 text-sm text-muted-foreground">The people who can sign in to this admin panel.</p>
        <UsersPage />
      </div>
    </div>
  );
}
