import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSettingsStore } from "../../stores/settings-store";
import { getChartPalette } from "../../lib/chart-colors";
import type { TierCount } from "../../lib/types";

const TIER_LABELS: Record<string, string> = {
  poor_match: "Poor",
  average_match: "Average",
  good_match: "Good",
  great_match: "Great",
};

export function TierChart({ data }: { data: TierCount[] }) {
  const theme = useSettingsStore((s) => s.theme);
  const palette = getChartPalette(theme);

  const rows = data.map((d) => ({ ...d, label: TIER_LABELS[d.tier] ?? d.tier }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 0, bottom: 4 }} barCategoryGap={10}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: palette.ink.secondary, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={64}
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
          {rows.map((row, i) => (
            <Cell key={row.tier} fill={palette.ordinal[i]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
