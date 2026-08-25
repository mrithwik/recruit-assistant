import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSettingsStore } from "../../stores/settings-store";
import { getChartPalette } from "../../lib/chart-colors";
import type { NamedCount } from "../../lib/types";

// Single-hue ranked bars — magnitude encoding, not identity, so one color is
// correct here (per the dataviz skill: color follows the job it does).
export function RankedBarChart({ data, height = 200 }: { data: NamedCount[]; height?: number }) {
  const theme = useSettingsStore((s) => s.theme);
  const palette = getChartPalette(theme);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 0, bottom: 4 }} barCategoryGap={8}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: palette.ink.secondary, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={110}
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
        <Bar
          dataKey="count"
          fill={palette.magnitude}
          radius={[0, 4, 4, 0]}
          maxBarSize={18}
          label={{ position: "right", fill: palette.ink.secondary, fontSize: 12 }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
