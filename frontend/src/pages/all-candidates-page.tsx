import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Users } from "lucide-react";
import { useCandidatesStore, CANDIDATES_PAGE_SIZE } from "../stores/candidates-store";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { SourceBadges } from "../components/ui/source-badges";
import { SortSelect } from "../components/ui/sort-select";
import { TimingBadge } from "../components/ui/timing-badge";
import type { Candidate } from "../lib/types";

type SortKey = "recent" | "oldest" | "name_asc" | "name_desc";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "recent", label: "Most recent" },
  { value: "oldest", label: "Oldest first" },
  { value: "name_asc", label: "Name A–Z" },
  { value: "name_desc", label: "Name Z–A" },
];

// Reached from the dashboard's "Total candidates" tile — a paginated browse
// of the whole candidate pool, independent of any one job (Candidate
// Results is job-scoped; this isn't). Search/sort/pagination all run
// server-side (see /candidates route + candidates-store) — this page never
// holds more than one page of candidates in memory, unlike the old version
// which loaded the entire pool up front and filtered/sliced it client-side.
export function AllCandidatesPage() {
  const { candidates, total, query, sort, page, loading, lastElapsedSeconds, fetchCandidates, setQuery, setSort, setPage } =
    useCandidatesStore();
  const push = useToastStore((s) => s.push);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => {
      fetchCandidates().catch((e) => push(String(e), "error"));
    }, 300);
    return () => clearTimeout(t);
  }, [query, sort, page]);

  const totalPages = Math.max(1, Math.ceil(total / CANDIDATES_PAGE_SIZE));

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="All Candidates"
        description="Every candidate in the pool, independent of any one job — search by name, email, or skill."
        action={
          <div className="flex items-center gap-2">
            <TimingBadge seconds={lastElapsedSeconds} />
            <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              {total} total
            </span>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name, email, or skill…" className="pl-8" />
        </div>
        <SortSelect value={sort as SortKey} onChange={(v) => setSort(v)} options={SORT_OPTIONS} />
      </div>

      {!loading && total === 0 && !query && (
        <EmptyState
          icon={<Users size={20} />}
          title="No candidates yet"
          description="Scan a local folder or connected mailbox from Scan Sources to build the pool."
        />
      )}

      {!loading && total === 0 && query && (
        <p className="py-8 text-center text-sm text-zinc-400">No candidates match "{query}".</p>
      )}

      <div className="flex flex-col gap-2">
        {candidates.map((c: Candidate) => (
          <Card
            key={c.id}
            interactive
            className="cursor-pointer p-3"
            onClick={() => navigate(`/app/candidates/${c.id}`)}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-zinc-900 dark:text-white">
                  {c.legal_first_name || c.legal_last_name ? `${c.legal_first_name} ${c.legal_last_name}`.trim() : c.email || "Unnamed candidate"}
                </p>
                <p className="mt-0.5 line-clamp-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {c.semantic_summary || "No summary yet"}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-zinc-400">
                <span>Submitted {new Date(c.date_submitted).toLocaleDateString()}</span>
                <SourceBadges sources={c.sources} />
              </div>
            </div>
            {c.skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {c.skills.slice(0, 8).map((s) => (
                  <span key={s} className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
                    {s}
                  </span>
                ))}
                {c.skills.length > 8 && <span className="text-[11px] text-zinc-400">+{c.skills.length - 8} more</span>}
              </div>
            )}
          </Card>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="text-zinc-500 dark:text-zinc-400">
            Page {page} of {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
