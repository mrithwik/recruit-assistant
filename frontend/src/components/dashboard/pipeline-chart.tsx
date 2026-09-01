import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSettingsStore } from "../../stores/settings-store";
import { getChartPalette } from "../../lib/chart-colors";
import { STAGE_LABELS } from "../ui/pipeline-stage-badge";
import type { PipelineStageCount } from "../../lib/types";

// Stage is identity (7 distinct steps in a process), not magnitude, so this
// uses fixed per-stage hues — mirroring PipelineStageBadge's colors, in the
// same sourced->declined order — rather than TierChart's single-hue ordinal
// ramp, which is built for a 4-step quality gradient, not 7 named stages.
const STAGE_COLORS: Record<string, string> = {
  sourced: "#94a3b8",
  screened: "#0ea5e9",
  submitted: "#2563eb",
  interviewing: "#8b5cf6",
  offer: "#f59e0b",
  placed: "#059669",
  declined: "#a8a29e",
};

export function PipelineChart({ data }: { data: PipelineStageCount[] }) {
  const theme = useSettingsStore((s) => s.theme);
  const palette = getChartPalette(theme);

  const rows = data.map((d) => ({ ...d, label: STAGE_LABELS[d.stage] ?? d.stage }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 0, bottom: 4 }} barCategoryGap={10}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: palette.ink.secondary, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={80}
        />
        <Tooltip
          cursor={{ fill: theme === "dark" ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)" }}
          contentStyle={{
            background: theme === "dark" ? "#1a1a19" : "#fcfcfb",
            border: `1px solid ${palette.ink.grid}`,
            borderRadius: 8,
            fontSize: 12,
            color: palette.ink.primary,
          }}
        />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22} label={{ position: "right", fill: palette.ink.secondary, fontSize: 12 }}>
          {rows.map((row) => (
            <Cell key={row.stage} fill={STAGE_COLORS[row.stage] ?? palette.magnitude} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
