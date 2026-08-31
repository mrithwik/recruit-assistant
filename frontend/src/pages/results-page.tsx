import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Building2,
  CalendarPlus,
  ChevronDown,
  ChevronsDownUp,
  ChevronsUpDown,
  Clock,
  Columns3,
  Flag,
  Mail,
  Play,
  RefreshCw,
  Sparkles,
  Users,
} from "lucide-react";
import { useJobsStore } from "../stores/jobs-store";
import { useMatchesStore } from "../stores/matches-store";
import { useToastStore } from "../stores/toast-store";
import { MatchBadge } from "../components/ui/match-badge";
import { DraftEmailModal } from "../components/candidates/draft-email-modal";
import { CandidateCompareModal } from "../components/candidates/candidate-compare-modal";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { ProgressBar, useSimulatedProgress } from "../components/ui/progress-bar";
import { SourceBadges } from "../components/ui/source-badges";
import { SortSelect } from "../components/ui/sort-select";
import { TimingBadge } from "../components/ui/timing-badge";
import { onNumberChange, selectOnFocus } from "../lib/number-input";
import type { Match } from "../lib/types";

type SortKey = "best_match" | "recent" | "oldest" | "name_asc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "best_match", label: "Best match" },
  { value: "recent", label: "Most recently submitted" },
  { value: "oldest", label: "Oldest submitted" },
  { value: "name_asc", label: "Name A–Z" },
];

function matchName(m: Match): string {
  return `${m.candidate.legal_first_name} ${m.candidate.legal_last_name}`.trim() || m.candidate.email || "";
}

function sortMatches(list: Match[], sort: SortKey): Match[] {
  if (sort === "best_match") return list; // already score-sorted by the backend
  const sorted = [...list];
  switch (sort) {
    case "recent":
      return sorted.sort(
        (a, b) => new Date(b.candidate.date_submitted).getTime() - new Date(a.candidate.date_submitted).getTime(),
      );
    case "oldest":
      return sorted.sort(
        (a, b) => new Date(a.candidate.date_submitted).getTime() - new Date(b.candidate.date_submitted).getTime(),
      );
    case "name_asc":
      return sorted.sort((a, b) => matchName(a).localeCompare(matchName(b)));
  }
}

