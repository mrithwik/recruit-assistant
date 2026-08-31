import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";

// Any mistyped or stale URL — top-level or under /app/* — used to render a
// completely blank page (no nav, no message, no way out). This is the
// catch-all `*` route both Routes blocks in App.tsx fall through to.
export function NotFoundPage({ homeTo, homeLabel }: { homeTo: string; homeLabel: string }) {
  return (
    <div className="mx-auto flex max-w-3xl items-center justify-center px-4 py-24">
      <EmptyState
        icon={<Compass size={20} />}
        title="Page not found"
        description="There's nothing here — the link may be stale, or the address was mistyped."
        action={
          <Link to={homeTo}>
            <Button size="sm">{homeLabel}</Button>
          </Link>
        }
      />
    </div>
  );
}
