import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { api } from "../../lib/api";
import { MaintenanceTaskRow } from "../maintenance/maintenance-task-row";
import type { MaintenanceTask } from "../../lib/types";

// New features that need to touch data already sitting in the database
// (like the email-link deep link, which only populates going forward)
// register a task in backend/app/maintenance/tasks.py instead of shipping
// a one-off script — this panel lists whatever's registered so a recruiter
// always has one place to check "does this apply to my existing data" and
// a button to make it so, without needing a terminal. See also the
// Dashboard's "Updates available" banner, which surfaces only the tasks
// with pending work using the same MaintenanceTaskRow.
export function MaintenanceTasks() {
  const [tasks, setTasks] = useState<MaintenanceTask[]>([]);

  function refresh() {
    api.listMaintenanceTasks().then(setTasks).catch(() => {});
  }

  useEffect(() => {
    refresh();
  }, []);

  // Same rule as the Dashboard's "Updates available" banner — a task with
  // nothing left to touch (pending_count is 0) drops out here too, instead
  // of sitting in the list forever with nothing to actually do. Applies
  // automatically to every task registered in the framework, not just this
  // one — see backend/app/maintenance/tasks.py.
  const pendingTasks = tasks.filter((t) => t.pending_count > 0);
  if (pendingTasks.length === 0) return null;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        <Wrench size={12} /> Data maintenance
      </p>
      <div className="flex flex-col gap-3">
        {pendingTasks.map((t) => (
          <MaintenanceTaskRow key={t.id} task={t} onDone={refresh} />
        ))}
      </div>
    </div>
  );
}