export function ResultsPage() {
  const { jobs, selectedJobId, selectJob, fetchJobs } = useJobsStore();
  const {
    matches,
    topN,
    setTopN,
    loadMatches,
    runMatching,
    flag,
    loading,
    lastElapsedSeconds,
    lastLoadWasFullRun,
    rescanMatched,
    rescanningMatched,
    rescanMatchedProgress,
    activeRescanForJobId,
    resumeRescanIfAny,
  } = useMatchesStore();
  const push = useToastStore((s) => s.push);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [draftFor, setDraftFor] = useState<Match | null>(null);
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [comparing, setComparing] = useState(false);
  const [sort, setSort] = useState<SortKey>("best_match");
  const { pct, remainingSeconds, overrun } = useSimulatedProgress(15, loading);
  const { pct: rescanPct, remainingSeconds: rescanRemaining, overrun: rescanOverrun } = useSimulatedProgress(
    Math.max(10, matches.length * 3),
    rescanningMatched,
  );

  const selectedJob = jobs.find((j) => j.id === selectedJobId);

  useEffect(() => {
    if (jobs.length === 0) fetchJobs();
    // Reattaches to an already-running "Check for updates" job if one was
    // started before a refresh/reopen (see matches-store's activeRescanJobId).
    resumeRescanIfAny().catch(() => {});
  }, []);

  useEffect(() => {
    // Arriving here via a "View results" link elsewhere (job param in the
    // URL) is an explicit request to see this job's results, so that one
    // load happens automatically. Changing the job or Top N afterward via
    // the controls on this page does not auto-reload — see handleLoad,
    // bound to the "Load results" button below.
    const fromQuery = searchParams.get("job");
    if (fromQuery && fromQuery !== selectedJobId) {
      selectJob(fromQuery);
      loadMatches(fromQuery).catch(() => {});
    }
  }, [searchParams]);

  function handleLoad() {
    if (!selectedJobId) return;
    loadMatches(selectedJobId).catch((e) => push(String(e), "error"));
  }

  function handleRescanMatched() {
    if (!selectedJobId) return;
    rescanMatched(selectedJobId).catch((e) => push(String(e), "error"));
  }

  async function handleRun() {
    if (!selectedJobId) return;
    try {
      await runMatching(selectedJobId);
      push("Matching complete", "success");
    } catch (e) {
      push(String(e), "error");
    }
  }

  async function handleFlag(matchId: string, color: "green" | "red") {
    const note = window.prompt(`Add a note for this ${color} flag (optional):`) ?? "";
    try {
      await flag(matchId, color, note);
    } catch (e) {
      push(String(e), "error");
    }
  }

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleCompare(id: string) {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const compareMatches = useMemo(() => matches.filter((m) => compareIds.has(m.id)), [matches, compareIds]);
  const sortedMatches = useMemo(() => sortMatches(matches, sort), [matches, sort]);
  // Switching the job dropdown no longer auto-reloads (see handleLoad) —
  // the currently-displayed matches can belong to a job other than the one
  // now selected. Detect that rather than silently showing mismatched
  // results under the new job's header.
  const resultsAreStale = matches.length > 0 && matches[0].job_id !== selectedJobId;

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Match Results" description="LLM-scored matches for the selected job, ranked and color-coded by fit." />

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <select
          value={selectedJobId ?? ""}
          onChange={(e) => selectJob(e.target.value)}
          className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        >
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {j.title}
            </option>
          ))}
        </select>
        <div className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
          <span className="text-zinc-500 dark:text-zinc-400">Top</span>
          <input
            type="number"
            min={1}
            max={200}
            value={topN}
            onChange={onNumberChange(setTopN)}
            onFocus={selectOnFocus}
            className="w-12 bg-transparent text-center font-medium text-zinc-800 outline-none dark:text-zinc-100"
          />
        </div>
        <Button variant="secondary" icon={<RefreshCw size={14} />} loading={loading} disabled={!selectedJobId} onClick={handleLoad}>
          Load results
        </Button>
        <Button icon={<Play size={14} />} loading={loading} disabled={!selectedJobId} onClick={handleRun}>
          Run matching
        </Button>
        <Button
          variant="secondary"
          icon={<Sparkles size={14} />}
          loading={rescanningMatched}
          disabled={!selectedJobId || matches.length === 0}
          onClick={handleRescanMatched}
          title="Bounded to just this job's matched candidates — faster than a full mailbox rescan"
        >
          Check for updates
        </Button>
        <SortSelect value={sort} onChange={setSort} options={SORT_OPTIONS} />
        {!loading && (
          <TimingBadge seconds={lastElapsedSeconds} label={lastLoadWasFullRun ? "Matched" : "Loaded"} />
        )}
      </div>

      {rescanningMatched && activeRescanForJobId === selectedJobId && (
        <div className="mb-4">
          <ProgressBar
            pct={rescanPct}
            label="Checking matched candidates for updates…"
            remainingSeconds={rescanRemaining}
            overrun={rescanOverrun}
          />
          {rescanMatchedProgress && (
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              {rescanMatchedProgress.resumes_found} candidate(s) checked — {rescanMatchedProgress.candidates_updated} updated so far
            </p>
          )}
        </div>
      )}

      {selectedJob && (
        <p className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
          {selectedJob.company && (
            <span className="flex items-center gap-1">
              <Building2 size={12} /> {selectedJob.company}
            </span>
          )}
          <span className="flex items-center gap-1">
            <CalendarPlus size={12} /> Posted {new Date(selectedJob.created_at).toLocaleDateString()}
          </span>
        </p>
      )}

      {loading && (
        <div className="mb-4">
          <ProgressBar pct={pct} label="Scoring candidates against this job…" remainingSeconds={remainingSeconds} overrun={overrun} />
        </div>
      )}

      {compareIds.size > 0 && (
        <div className="mb-3 flex items-center justify-between rounded-lg bg-indigo-50 px-3 py-2 text-sm dark:bg-indigo-500/10">
          <span className="text-indigo-700 dark:text-indigo-300">{compareIds.size} selected for comparison</span>
          <div className="flex gap-3">
            <button onClick={() => setCompareIds(new Set())} className="text-zinc-500 hover:underline dark:text-zinc-400">
              Clear
            </button>
            <button
              onClick={() => setComparing(true)}
              disabled={compareIds.size < 2}
              className="flex items-center gap-1 font-medium text-indigo-600 hover:underline disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-400"
            >
              <Columns3 size={13} /> Compare
            </button>
          </div>
        </div>
      )}

      {matches.length > 1 && (
        <div className="mb-2 flex justify-end">
          <button
            onClick={() =>
              setExpandedIds(expandedIds.size > 0 ? new Set() : new Set(matches.map((m) => m.id)))
            }
            className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-indigo-600 dark:text-zinc-400 dark:hover:text-indigo-400"
          >
            {expandedIds.size > 0 ? <ChevronsDownUp size={13} /> : <ChevronsUpDown size={13} />}
            {expandedIds.size > 0 ? "Collapse all" : "Expand all"}
          </button>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {matches.length === 0 && !selectedJobId && (
          <EmptyState
            icon={<Users size={20} />}
            title="No job selected"
            description="Add a job description first, then come back here to run matching."
          />
        )}
        {matches.length === 0 && selectedJobId && (
          <EmptyState
            icon={<Users size={20} />}
            title="No results loaded"
            description="Click “Load results” to see this job's existing matches, or “Run matching” if it hasn't been scored yet."
          />
        )}
        {resultsAreStale && (
          <EmptyState
            icon={<Users size={20} />}
            title="Switched jobs"
            description="These results are for a different job. Click “Load results” to see matches for the one now selected."
          />
        )}
        {!resultsAreStale && sortedMatches.map((m) => (
          <Card key={m.id} className="p-0">
            <div className="flex items-start justify-between gap-3 p-4">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={compareIds.has(m.id)}
                  onChange={() => toggleCompare(m.id)}
                  title="Select to compare"
                  className="mt-1 h-4 w-4 shrink-0 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
                />
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => navigate(`/app/candidates/${m.candidate.id}`)}
                      className="font-medium text-zinc-900 hover:underline dark:text-white"
                    >
                      {m.candidate.legal_first_name || m.candidate.legal_last_name
                        ? `${m.candidate.legal_first_name} ${m.candidate.legal_last_name}`.trim()
                        : m.candidate.email || "Unnamed candidate"}
                    </button>
                    <MatchBadge tier={m.tier} score={m.score} />
                  </div>
                  <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-zinc-500 dark:text-zinc-400">
                    Submitted {new Date(m.candidate.date_submitted).toLocaleDateString()} via{" "}
                    <SourceBadges sources={m.candidate.sources} />
                    <span className="text-zinc-300 dark:text-zinc-600">·</span>
                    Scored {new Date(m.matched_at).toLocaleDateString()}
                    {m.candidate.email_link && (
                      <>
                        <span className="text-zinc-300 dark:text-zinc-600">·</span>
                        <a
                          href={m.candidate.email_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-indigo-600 hover:underline dark:text-indigo-400"
                        >
                          <Mail size={11} /> Open email
                        </a>
                      </>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  onClick={() => handleFlag(m.id, "green")}
                  title="Green flag"
                  className="flex h-7 w-7 items-center justify-center rounded-md text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-500/10"
                >
                  <Flag size={14} />
                </button>
                <button
                  onClick={() => handleFlag(m.id, "red")}
                  title="Red flag"
                  className="flex h-7 w-7 items-center justify-center rounded-md text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
                >
                  <Flag size={14} />
                </button>
                <Button variant="secondary" size="sm" icon={<Mail size={13} />} onClick={() => setDraftFor(m)}>
                  Draft email
                </Button>
                <button
                  onClick={() => toggleExpanded(m.id)}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  <ChevronDown size={15} className={`transition-transform ${expandedIds.has(m.id) ? "rotate-180" : ""}`} />
                </button>
              </div>
            </div>

            {m.flags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-4 pb-3">
                {m.flags.map((f, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                      f.color === "green"
                        ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                        : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
                    }`}
                  >
                    <Flag size={11} /> {f.note || "flagged"}
                  </span>
                ))}
              </div>
            )}

            {expandedIds.has(m.id) && (
              <div className="space-y-3 border-t border-zinc-100 bg-zinc-50/60 p-4 text-sm dark:border-zinc-800 dark:bg-zinc-950/40">
                <div>
                  <p className="mb-1 font-semibold text-emerald-700 dark:text-emerald-400">Why they match</p>
                  <ul className="list-inside list-disc space-y-0.5 text-zinc-600 dark:text-zinc-400">
                    {m.reasons.matched.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
                {m.reasons.gaps.length > 0 && (
                  <div>
                    <p className="mb-1 font-semibold text-orange-700 dark:text-orange-400">Gaps</p>
                    <ul className="list-inside list-disc space-y-0.5 text-zinc-600 dark:text-zinc-400">
                      {m.reasons.gaps.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {m.missing_info.length > 0 && (
                  <div>
                    <p className="mb-1 font-semibold text-red-700 dark:text-red-400">Missing info</p>
                    <ul className="list-inside list-disc space-y-0.5 text-zinc-600 dark:text-zinc-400">
                      {m.missing_info.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {m.judge_notes && <p className="italic text-zinc-500 dark:text-zinc-400">Judge notes: {m.judge_notes}</p>}
                <p className="text-zinc-400 dark:text-zinc-500">{m.candidate.semantic_summary}</p>
                {m.candidate.history.length > 1 && (
                  <div>
                    <p className="mb-1 flex items-center gap-1 font-semibold text-zinc-600 dark:text-zinc-300">
                      <Clock size={12} /> Candidate history ({m.candidate.history.length} submissions)
                    </p>
                    <ul className="space-y-0.5 border-l border-zinc-200 pl-3 dark:border-zinc-700">
                      {m.candidate.history.map((h, i) => (
                        <li key={i} className="text-zinc-500 dark:text-zinc-400">
                          <span className="font-medium text-zinc-600 dark:text-zinc-300">
                            {new Date(h.date).toLocaleDateString()}
                          </span>{" "}
                          — {h.note}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        ))}
      </div>

      {draftFor && <DraftEmailModal match={draftFor} onClose={() => setDraftFor(null)} />}
      {comparing && <CandidateCompareModal matches={compareMatches} onClose={() => setComparing(false)} />}
    </div>
  );
}
