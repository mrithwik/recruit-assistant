import { useState } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { Card } from "../ui/card";

// Shown on Email Access when Google/Microsoft OAuth credentials aren't set
// in .env yet — replaces what used to happen if you clicked Connect anyway:
// the backend correctly 400s, but connect/* is a plain <a href> browser
// navigation (can't carry the app's auth header, so it can't be a normal
// fetch() call either), so that error just rendered as raw unstyled JSON
// instead of reaching this app's own UI at all.
const GOOGLE_STEPS = [
  <>
    <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer" className="underline">
      Google Cloud Console
    </a>{" "}
    → new project → APIs &amp; Services → enable the <strong>Gmail API</strong>.
  </>,
  <>
    OAuth consent screen → External → add scopes <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">gmail.readonly</code> and{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">userinfo.email</code>.
  </>,
  <>
    <strong>Add yourself as a test user</strong> on that same consent-screen page — skip this and Google will
    reject sign-in from your own account with a confusing error.
  </>,
  <>
    Credentials → OAuth client ID (type: Web application) → redirect URI:{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">http://localhost:8000/api/v1/email-accounts/callback/google</code>
  </>,
  <>
    Put the client ID/secret in <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">.env</code> as{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">GOOGLE_OAUTH_CLIENT_ID</code> /{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">GOOGLE_OAUTH_CLIENT_SECRET</code>, then restart the backend.
  </>,
];

const MICROSOFT_STEPS = [
  <>
    <a href="https://portal.azure.com/" target="_blank" rel="noreferrer" className="underline">
      Azure Portal
    </a>{" "}
    → App registrations → new registration.
  </>,
  <>
    API permissions → Microsoft Graph → <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">Mail.Read</code> (delegated).
  </>,
  <>Certificates &amp; secrets → new client secret (this is MS_OAUTH_CLIENT_SECRET).</>,
  <>
    Redirect URI (Authentication, type "Web"):{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">http://localhost:8000/api/v1/email-accounts/callback/microsoft</code>
  </>,
  <>
    Put the client ID/secret in <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">.env</code> as{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">MS_OAUTH_CLIENT_ID</code> /{" "}
    <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">MS_OAUTH_CLIENT_SECRET</code>, then restart the backend.
  </>,
];

function StepList({ steps }: { steps: React.ReactNode[] }) {
  return (
    <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-600 dark:text-zinc-300">
      {steps.map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ol>
  );
}

export function OAuthSetupGuide({ googleConfigured, microsoftConfigured }: { googleConfigured: boolean; microsoftConfigured: boolean }) {
  const [openProvider, setOpenProvider] = useState<"google" | "microsoft" | null>(null);

  if (googleConfigured && microsoftConfigured) return null;

  return (
    <Card className="mb-6 border-amber-200 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-500/5">
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
            {!googleConfigured && !microsoftConfigured
              ? "Gmail and Outlook aren't set up yet"
              : !googleConfigured
                ? "Gmail isn't set up yet"
                : "Outlook isn't set up yet"}
          </p>
          <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-300">
            Connecting an account needs an OAuth app registered with the provider first — a one-time setup, not
            something this app can do for you. Steps below.
          </p>

          <div className="mt-3 flex flex-col gap-2">
            {!googleConfigured && (
              <div>
                <button
                  onClick={() => setOpenProvider(openProvider === "google" ? null : "google")}
                  className="flex items-center gap-1 text-sm font-medium text-amber-700 dark:text-amber-400"
                >
                  <ChevronDown size={14} className={`transition-transform ${openProvider === "google" ? "rotate-180" : ""}`} />
                  Gmail setup steps
                </button>
                {openProvider === "google" && <div className="mt-2 pl-1">{<StepList steps={GOOGLE_STEPS} />}</div>}
              </div>
            )}
            {!microsoftConfigured && (
              <div>
                <button
                  onClick={() => setOpenProvider(openProvider === "microsoft" ? null : "microsoft")}
                  className="flex items-center gap-1 text-sm font-medium text-amber-700 dark:text-amber-400"
                >
                  <ChevronDown size={14} className={`transition-transform ${openProvider === "microsoft" ? "rotate-180" : ""}`} />
                  Outlook setup steps
                </button>
                {openProvider === "microsoft" && <div className="mt-2 pl-1">{<StepList steps={MICROSOFT_STEPS} />}</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
