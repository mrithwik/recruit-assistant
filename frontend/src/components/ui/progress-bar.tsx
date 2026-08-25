import { useEffect, useRef, useState } from "react";

/**
 * Simulated determinate progress for actions with no real backend progress
 * stream (scan/generate/match all run as one blocking request today — see
 * project-log's streaming-results roadmap item for the real thing). Fills
 * on an easing curve toward 95% over `estimatedSeconds`, then jumps to 100%
 * the moment `active` goes false — so the user has *something* to read
 * ("about 12s left") instead of an indefinite spinner, without pretending
 * to know the actual remaining time exactly.
 */
export function useSimulatedProgress(estimatedSeconds: number, active: boolean) {
  const [pct, setPct] = useState(0);
  const [overrun, setOverrun] = useState(false);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      if (startRef.current !== null) setPct(100);
      startRef.current = null;
      setOverrun(false);
      return;
    }
    startRef.current = Date.now();
    setPct(2);
    setOverrun(false);
    const total = Math.max(1, estimatedSeconds) * 1000;
    const interval = setInterval(() => {
      const elapsed = Date.now() - (startRef.current ?? Date.now());
      const linear = elapsed / total;
      const eased = 1 - Math.pow(1 - Math.min(linear, 1), 2);
      setPct(Math.min(95, Math.round(eased * 95)));
      // Past ~1.5x the estimate, stop implying "almost done" — a slow scan
      // sitting at 95% reading "almost done" for minutes reads as hung.
      setOverrun(elapsed > total * 1.5);
    }, 200);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setPct(0), 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const remainingSeconds = Math.max(0, Math.round((estimatedSeconds * (100 - pct)) / 100));
  return { pct, remainingSeconds, overrun };
}

interface ProgressBarProps {
  pct: number;
  label?: string;
  remainingSeconds?: number;
  overrun?: boolean;
}

export function ProgressBar({ pct, label, remainingSeconds, overrun }: ProgressBarProps) {
  return (
    <div className="w-full">
      {(label || remainingSeconds !== undefined) && (
        <div className="mb-1 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
          <span>{overrun ? "Still working — large batches can take a few minutes, this isn't stuck" : label}</span>
          {remainingSeconds !== undefined && pct < 100 && !overrun && (
            <span className="tabular-nums">
              {remainingSeconds > 0 ? `~${remainingSeconds}s remaining` : "almost done…"}
            </span>
          )}
        </div>
      )}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div
          className="h-full rounded-full bg-indigo-500 transition-[width] duration-200 ease-out dark:bg-indigo-400"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
