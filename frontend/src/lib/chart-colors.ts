// Colors for the dashboard's recharts components, taken from the dataviz
// skill's validated reference palette (CVD-safe categorical order, ordinal
// blue ramp, fixed status colors). Not used elsewhere in the app — this is
// specifically the chart-rendering palette, kept separate from the Tailwind
// utility classes the rest of the UI uses.

export interface ChartPalette {
  categorical: [string, string]; // [email, folder] — fixed order, never cycled
  ordinal: [string, string, string, string]; // poor -> average -> good -> great
  magnitude: string; // single-hue bars (skills, visa breakdown)
  status: { good: string; warning: string; serious: string; critical: string };
  ink: { primary: string; secondary: string; muted: string; grid: string };
}

const LIGHT: ChartPalette = {
  categorical: ["#2a78d6", "#eb6834"],
  ordinal: ["#86b6ef", "#3987e5", "#256abf", "#184f95"],
  magnitude: "#2a78d6",
  status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
  ink: { primary: "#0b0b0b", secondary: "#52514e", muted: "#898781", grid: "#e1e0d9" },
};

const DARK: ChartPalette = {
  categorical: ["#3987e5", "#d95926"],
  ordinal: ["#86b6ef", "#3987e5", "#256abf", "#184f95"],
  magnitude: "#3987e5",
  status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#e66767" },
  ink: { primary: "#ffffff", secondary: "#c3c2b7", muted: "#898781", grid: "#2c2c2a" },
};

export function getChartPalette(theme: "light" | "dark"): ChartPalette {
  return theme === "dark" ? DARK : LIGHT;
}
