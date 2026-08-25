import { CheckCircle2, Clock, FolderSearch, Mail, Network, Radar } from "lucide-react";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";

// Screening Sources tab (2.10) — Phase 1 ships email + local folders (see
// Scan Sources). This tab is where additional screening sources (LinkedIn
// export, job-board imports, ATS integrations) get added over time, each as
// another ResumeIngestor implementation behind the same interface.
const SOURCES = [
  { name: "Local folders", status: "active" as const, detail: "Scan Sources tab", icon: FolderSearch },
  { name: "Email (Gmail / Outlook)", status: "active" as const, detail: "Email Access tab", icon: Mail },
  { name: "LinkedIn export", status: "planned" as const, detail: "Phase 2", icon: Network },
  { name: "Job board imports (Indeed, ZipRecruiter, etc.)", status: "planned" as const, detail: "Phase 2", icon: Network },
  { name: "ATS integration", status: "planned" as const, detail: "Phase 2", icon: Network },
];

export function ScreeningSourcesPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Screening Sources"
        description="Every source feeds the same candidate pool and matching pipeline — adding a new source later doesn't change how results are scored or displayed."
      />
      <Card className="p-0">
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {SOURCES.map((s) => {
            const Icon = s.icon;
            return (
              <li key={s.name} className="flex items-center justify-between p-3.5 text-sm">
                <div className="flex items-center gap-3">
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                      s.status === "active"
                        ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400"
                        : "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500"
                    }`}
                  >
                    <Icon size={15} />
                  </div>
                  <span className="text-zinc-800 dark:text-zinc-200">{s.name}</span>
                </div>
                <span
                  className={`flex items-center gap-1.5 text-xs font-medium ${
                    s.status === "active" ? "text-emerald-600 dark:text-emerald-400" : "text-zinc-400"
                  }`}
                >
                  {s.status === "active" ? <CheckCircle2 size={13} /> : <Clock size={13} />}
                  {s.detail}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
      <p className="mt-4 flex items-center gap-1.5 text-xs text-zinc-400">
        <Radar size={12} /> New sources are added as another ingestor behind the same interface — see design-decisions.md ADR-003.
      </p>
    </div>
  );
}
