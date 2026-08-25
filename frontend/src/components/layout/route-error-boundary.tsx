import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "../ui/button";

// Without this, an uncaught render error (e.g. a stale localStorage value
// missing a field a newer component expects) unmounts the entire app —
// blank page, and even the browser back button can't recover since React
// itself has crashed and stopped handling navigation. This contains the
// crash to the current page and offers a way out that doesn't require a
// hard refresh.
export class RouteErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Route crashed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
          <AlertTriangle className="text-red-500" size={28} />
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-200">Something went wrong loading this page.</p>
          <p className="max-w-md text-xs text-zinc-500 dark:text-zinc-400">{this.state.error.message}</p>
          <Button variant="secondary" onClick={() => window.location.assign("/app/dashboard")}>
            Back to dashboard
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
