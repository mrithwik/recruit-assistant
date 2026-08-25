import { ArrowUpDown } from "lucide-react";

export interface SortOption<T extends string> {
  value: T;
  label: string;
}

export function SortSelect<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: SortOption<T>[];
}) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-2 text-sm shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <ArrowUpDown size={13} className="shrink-0 text-zinc-400" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className="bg-transparent font-medium text-zinc-700 outline-none dark:text-zinc-200"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
