import { Link } from "react-router-dom";
import {
  ArrowRight,
  FolderSearch,
  Mail,
  ShieldCheck,
  Sparkles,
  SlidersHorizontal,
  Users,
} from "lucide-react";

const FEATURES = [
  {
    icon: FolderSearch,
    title: "Scan folders and email, together",
    description:
      "Point it at local resume folders and connected mailboxes — either works alone, or run both. Everything converges into one deduplicated candidate pool.",
  },
  {
    icon: Sparkles,
    title: "LLM-scored matches, with a judge pass",
    description:
      "Two-stage matching narrows a full candidate pool to a shortlist, then scores it against your job description — with a second LLM reviewing borderline calls.",
  },
  {
    icon: Users,
    title: "Color-coded results you can act on",
    description:
      "Ranked, tiered results with match reasons, missing info, and green/red flags. Draft an outreach email straight from a match.",
  },
  {
    icon: SlidersHorizontal,
    title: "Criteria you control",
    description:
      "Standard job-board filters out of the box, plus custom criteria you add — with the choice to rescan everything or reuse what's already there.",
  },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-indigo-600 text-white">
            <Sparkles size={16} strokeWidth={2.5} />
          </div>
          <span className="font-display text-base font-semibold text-zinc-900 dark:text-white">
            Recruit Assistant
          </span>
        </div>
        <Link
          to="/login"
          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
        >
          Sign in <ArrowRight size={14} />
        </Link>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="py-20 text-center sm:py-28">
          <div className="mx-auto mb-6 inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
            <ShieldCheck size={13} /> Local-first — your data never leaves your machine
          </div>
          <h1 className="mx-auto max-w-3xl font-display text-4xl font-semibold tracking-tight text-zinc-900 sm:text-5xl dark:text-white">
            Find the right candidate, faster — without leaving your desk.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base text-zinc-500 dark:text-zinc-400">
            Scan resumes from email and local folders, match them against your job
            descriptions with LLM scoring, and draft outreach — all running locally,
            all under your control.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500"
            >
              Get started <ArrowRight size={15} />
            </Link>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-5 pb-24 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
                  <Icon size={17} />
                </div>
                <h3 className="mb-1.5 font-medium text-zinc-900 dark:text-white">{f.title}</h3>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">{f.description}</p>
              </div>
            );
          })}
        </section>

        <section className="mb-24 flex flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50 px-6 py-10 text-center dark:border-zinc-800 dark:bg-zinc-900/60">
          <Mail size={20} className="text-zinc-400" />
          <h2 className="font-display text-xl font-semibold text-zinc-900 dark:text-white">
            Read-only email access, revocable any time
          </h2>
          <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">
            Gmail and Outlook connect via OAuth with read-only mail scope. Access tokens live in
            your OS keychain — never in a database or config file.
          </p>
        </section>
      </main>

      <footer className="border-t border-zinc-100 py-6 text-center text-xs text-zinc-400 dark:border-zinc-900">
        Recruit Assistant — runs locally, your data stays with you.
      </footer>
    </div>
  );
}
