import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { ArrowUp } from "lucide-react";
import { Header } from "./header";
import { Sidebar } from "./sidebar";
import { Toaster } from "../ui/toaster";
import { RouteErrorBoundary } from "./route-error-boundary";

const SCROLL_THRESHOLD = 320;

export function AppShell({ children }: { children: ReactNode }) {
  const mainRef = useRef<HTMLElement>(null);
  const [showScrollTop, setShowScrollTop] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const onScroll = () => setShowScrollTop(el.scrollTop > SCROLL_THRESHOLD);
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="flex h-screen flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main ref={mainRef} className="relative flex-1 overflow-y-auto px-6 py-7 md:px-10">
          <div className="animate-fade-in-up" key={location.pathname}>
            <RouteErrorBoundary>{children}</RouteErrorBoundary>
          </div>
          {showScrollTop && (
            <button
              onClick={() => mainRef.current?.scrollTo({ top: 0, behavior: "smooth" })}
              aria-label="Scroll to top"
              title="Scroll to top"
              className="fixed bottom-6 right-6 z-30 flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg transition-opacity hover:bg-indigo-500"
            >
              <ArrowUp size={17} />
            </button>
          )}
        </main>
      </div>
      <Toaster />
    </div>
  );
}
