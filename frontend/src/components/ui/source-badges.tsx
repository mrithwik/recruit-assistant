import { Folder, Mail } from "lucide-react";

const STYLES: Record<string, { label: string; icon: typeof Mail; className: string }> = {
  email: {
    label: "Email",
    icon: Mail,
    className: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  },
  folder: {
    label: "Folder",
    icon: Folder,
    className: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  },
};

// Makes it unambiguous when a candidate was seen through both channels
// (previously rendered as a plain comma-joined, sometimes duplicated string
// like "email, email, folder" — easy to misread as "only folder").
export function SourceBadges({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return <span className="text-zinc-400">unknown source</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      {sources.map((s) => {
        const style = STYLES[s] ?? { label: s, icon: Folder, className: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300" };
        const Icon = style.icon;
        return (
          <span key={s} className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium ${style.className}`}>
            <Icon size={10} /> {style.label}
          </span>
        );
      })}
    </span>
  );
}
