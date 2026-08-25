import { useEffect, useState } from "react";
import { Loader2, SlidersHorizontal } from "lucide-react";
import { api } from "../../lib/api";
import { useToastStore } from "../../stores/toast-store";
import type { JobCriterionSelection } from "../../lib/types";

// Renders the criteria library as a checklist, with the control matching
// each criterion's field_type — a recruiter enables the criteria that apply
// to *this* job and sets its value, per requirement 2.
export function JobCriteriaPanel({ jobId }: { jobId: string }) {
  const [selections, setSelections] = useState<JobCriterionSelection[] | null>(null);
  const push = useToastStore((s) => s.push);

  useEffect(() => {
    api.getCriteriaForJob(jobId).then(setSelections).catch((e) => push(String(e), "error"));
  }, [jobId]);

  async function update(criterionId: string, enabled: boolean, value: string) {
    setSelections((prev) =>
      prev ? prev.map((s) => (s.criterion.id === criterionId ? { ...s, enabled, value } : s)) : prev,
    );
    try {
      await api.setCriterionForJob(jobId, criterionId, enabled, value);
    } catch (e) {
      push(String(e), "error");
    }
  }

  if (!selections) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-zinc-500 dark:text-zinc-400">
        <Loader2 size={14} className="animate-spin" /> Loading criteria…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        <SlidersHorizontal size={12} /> Criteria for this job
      </div>
      <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {selections.map((s) => (
          <li key={s.criterion.id} className="flex items-center gap-3 py-2.5 text-sm">
            <input
              type="checkbox"
              checked={s.enabled}
              onChange={(e) => update(s.criterion.id, e.target.checked, s.value)}
              className="h-4 w-4 shrink-0 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500"
            />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-zinc-800 dark:text-zinc-200">{s.criterion.name}</p>
              <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">{s.criterion.description}</p>
            </div>
            <div className="w-40 shrink-0">
              <CriterionValueControl
                selection={s}
                onChange={(value) => update(s.criterion.id, s.enabled, value)}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CriterionValueControl({
  selection,
  onChange,
}: {
  selection: JobCriterionSelection;
  onChange: (value: string) => void;
}) {
  const { criterion, value, enabled } = selection;
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);

  const baseClass =
    "w-full rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-700 disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200";

  if (criterion.field_type === "boolean") {
    return (
      <select
        disabled={!enabled}
        value={value || "false"}
        onChange={(e) => onChange(e.target.value)}
        className={baseClass}
      >
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }

  if (criterion.field_type === "select") {
    return (
      <select disabled={!enabled} value={value} onChange={(e) => onChange(e.target.value)} className={baseClass}>
        <option value="" disabled>
          Choose…
        </option>
        {criterion.options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }

  const isNumber = criterion.field_type === "number";

  return (
    <input
      type={isNumber ? "number" : "text"}
      disabled={!enabled}
      value={draft}
      placeholder={isNumber ? "e.g. 5" : "e.g. Java, SQL"}
      onChange={(e) => {
        // "0" already in the field + typing "20" after it produces the
        // literal string "020" — strip a leading zero the moment it's
        // no longer the whole value, same fix as lib/number-input.ts.
        const v = isNumber ? e.target.value.replace(/^0+(?=\d)/, "") : e.target.value;
        setDraft(v);
        e.target.value = v;
      }}
      onFocus={(e) => e.target.select()}
      onBlur={() => onChange(draft)}
      className={baseClass}
    />
  );
}
