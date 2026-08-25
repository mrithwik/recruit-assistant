import type { MatchTier } from "../../lib/types";

// Color coding per requirement 2.5: shades of green for good/great matches
// (darker dot = better), orange for average, shades of red for poor/red-flagged.
const TIER_STYLES: Record<MatchTier, { label: string; badge: string; dot: string }> = {
  great_match: {
    label: "Great match",
    badge: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30",
    dot: "bg-emerald-600",
  },
  good_match: {
    label: "Good match",
    badge: "bg-green-50 text-green-700 ring-green-200 dark:bg-green-500/10 dark:text-green-300 dark:ring-green-500/30",
    dot: "bg-green-500",
  },
  average_match: {
    label: "Average match",
    badge: "bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/30",
    dot: "bg-orange-500",
  },
  poor_match: {
    label: "Poor match",
    badge: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30",
    dot: "bg-red-500",
  },
  red_flagged: {
    label: "Red flagged",
    badge: "bg-red-100 text-red-900 ring-red-300 dark:bg-red-900/40 dark:text-red-200 dark:ring-red-800",
    dot: "bg-red-800",
  },
};

export function MatchBadge({ tier, score }: { tier: MatchTier; score: number }) {
  const style = TIER_STYLES[tier];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${style.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
      <span className="opacity-60">·</span>
      {Math.round(score)}
    </span>
  );
}
