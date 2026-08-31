// Client-side CSV export for data that's already loaded in the browser
// (Match Results — see results-page.tsx) as opposed to candidates/export
// on the backend, which exists because that data ISN'T all loaded
// (thousands of rows behind pagination). No network round-trip needed
// here, so no auth-fetch-then-blob dance either — just build the string
// and hand it to the browser.
function escapeCell(value: string | number): string {
  const s = String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function downloadCsv(filename: string, rows: (string | number)[][]): void {
  const csv = rows.map((row) => row.map(escapeCell).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
