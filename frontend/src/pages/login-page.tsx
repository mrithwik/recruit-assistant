import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { AlertTriangle, KeyRound, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { useAuthStore } from "../stores/auth-store";
import { Input, Label } from "../components/ui/input";
import { Button } from "../components/ui/button";

export function LoginPage() {
  const navigate = useNavigate();
  const { status, setupComplete, checkAuthStatus, login, register } = useAuthStore();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (setupComplete === null) checkAuthStatus().catch(() => {});
  }, []);

  if (status === "authenticated") {
    return <Navigate to="/app/dashboard" replace />;
  }

  const isFirstRun = setupComplete === false;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (isFirstRun) {
        await register(email, password, name, remember);
      } else {
        await login(email, password, remember);
      }
      navigate("/app/dashboard");
    } catch (err) {
      setError(String(err).replace(/^Error:\s*/, ""));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <Sparkles size={18} strokeWidth={2.5} />
          </div>
          <h1 className="font-display text-xl font-semibold text-zinc-900 dark:text-white">
            {setupComplete === null ? "Recruit Assistant" : isFirstRun ? "Create your account" : "Welcome back"}
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {setupComplete === null
              ? "Checking setup status…"
              : isFirstRun
                ? "This is a one-time setup — the first account becomes the only local account."
                : "Sign in to your local Recruit Assistant instance."}
          </p>
        </div>

        {setupComplete === null ? (
          <div className="flex justify-center py-8">
            <Loader2 className="animate-spin text-zinc-400" size={20} />
          </div>
        ) : (
          <form onSubmit={submit} autoComplete="on" className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            {isFirstRun && (
              <div className="mb-4">
                <Label>Name</Label>
                <Input name="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
              </div>
            )}
            <div className="mb-4">
              <Label>Email</Label>
              <Input
                type="email"
                name="username"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="mb-2">
              <Label>Password</Label>
              <Input
                type="password"
                name="password"
                autoComplete={isFirstRun ? "new-password" : "current-password"}
                required
                minLength={isFirstRun ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isFirstRun ? "At least 8 characters" : "••••••••"}
              />
            </div>

            <label className="flex items-center gap-2 py-1 text-sm text-zinc-600 dark:text-zinc-300">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
              />
              Keep me signed in on this device
            </label>

            {error && (
              <p className="mt-3 flex items-start gap-1.5 rounded-lg bg-red-50 p-2.5 text-xs text-red-700 dark:bg-red-500/10 dark:text-red-300">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {error}
              </p>
            )}

            <Button type="submit" className="mt-5 w-full justify-center" icon={<KeyRound size={14} />} loading={submitting}>
              {isFirstRun ? "Create account & sign in" : "Sign in"}
            </Button>

            <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-zinc-400">
              <ShieldCheck size={11} /> Password is hashed (PBKDF2) before storage — never kept in plain text.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
