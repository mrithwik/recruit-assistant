import { useState } from "react";
import { CalendarRange } from "lucide-react";

// Date-range control shared by Scan Sources, Candidate Results, and Search
// History (requirement 2.8): days/weeks/years presets + custom range.
const PRESETS = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "12 weeks", days: 84 },
  { label: "1 year", days: 365 },
];

export function DateRangePicker({
  onChange,
}: {
  onChange: (start?: string, end?: string) => void;
}) {
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [active, setActive] = useState<string>("");

  function applyPreset(days: number, label: string) {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - days);
    setActive(label);
    onChange(start.toISOString(), end.toISOString());
  }

  function applyCustom() {
    setActive("custom");
    onChange(customStart ? new Date(customStart).toISOString() : undefined, customEnd ? new Date(customEnd).toISOString() : undefined);
  }

  function clear() {
    setActive("");
    setCustomStart("");
    setCustomEnd("");
    onChange(undefined, undefined);
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
              active === p.label
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
      {active ? (
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
