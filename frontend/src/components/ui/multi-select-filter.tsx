import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

function humanize(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// A dropdown "Skills" / "Status" style filter button — click to open a
// checklist popover, click options to toggle, click outside to close. Used
// wherever a filter is "any of a set of options" (skills, employment
// status, work visa status) rather than a single value (that's SortSelect's
// job).
export function MultiSelectFilter({
  label,
  options,
  selected,
  onToggle,
  humanizeLabels = false,
}: {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
  humanizeLabels?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-sm font-medium shadow-sm transition-colors ${
          selected.length > 0
            ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-500/10 dark:text-indigo-300"
            : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        }`}
      >
        {label}
        {selected.length > 0 && (
          <span className="rounded-full bg-indigo-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {selected.length}
          </span>
        )}
        <ChevronDown size={13} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-64 w-56 overflow-y-auto rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {options.length === 0 && <p className="px-2 py-1.5 text-xs text-zinc-400">No options yet.</p>}
          {options.map((opt) => {
            const isSelected = selected.includes(opt);
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onToggle(opt)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
              >
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                    isSelected
                      ? "border-indigo-600 bg-indigo-600 text-white"
                      : "border-zinc-300 dark:border-zinc-600"
                  }`}
                >
                  {isSelected && <Check size={11} strokeWidth={3} />}
                </span>
                <span className="truncate">{humanizeLabels ? humanize(opt) : opt}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
