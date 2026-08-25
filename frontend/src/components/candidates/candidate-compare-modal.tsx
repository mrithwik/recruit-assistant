import { X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { MatchBadge } from "../ui/match-badge";
import type { Match } from "../../lib/types";

const ROWS: { label: string; render: (m: Match) => React.ReactNode }[] = [
  { label: "Match", render: (m) => <MatchBadge tier={m.tier} score={m.score} /> },
  {
    label: "Experience",
    render: (m) => (m.candidate.experience_years ? `${m.candidate.experience_years} yrs` : "—"),
  },
  {
    label: "Skills",
    render: (m) =>
      m.candidate.skills.length ? (
        <div className="flex flex-wrap gap-1">
          {m.candidate.skills.map((s) => (
            <span key={s} className="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
              {s}
            </span>
          ))}
        </div>
      ) : (
        "—"
      ),
  },
  { label: "Education", render: (m) => m.candidate.education.join(", ") || "—" },
  { label: "Status", render: (m) => m.candidate.employment_status.replace(/_/g, " ") },
  { label: "Work authorization", render: (m) => m.candidate.work_visa_status.replace(/_/g, " ") },
  {
    label: "Matched on",
    render: (m) =>
      m.reasons.matched.length ? (
        <ul className="list-inside list-disc text-emerald-700 dark:text-emerald-400">
          {m.reasons.matched.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      ) : (
        "—"
      ),
  },
  {
    label: "Gaps",
    render: (m) =>
      m.reasons.gaps.length ? (
        <ul className="list-inside list-disc text-orange-700 dark:text-orange-400">
          {m.reasons.gaps.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      ) : (
        "—"
      ),
  },
  { label: "Submitted", render: (m) => new Date(m.candidate.date_submitted).toLocaleDateString() },
  { label: "Sources", render: (m) => m.candidate.sources.join(", ") || "—" },
];

export function CandidateCompareModal({ matches, onClose }: { matches: Match[]; onClose: () => void }) {
  const navigate = useNavigate();

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-900/40 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="animate-fade-in-up max-h-[85vh] w-full max-w-5xl overflow-auto rounded-2xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-base font-semibold text-zinc-900 dark:text-white">
            Comparing {matches.length} candidates
          </h2>
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <X size={16} />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px] border-collapse text-sm">
            <thead>
              <tr>
                <th className="w-32 shrink-0 border-b border-zinc-100 p-2 text-left text-xs font-semibold uppercase tracking-wide text-zinc-400 dark:border-zinc-800" />
                {matches.map((m) => (
                  <th key={m.id} className="min-w-[180px] border-b border-zinc-100 p-2 text-left dark:border-zinc-800">
                    <button
                      onClick={() => navigate(`/app/candidates/${m.candidate.id}`)}
                      className="font-semibold text-zinc-900 hover:underline dark:text-white"
                    >
                      {m.candidate.legal_first_name || m.candidate.legal_last_name
                        ? `${m.candidate.legal_first_name} ${m.candidate.legal_last_name}`.trim()
                        : m.candidate.email || "Unnamed candidate"}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label} className="align-top">
                  <td className="border-b border-zinc-100 p-2 text-xs font-semibold uppercase tracking-wide text-zinc-400 dark:border-zinc-800">
                    {row.label}
                  </td>
                  {matches.map((m) => (
                    <td key={m.id} className="border-b border-zinc-100 p-2 text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
                      {row.render(m)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
