import type { PipelineStage } from "../../lib/types";

// Deliberately a different hue family from MatchBadge's tier colors (green→red
// quality scale) — stage is a status, not a quality signal, so mixing the two
// palettes would make a badge row read as "how good" when it means "how far
// along." Slate→blue→violet→amber→emerald traces the process forward; declined
// stays neutral rather than red, since red here already means "poor match."
export const STAGE_LABELS: Record<PipelineStage, string> = {
  sourced: "Sourced",
  screened: "Screened",
  submitted: "Submitted",
  interviewing: "Interviewing",
  offer: "Offer",
  placed: "Placed",
  declined: "Declined",
};

const STAGE_STYLES: Record<PipelineStage, string> = {
  sourced: "bg-zinc-100 text-zinc-700 ring-zinc-300 dark:bg-zinc-500/10 dark:text-zinc-300 dark:ring-zinc-500/30",
  screened: "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/30",
  submitted: "bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30",
  interviewing: "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-500/30",
  offer: "bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30",
  placed: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30",
  declined: "bg-stone-100 text-stone-500 ring-stone-300 dark:bg-stone-500/10 dark:text-stone-400 dark:ring-stone-500/30",
};

export const PIPELINE_STAGE_OPTIONS: PipelineStage[] = [
  "sourced",
  "screened",
  "submitted",
  "interviewing",
  "offer",
  "placed",
  "declined",
];

export function PipelineStageBadge({ stage }: { stage: PipelineStage }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${STAGE_STYLES[stage]}`}>
      {STAGE_LABELS[stage]}
    </span>
  );
}
