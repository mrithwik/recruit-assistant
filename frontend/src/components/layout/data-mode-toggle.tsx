import { useDataModeStore, type DataMode } from "../../stores/data-mode-store";

const OPTIONS: { value: DataMode; label: string }[] = [
  { value: "all", label: "All" },
  { value: "real", label: "Real" },
  { value: "mock", label: "Mock" },
];

// Global scope switch for Candidates / Match Results / Dashboard — lets a
// recruiter who loaded a large sample dataset for testing (see the
// sample-data generator) work with just their real, actually-scanned
// candidates, or just the sample set, without deleting either.
export function DataModeToggle() {
  const dataMode = useDataModeStore((s) => s.dataMode);
  const setDataMode = useDataModeStore((s) => s.setDataMode);
  const counts = useDataModeStore((s) => s.counts);

  function countFor(value: DataMode): number | null {
    if (!counts) return null;
    if (value === "all") return counts.total;
    if (value === "real") return counts.real;
    return counts.mock;
  }

  return (
    <div
      className="flex rounded-lg bg-zinc-200/70 p-0.5 text-xs dark:bg-zinc-800"
      title="Filter candidates, match results, and dashboard stats to real scanned data, sample/mock data, or both"
    >
      {OPTIONS.map((opt) => {
        const count = countFor(opt.value);
        const active = dataMode === opt.value;
        return (
          <button
            key={opt.value}
            onClick={() => setDataMode(opt.value)}
            className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
              active
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-900 dark:text-white"
                : "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            {opt.label}
            {count !== null && <span className="ml-1 tabular-nums text-zinc-400 dark:text-zinc-500">{count}</span>}
          </button>
        );
      })}
    </div>
  );
}
