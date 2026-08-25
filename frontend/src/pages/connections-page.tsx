import { Rocket, Server } from "lucide-react";
import { PageHeader } from "../components/ui/page-header";
import { EmptyState } from "../components/ui/empty-state";

// Connection Setup tab (2.4) — company server / cloud storage backend.
// Phase 2 per the plan: storage is local-only for now (BaseStorageBackend
// has one implementation, LocalStorageBackend). This tab exists so the nav
// structure is complete now; wiring it up is a swap of the storage backend,
// not a frontend rebuild.
export function ConnectionsPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Connection Setup" description="Company server and cloud storage connections." />
      <EmptyState
        icon={<Server size={20} />}
        title="Coming soon"
        description="Everything currently runs against local SQLite + local files, behind a storage-backend interface designed to swap in a company server or cloud target without touching the rest of the app."
        action={
          <span className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400">
            <Rocket size={13} /> Planned for Phase 2
          </span>
        }
      />
    </div>
  );
}
