import { useEffect, useRef, useState } from "react";
import { ChevronDown, TrendingUp } from "lucide-react";

// Min/max years-of-experience filter, same popover pattern as
// MultiSelectFilter — a dedicated component rather than reusing it since
// this filter is a numeric range, not a set of discrete options.
export function ExperienceRangeFilter({
  min,
  max,
  ceiling,
  onChange,
}: {
  min: number | undefined;
  max: number | undefined;
  ceiling: number;
  onChange: (min: number | undefined, max: number | undefined) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draftMin, setDraftMin] = useState(min?.toString() ?? "");
  const [draftMax, setDraftMax] = useState(max?.toString() ?? "");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const active = min !== undefined || max !== undefined;

  function apply() {
    onChange(draftMin ? Number(draftMin) : undefined, draftMax ? Number(draftMax) : undefined);
    setOpen(false);
  }

  function clear() {
    setDraftMin("");
    setDraftMax("");
    onChange(undefined, undefined);
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-sm font-medium shadow-sm transition-colors ${
          active
            ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-500/10 dark:text-indigo-300"
            : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        }`}
      >
        <TrendingUp size={13} />
        Experience
        {active && (
          <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {min ?? 0}–{max ?? ceiling}y
          </span>
        )}
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-56 rounded-lg border border-zinc-200 bg-white p-3 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              max={ceiling}
              placeholder="Min"
              value={draftMin}
              onChange={(e) => setDraftMin(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-900 outline-none focus:border-indigo-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
            />
            <span className="text-zinc-400">–</span>
            <input
              type="number"
              min={0}
              max={ceiling}
              placeholder="Max"
              value={draftMax}
              onChange={(e) => setDraftMax(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-900 outline-none focus:border-indigo-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white"
            />
          </div>
          <p className="mt-1.5 text-[11px] text-zinc-400">years — up to {ceiling}</p>
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={clear} className="text-xs font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300">
              Clear
            </button>
            <button
              type="button"
              onClick={apply}
              className="rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-indigo-500"
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
