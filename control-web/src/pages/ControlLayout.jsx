import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card.jsx";
import ControlShell from "../components/ControlShell.jsx";
import { cn } from "../utils/cn.js";
import {
  bootstrapAdmin,
  getControlMeta,
  loginControl,
  logoutControl,
  resetControlAdmin,
  setControlToken,
} from "../controlApi.js";
import { boardUrl } from "../ports.js";

const NAV = [
  { to: "/overview", label: "Overview" },
  { to: "/usage", label: "Usage" },
  { to: "/apps", label: "Apps" },
  { to: "/models", label: "Models" },
  { to: "/users", label: "People" },
  { to: "/machine", label: "Machine" },
  { to: "/updates", label: "Updates" },
];

// The installer opens Control with ?setup=<token> so the first admin can be made from
// another machine. Read it once and take it out of the address bar.
function takeSetupToken() {
  try {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("setup") || "";
    if (token) {
      url.searchParams.delete("setup");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
    return token;
  } catch {
    return "";
  }
}

export default function ControlLayout() {
  const [setupToken] = useState(takeSetupToken);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");
  // Why a sign in through an extension (a company login) failed. Control sends it once.
  const [signInError, setSignInError] = useState("");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [resetMode, setResetMode] = useState(false);
  const navigate = useNavigate();

  async function refresh() {
    setError("");
    try {
      const next = await getControlMeta();
      if (next.sign_in_error) setSignInError(String(next.sign_in_error).slice(0, 300));
      setMeta(next);
    } catch (err) {
      setMeta({
        bootstrap_needed: false,
        signed_in: false,
        users: null,
        error: err.message || "Control stopped answering. It restarts by itself; try again in a moment.",
        offline: true,
      });
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onAuth(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (resetMode) {
        await resetControlAdmin({ username, password, display_name: "Admin" });
        setResetMode(false);
      } else if (meta?.bootstrap_needed) {
        await bootstrapAdmin({ username, password, display_name: "Admin", token: setupToken || undefined });
      } else {
        await loginControl({ username, password });
      }
      setPassword("");
      await refresh();
      navigate("/overview");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    try {
      await logoutControl();
    } catch {
      setControlToken("");
    }
    await refresh();
  }

  const signedIn = Boolean(meta?.signed_in && meta?.user);
  const creating = Boolean(meta?.bootstrap_needed) || resetMode;
  // First admin from another machine without the setup link: explain instead of a form that will fail.
  const needsSetupLink = Boolean(meta?.bootstrap_needed) && !meta?.setup_local && !setupToken;

  return (
    <ControlShell
      actions={
        <>
          <a
            href={boardUrl(meta?.board_port)}
            className="rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground sm:text-sm"
          >
            Open the Board
          </a>
          {signedIn ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="hidden sm:inline">
                {meta.user.display_name} · {meta.user.role}
              </span>
              <Button type="button" size="sm" variant="ghost" onClick={onLogout}>
                Sign out
              </Button>
            </div>
          ) : null}
        </>
      }
    >
      {!meta ? (
        <p className="py-16 text-center text-muted-foreground">Loading Control…</p>
      ) : meta.offline ? (
        <Card className="mx-auto max-w-lg">
          <CardHeader>
            <CardTitle>Control stopped answering</CardTitle>
            <CardDescription>
              It restarts by itself. Try again in a moment.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {meta.error && <p className="text-muted-foreground">{meta.error}</p>}
            <Button type="button" onClick={refresh}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : !signedIn && needsSetupLink ? (
        <Card className="mx-auto max-w-md">
          <CardHeader>
            <CardTitle>Finish setup on the Mac</CardTitle>
            <CardDescription>
              StarFerret needs its first admin. For safety, only someone at the Mac can create it.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Open Control on the Mac running StarFerret, or use the setup link the installer printed.</p>
            <Button type="button" variant="outline" onClick={refresh}>
              Check again
            </Button>
          </CardContent>
        </Card>
      ) : !signedIn ? (
        <Card className="mx-auto max-w-md">
          <CardHeader>
            <CardTitle>
              {creating ? (resetMode ? "Reset admin" : "Create admin") : "Sign in to Control"}
            </CardTitle>
            <CardDescription>
              {creating
                ? "Choose a username and password (8+ characters). This unlocks the admin panel."
                : "Control is gated. Board guests keep using display names; only admins manage the stack."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={onAuth}>
              <label className="block space-y-1 text-sm">
                <span className="text-muted-foreground">Username</span>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
              </label>
              <label className="block space-y-1 text-sm">
                <span className="text-muted-foreground">Password</span>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={creating ? "new-password" : "current-password"}
                />
              </label>
              {(error || signInError) && <p className="text-sm text-destructive">{error || signInError}</p>}
              <Button className="w-full" disabled={busy || password.length < 8}>
                {busy ? "Working…" : creating ? (resetMode ? "Reset and sign in" : "Create admin") : "Sign in"}
              </Button>
            </form>
            {!creating && meta.sign_in_options?.length > 0 && (
              <div className="mt-4 space-y-2 border-t pt-4">
                {meta.sign_in_options.map((option) => (
                  <Button key={option.id} asChild variant="outline" className="h-11 w-full">
                    <a href={option.url}>{option.label}</a>
                  </Button>
                ))}
              </div>
            )}
            {!meta.bootstrap_needed && (
              <div className="mt-4 space-y-2 border-t pt-4 text-xs text-muted-foreground">
                <p>Forgot the password? On this Mac you can reset the local admin.</p>
                <Button
                  type="button"
                  size="sm"
                  variant={resetMode ? "secondary" : "outline"}
                  onClick={() => {
                    setResetMode((v) => !v);
                    setError("");
                    setPassword("");
                  }}
                >
                  {resetMode ? "Cancel reset" : "Reset admin on this machine"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-semibold">Control</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              How many people your AI can serve, who is using it, and what is running.
            </p>
          </div>
          <nav className="flex flex-wrap gap-1 border-b pb-2">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 items-center rounded-md px-3 text-sm sm:min-h-9",
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <Outlet context={{ user: meta.user, refreshMeta: refresh, boardHref: boardUrl(meta.board_port) }} />
        </div>
      )}
    </ControlShell>
  );
}
