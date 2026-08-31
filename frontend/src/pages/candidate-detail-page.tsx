import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Briefcase,
  Clock,
  Code2,
  ExternalLink,
  FileText,
  Flag,
  Globe,
  GraduationCap,
  Link as LinkIcon,
  Mail,
  Phone,
  RefreshCw,
} from "lucide-react";
import { api } from "../lib/api";
import { useToastStore } from "../stores/toast-store";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { MatchBadge } from "../components/ui/match-badge";
import { SourceBadges } from "../components/ui/source-badges";
import { ProgressBar, useSimulatedProgress } from "../components/ui/progress-bar";
import type { CandidateDetail, ResumeSourceInfo, ScanResult } from "../lib/types";

const RESCAN_POLL_INTERVAL_MS = 1500;
// Scoped to one person's messages, so this is normally quick — a low
// estimate just gives the bar initial motion rather than sitting at 0%.
const RESCAN_ESTIMATED_SECONDS = 8;

function fullName(c: CandidateDetail): string {
  return `${c.legal_first_name} ${c.legal_last_name}`.trim() || c.email || "Unnamed candidate";
}

export function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const push = useToastStore((s) => s.push);
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null);
  const [sources, setSources] = useState<ResumeSourceInfo[]>([]);
  const [openSourceId, setOpenSourceId] = useState<string | null>(null);
  const [sourceText, setSourceText] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [rescanning, setRescanning] = useState(false);
  const [rescanProgress, setRescanProgress] = useState<ScanResult | null>(null);
  const { pct: rescanPct, remainingSeconds: rescanRemaining, overrun: rescanOverrun } = useSimulatedProgress(
    RESCAN_ESTIMATED_SECONDS,
    rescanning,
  );

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    Promise.all([api.getCandidate(id), api.listCandidateSources(id)])
      .then(([c, s]) => {
        setCandidate(c);
        setSources(s);
      })
      .catch((e) => push(String(e), "error"))
      .finally(() => setLoading(false));
  }, [id]);

  async function checkForUpdates() {
    if (!id) return;
    setRescanning(true);
    setRescanProgress(null);
    try {
      const job = await api.rescanCandidate(id);
      let current = job;
      while (current.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, RESCAN_POLL_INTERVAL_MS));
        current = await api.getScanJob(current.id);
        setRescanProgress(current.progress ?? null);
      }
      if (current.status === "failed") {
        push(current.error ?? "Rescan failed.", "error");
        return;
      }
      const result = current.result;
      if (!result) return;
      // candidates_updated is specifically THIS candidate's row being
      // touched — a folder-origin rescan can also pick up an unrelated new
      // candidate from the same shared folder (candidates_created), which
      // isn't news about the person being viewed here.
      if (result.candidates_updated > 0) {
        push("Found an update — refreshing this candidate's profile.", "success");
        const [c, s] = await Promise.all([api.getCandidate(id), api.listCandidateSources(id)]);
        setCandidate(c);
        setSources(s);
      } else {
        push("No updates found — nothing new since the last scan.", "success");
      }
    } catch (e) {
      push(String(e), "error");
    } finally {
      setRescanning(false);
      setRescanProgress(null);
    }
  }

  async function toggleSource(sourceId: string) {
    if (openSourceId === sourceId) {
      setOpenSourceId(null);
      return;
    }
    setOpenSourceId(sourceId);
    if (!sourceText[sourceId] && id) {
      try {
        const res = await api.getCandidateSourceText(id, sourceId);
        setSourceText((prev) => ({ ...prev, [sourceId]: res.text }));
      } catch (e) {
        push(String(e), "error");
      }
    }
  }

  if (loading) {
    return <div className="mx-auto max-w-3xl py-10 text-center text-sm text-zinc-400">Loading candidate…</div>;
  }
  if (!candidate) {
    return <div className="mx-auto max-w-3xl py-10 text-center text-sm text-zinc-400">Candidate not found.</div>;
  }

  const name = fullName(candidate);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          <ArrowLeft size={14} /> Back
        </button>
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={13} />}
          loading={rescanning}
          onClick={checkForUpdates}
          title="Re-checks this candidate's known email/folder sources for anything new"
        >
          Check for updates
        </Button>
      </div>

      {rescanning && (
        <div className="mb-4">
          <ProgressBar
            pct={rescanPct}
            label="Checking this candidate's sources…"
            remainingSeconds={rescanRemaining}
            overrun={rescanOverrun}
          />
          {rescanProgress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {rescanProgress.resumes_found} message(s) checked so far
              {rescanProgress.errors.length > 0 && ` — ${rescanProgress.errors.length} error(s)`}
            </p>
          )}
        </div>
      )}

      <Card className="mb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-white">{name}</h1>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400">
              Submitted {new Date(candidate.date_submitted).toLocaleDateString()} · via{" "}
              <SourceBadges sources={candidate.sources} />
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {candidate.employment_status !== "unknown" && (
              <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                {candidate.employment_status.replace(/_/g, " ")}
              </span>
            )}
            {candidate.work_visa_status !== "unknown" && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
                {candidate.work_visa_status.replace(/_/g, " ")}
              </span>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          {candidate.email && (
            <a
              href={`mailto:${candidate.email}`}
              className="flex items-center gap-1.5 rounded-lg bg-zinc-50 px-3 py-1.5 text-zinc-600 hover:bg-zinc-100 dark:bg-zinc-800/60 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <Mail size={13} /> {candidate.email}
            </a>
          )}
          {candidate.email_link && (
            <a
              href={candidate.email_link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-indigo-50 px-3 py-1.5 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
            >
              <Mail size={13} /> Open in inbox <ExternalLink size={11} />
            </a>
          )}
          {candidate.phone && (
            <span className="flex items-center gap-1.5 rounded-lg bg-zinc-50 px-3 py-1.5 text-zinc-600 dark:bg-zinc-800/60 dark:text-zinc-300">
              <Phone size={13} /> {candidate.phone}
            </span>
          )}
          {candidate.linkedin_url && (
            <a
              href={
                candidate.linkedin_url.startsWith("http")
                  ? candidate.linkedin_url
                  : `https://${candidate.linkedin_url}`
              }
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-blue-700 hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20"
            >
              <LinkIcon size={13} /> LinkedIn <ExternalLink size={11} />
            </a>
          )}
          {candidate.github_url && (
            <a
              href={candidate.github_url.startsWith("http") ? candidate.github_url : `https://${candidate.github_url}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-zinc-50 px-3 py-1.5 text-zinc-700 hover:bg-zinc-100 dark:bg-zinc-800/60 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <Code2 size={13} /> GitHub <ExternalLink size={11} />
            </a>
          )}
          {candidate.portfolio_url && (
            <a
              href={
                candidate.portfolio_url.startsWith("http")
                  ? candidate.portfolio_url
                  : `https://${candidate.portfolio_url}`
              }
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-1.5 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/20"
            >
              <Globe size={13} /> Portfolio <ExternalLink size={11} />
            </a>
          )}
        </div>

        {candidate.semantic_summary && (
          <p className="mt-4 rounded-lg bg-zinc-50 p-3 text-sm text-zinc-600 dark:bg-zinc-800/40 dark:text-zinc-300">
            {candidate.semantic_summary}
          </p>
        )}
      </Card>

      <Card className="mb-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-700 dark:text-zinc-200">Skills & experience</h2>
        <p className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
          {candidate.experience_years ? `${candidate.experience_years} years experience` : "Experience not detected"}
        </p>
        {candidate.skills.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {candidate.skills.map((s) => (
              <span
                key={s}
                className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300"
              >
                {s}
              </span>
            ))}
          </div>
        )}
        {candidate.education.length > 0 && (
          <div className="flex items-start gap-1.5 text-sm text-zinc-600 dark:text-zinc-300">
            <GraduationCap size={14} className="mt-0.5 shrink-0 text-zinc-400" />
            <span>{candidate.education.join(", ")}</span>
          </div>
        )}
      </Card>

      {candidate.matches.length > 0 && (
        <Card className="mb-4">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            <Briefcase size={14} /> Pipeline across jobs ({candidate.matches.length})
          </h2>
          <ul className="flex flex-col gap-2">
            {candidate.matches.map((m) => {
              const needsAttention = m.tier === "red_flagged" || m.missing_info.length > 0;
              return (
                <li key={m.match_id} className="rounded-lg bg-zinc-50 px-3 py-2 dark:bg-zinc-800/40">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <button
                        onClick={() => navigate(`/app/results?job=${m.job_id}`)}
                        className="text-sm font-medium text-zinc-700 hover:underline dark:text-zinc-200"
                      >
                        {m.job_title}
                      </button>
                      <p className="text-xs text-zinc-400">Scored {new Date(m.matched_at).toLocaleDateString()}</p>
                    </div>
                    <MatchBadge tier={m.tier} score={m.score} />
                  </div>

                  {needsAttention && (
                    <div className="mt-2 space-y-1.5 border-t border-zinc-200 pt-2 text-xs dark:border-zinc-700">
                      {m.flags
                        .filter((f) => f.color === "red")
                        .map((f, i) => (
                          <p key={i} className="flex items-start gap-1.5 text-red-600 dark:text-red-400">
                            <Flag size={12} className="mt-0.5 shrink-0" /> {f.note || "Red-flagged"}
                          </p>
                        ))}
                      {m.missing_info.length > 0 && (
                        <p className="flex items-start gap-1.5 text-amber-600 dark:text-amber-400">
                          <AlertCircle size={12} className="mt-0.5 shrink-0" /> Missing: {m.missing_info.join(", ")}
                        </p>
                      )}
                      {m.reasons.gaps.length > 0 && (
                        <p className="text-zinc-500 dark:text-zinc-400">Gaps: {m.reasons.gaps.join(", ")}</p>
                      )}
                      {m.judge_notes && <p className="italic text-zinc-400 dark:text-zinc-500">{m.judge_notes}</p>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {candidate.history.length > 0 && (
        <Card className="mb-4">
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            <Clock size={14} /> History ({candidate.history.length} submissions)
          </h2>
          <ul className="space-y-1.5 border-l border-zinc-200 pl-3 text-sm dark:border-zinc-700">
            {candidate.history.map((h, i) => (
              <li key={i} className="text-zinc-500 dark:text-zinc-400">
                <span className="font-medium text-zinc-700 dark:text-zinc-200">
                  {new Date(h.date).toLocaleDateString()}
                </span>{" "}
                — {h.note}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {sources.length > 0 && (
        <Card>
          <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            <FileText size={14} /> Source emails & documents ({sources.length})
          </h2>
          <ul className="flex flex-col gap-2">
            {sources.map((s) => (
              <li key={s.id} className="rounded-lg border border-zinc-100 dark:border-zinc-800">
                <div className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
                  <button
                    onClick={() => toggleSource(s.id)}
                    className="min-w-0 flex-1 text-left text-zinc-600 dark:text-zinc-300"
                  >
                    <span className="mr-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                      {s.origin}
                    </span>
                    {new Date(s.date_submitted).toLocaleDateString()} · {s.source_ref}
                    {s.additional_attachments.length > 0 && (
                      <span className="ml-2 text-zinc-400">
                        + {s.additional_attachments.join(", ")}
                      </span>
                    )}
                  </button>
                  <span className="flex shrink-0 items-center gap-3 text-xs">
                    {s.email_link && (
                      <a
                        href={s.email_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        <Mail size={12} /> Open email <ExternalLink size={10} />
                      </a>
                    )}
                    <button
                      onClick={() => toggleSource(s.id)}
                      className="text-indigo-600 dark:text-indigo-400"
                    >
                      {openSourceId === s.id ? "Hide text" : "View text"}
                    </button>
                  </span>
                </div>
                {openSourceId === s.id && (
                  <pre className="whitespace-pre-wrap border-t border-zinc-100 bg-zinc-50 p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950/40 dark:text-zinc-400">
                    {sourceText[s.id] ?? "Loading…"}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
