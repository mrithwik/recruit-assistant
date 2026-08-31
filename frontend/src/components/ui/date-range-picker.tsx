import { useEffect, useState } from "react";
import { CalendarRange } from "lucide-react";

// Date-range control shared by Scan Sources, Match Results, and Search
// History (requirement 2.8): days/weeks/years presets + custom range.
const PRESETS = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "12 weeks", days: 84 },
  { label: "1 year", days: 365 },
];

function toDateInputValue(iso?: string): string {
  return iso ? iso.slice(0, 10) : "";
}

// Controlled by the parent's store rather than holding its own "which
// preset is active" state — this component used to reset to "nothing
// selected" every time it remounted (e.g. navigating to a different tab and
// back), even though the underlying date range was still applied. See
// scan-store's dateRangeLabel for why that state now lives one level up.
export function DateRangePicker({
  start,
  end,
  activeLabel,
  onChange,
}: {
  start?: string;
  end?: string;
  activeLabel?: string;
  onChange: (start?: string, end?: string, label?: string) => void;
}) {
  const [customStart, setCustomStart] = useState(activeLabel === "custom" ? toDateInputValue(start) : "");
  const [customEnd, setCustomEnd] = useState(activeLabel === "custom" ? toDateInputValue(end) : "");

  // Keeps the custom-range inputs in sync if the active range changes from
  // outside this component (e.g. reattaching persisted state on load).
  useEffect(() => {
    if (activeLabel === "custom") {
      setCustomStart(toDateInputValue(start));
      setCustomEnd(toDateInputValue(end));
    }
  }, [activeLabel, start, end]);

  function applyPreset(days: number, label: string) {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    onChange(startDate.toISOString(), endDate.toISOString(), label);
  }

  function applyCustom() {
    onChange(
      customStart ? new Date(customStart).toISOString() : undefined,
      customEnd ? new Date(customEnd).toISOString() : undefined,
      "custom",
    );
  }

  function clear() {
    setCustomStart("");
    setCustomEnd("");
    onChange(undefined, undefined, undefined);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <CalendarRange size={15} className="text-zinc-400" />
      <div className="flex rounded-lg bg-zinc-100 p-0.5 dark:bg-zinc-800">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => applyPreset(p.days, p.label)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              activeLabel === p.label
                ? "bg-white text-indigo-700 shadow-sm dark:bg-zinc-900 dark:text-indigo-300"
                : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1.5 text-xs">
        <input
          type="date"
          value={customStart}
          onChange={(e) => setCustomStart(e.target.value)}
          className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        />
        <span className="text-zinc-400">–</span>
        <input
          type="date"
          value={customEnd}
          onChange={(e) => setCustomEnd(e.target.value)}
          className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        />
        <button
          onClick={applyCustom}
          className="rounded-md border border-zinc-200 px-2 py-1 font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Apply
        </button>
      </div>
      {activeLabel ? (
        <button onClick={clear} className="text-xs text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400">
          Clear
        </button>
      ) : (
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
          All time (default — nothing selected scans everything)
        </span>
      )}
    </div>
  );
}
