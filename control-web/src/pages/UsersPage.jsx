import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import {
  createControlUser,
  deleteControlUser,
  listControlUsers,
  patchControlUser,
} from "../controlApi.js";

const ROLES = ["admin", "operator", "viewer"];

export default function UsersPage() {
  const { user } = useOutletContext();
  const [users, setUsers] = useState([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("operator");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = user?.role === "admin";

  async function refresh() {
    setError("");
    try {
      const data = await listControlUsers();
      setUsers(data.users || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await createControlUser({ username, password, role });
      setUsername("");
      setPassword("");
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!isAdmin) {
    return (
      <p className="text-sm text-muted-foreground">
        Only admins can manage Control users. Your role: {user?.role || "unknown"}.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Add an admin</CardTitle>
          <CardDescription>
            Admins can do everything here. Operators can run apps and models. Viewers can only look. People using
            the Board do not need an account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={onCreate}>
            <Input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
            <Input
              type="password"
              placeholder="Password (8+)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ROLES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <Button type="submit" disabled={busy || password.length < 8 || !username.trim()}>
              {busy ? "Creating…" : "Create user"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-2">
        {users.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
            <div>
              <div className="font-medium">
                {item.display_name}{" "}
                <span className="text-muted-foreground">@{item.username}</span>
              </div>
              <div className="mt-1 flex gap-1">
                <Badge variant="secondary">{item.role}</Badge>
                {item.disabled && <Badge variant="destructive">Disabled</Badge>}
              </div>
            </div>
            <div className="flex flex-wrap gap-1">
              <select
                className="h-8 rounded-md border bg-background px-2 text-xs"
                value={item.role}
                onChange={async (e) => {
                  try {
                    await patchControlUser(item.id, { role: e.target.value });
                    await refresh();
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  try {
                    await patchControlUser(item.id, { disabled: !item.disabled });
                    await refresh();
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                {item.disabled ? "Enable" : "Disable"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={item.id === user.id}
                onClick={async () => {
                  if (!window.confirm(`Delete ${item.username}?`)) return;
                  try {
                    await deleteControlUser(item.id);
                    await refresh();
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        ))}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
