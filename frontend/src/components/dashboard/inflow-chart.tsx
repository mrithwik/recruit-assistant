import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useSettingsStore } from "../../stores/settings-store";
import { getChartPalette } from "../../lib/chart-colors";
import type { InflowDay } from "../../lib/types";

function formatDay(date: string) {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Recharts' auto-tick algorithm produces non-monotonic ticks on tiny integer
// ranges (e.g. "3, 3, 1, 2") — build a clean 0..max integer tick set instead.
function integerTicks(maxValue: number): number[] {
  const ceiling = Math.max(4, maxValue);
  const step = Math.ceil(ceiling / 4);
  const ticks: number[] = [];
  for (let v = 0; v <= step * 4; v += step) ticks.push(v);
  return ticks;
}

export function InflowChart({ data }: { data: InflowDay[] }) {
  const theme = useSettingsStore((s) => s.theme);
  const palette = getChartPalette(theme);
  const [emailColor, folderColor] = palette.categorical;
  const maxStacked = Math.max(0, ...data.map((d) => d.email + d.folder));
  const ticks = integerTicks(maxStacked);
  // A stacked series that's flat zero across the whole window still draws
  // its stroke line exactly on the boundary of the series below it — since
  // it's drawn second (on top), that stroke visually overwrites the other
  // series' edge, making an all-email chart render as if it were all
  // folder (or vice versa). Only render a series that actually has data.
  const hasEmail = data.some((d) => d.email > 0);
  const hasFolder = data.some((d) => d.folder > 0);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={palette.ink.grid} strokeDasharray="0" />
        <XAxis
          dataKey="date"
          tickFormatter={formatDay}
          tick={{ fill: palette.ink.muted, fontSize: 11 }}
          axisLine={{ stroke: palette.ink.grid }}
          tickLine={false}
          interval={Math.ceil(data.length / 6)}
        />
        <YAxis
          tick={{ fill: palette.ink.muted, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
          width={28}
          domain={[0, ticks[ticks.length - 1]]}
          ticks={ticks}
        />
        <Tooltip
          contentStyle={{
            background: theme === "dark" ? "#1a1a19" : "#fcfcfb",
            border: `1px solid ${palette.ink.grid}`,
            borderRadius: 8,
            fontSize: 12,
            color: palette.ink.primary,
          }}
          labelFormatter={(v) => formatDay(String(v))}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: palette.ink.secondary }}
          iconType="circle"
          iconSize={8}
          formatter={(value) => (value === "email" ? "Email" : "Folder")}
        />
        {hasEmail && (
          <Area
            type="monotone"
            dataKey="email"
            stackId="1"
            stroke={emailColor}
            strokeWidth={2}
            fill={emailColor}
            fillOpacity={0.15}
          />
        )}
        {hasFolder && (
          <Area
            type="monotone"
            dataKey="folder"
            stackId="1"
            stroke={folderColor}
            strokeWidth={2}
            fill={folderColor}
            fillOpacity={0.15}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
