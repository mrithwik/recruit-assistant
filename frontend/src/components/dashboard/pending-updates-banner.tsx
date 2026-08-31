import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../../lib/api";
import { MaintenanceTaskRow } from "../maintenance/maintenance-task-row";
import { Card } from "../ui/card";
import type { MaintenanceTask } from "../../lib/types";

// A feature that reads a field on existing rows (email_link, or the next
// one like it) only applies going forward once shipped — this is what
// makes that visible without the recruiter having to know to check Scan
// Sources' "Data maintenance" panel. Only tasks with pending_count > 0
// show here at all; once a task's backfill is fully caught up, this
// banner has nothing left to say about it.
export function PendingUpdatesBanner() {
  const [tasks, setTasks] = useState<MaintenanceTask[]>([]);

  function refresh() {
    api.listMaintenanceTasks().then(setTasks).catch(() => {});
  }

  useEffect(() => {
    refresh();
  }, []);

  const pending = tasks.filter((t) => t.pending_count > 0);
  if (pending.length === 0) return null;

  return (
    <Card className="mb-6 border-indigo-200 bg-indigo-50/40 dark:border-indigo-900 dark:bg-indigo-500/5">
      <p className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
        <Sparkles size={15} /> Updates available
      </p>
      <div className="flex flex-col gap-4">
        {pending.map((t) => (
          <div key={t.id}>
            <MaintenanceTaskRow task={t} onDone={refresh} />
            <p className="mt-1 text-xs text-indigo-600 dark:text-indigo-400">
              Affects {t.pending_count.toLocaleString()} existing record(s).
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}
