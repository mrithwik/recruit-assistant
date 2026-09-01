import { clearToken, getToken } from "./auth-token";

const BASE = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    throw new Error("401 Unauthorized: session expired, please sign in again");
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// A plain <a href> can't carry the Authorization header this app uses for
// every other request (auth is a bearer token, not a cookie) — a resume
// download or CSV export needs an authenticated fetch first, then a
// client-side save from the resulting blob. Shared by both.
async function downloadFile(path: string, fallbackFilename: string, options?: RequestInit): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    throw new Error("401 Unauthorized: session expired, please sign in again");
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackFilename;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

interface CandidateFilterParams {
  date_start?: string;
  date_end?: string;
  source?: string;
  q?: string;
  sort?: string;
  skill?: string[];
  employment_status?: string[];
  work_visa_status?: string[];
  experience_min?: number;
  experience_max?: number;
  data_mode?: string;
  needs_attention?: boolean;
}

// Shared by listCandidates (paginated) and exportCandidates (full CSV) so
// "the current filters" can never mean something different between the
// screen and the export it produces — see storage.candidates_matching on
// the backend, which shares its condition-building with candidates_page
// for the identical reason.
function candidateFilterQueryString(params?: CandidateFilterParams): URLSearchParams {
  const qs = new URLSearchParams();
  if (params?.date_start) qs.set("date_start", params.date_start);
  if (params?.date_end) qs.set("date_end", params.date_end);
  if (params?.source) qs.set("source", params.source);
  if (params?.q) qs.set("q", params.q);
  if (params?.sort) qs.set("sort", params.sort);
  for (const s of params?.skill ?? []) qs.append("skill", s);
  for (const s of params?.employment_status ?? []) qs.append("employment_status", s);
  for (const s of params?.work_visa_status ?? []) qs.append("work_visa_status", s);
  if (params?.experience_min !== undefined) qs.set("experience_min", String(params.experience_min));
  if (params?.experience_max !== undefined) qs.set("experience_max", String(params.experience_max));
  if (params?.data_mode) qs.set("data_mode", params.data_mode);
  if (params?.needs_attention) qs.set("needs_attention", "true");
  return qs;
}

export const api = {
  health: () => fetch("/health").then((r) => r.json()),

  authStatus: () => request<import("./types").AuthStatus>("/auth/status"),
  register: (email: string, password: string, name: string, remember: boolean) =>
    request<import("./types").Session>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name, remember }),
    }),
  login: (email: string, password: string, remember: boolean) =>
    request<import("./types").Session>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, remember }),
    }),
  me: () => request<import("./types").AuthUser>("/auth/me"),

  listJobs: () => request<import("./types").Job[]>("/jobs"),
  createJob: (title: string, raw_text: string, company: string = "") =>
    request<import("./types").Job>("/jobs", {
      method: "POST",
      body: JSON.stringify({ title, raw_text, company }),
    }),
  deactivateJob: (id: string) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  bulkDeleteJobs: (job_ids: string[]) =>
    request<{ deleted: number }>("/jobs/bulk-delete", { method: "POST", body: JSON.stringify({ job_ids }) }),
  listInactiveJobs: () => request<import("./types").Job[]>("/jobs/inactive"),
  reactivateJob: (id: string) => request<import("./types").Job>(`/jobs/${id}/reactivate`, { method: "POST" }),

  scanFolders: (folder_paths: string[], include_subfolders: boolean, date_start?: string, date_end?: string) =>
    request<import("./types").ScanJob>("/scan/folders", {
      method: "POST",
      body: JSON.stringify({ folder_paths, include_subfolders, date_start, date_end }),
    }),
  scanEmailAccounts: (account_ids: string[], date_start?: string, date_end?: string) =>
    request<import("./types").ScanJob>("/scan/email-accounts", {
      method: "POST",
      body: JSON.stringify({ account_ids, date_start, date_end }),
    }),
  getScanJob: (jobId: string) => request<import("./types").ScanJob>(`/scan/jobs/${jobId}`),
  cancelScanJob: (jobId: string) =>
    request<import("./types").ScanJob>(`/scan/jobs/${jobId}/cancel`, { method: "POST" }),

  getOAuthStatus: () => request<import("./types").OAuthStatus>("/email-accounts/oauth-status"),

  listMaintenanceTasks: () => request<import("./types").MaintenanceTask[]>("/maintenance/tasks"),
  runMaintenanceTask: (taskId: string) =>
    request<import("./types").ScanJob>(`/maintenance/tasks/${taskId}/run`, { method: "POST" }),

  getMockMode: () => request<import("./types").MockMode>("/settings/mock-mode"),
  updateMockMode: (payload: { use_mock_llm?: boolean; use_mock_email?: boolean; consent_ack?: boolean }) =>
    request<import("./types").MockMode>("/settings/mock-mode", { method: "PATCH", body: JSON.stringify(payload) }),

  listCandidates: (params?: CandidateFilterParams & { limit?: number; offset?: number }) => {
    const qs = candidateFilterQueryString(params);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<import("./types").CandidateListResult>(`/candidates${suffix}`);
  },
  exportCandidates: (params?: CandidateFilterParams) => {
    const qs = candidateFilterQueryString(params);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return downloadFile(`/candidates/export${suffix}`, "candidates.csv");
  },
  exportSelectedCandidates: (ids: string[]) =>
    downloadFile("/candidates/export-selected", "candidates-selected.csv", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  getCandidateFacets: (dataMode?: string) =>
    request<import("./types").CandidateFacets>(
      `/candidates/facets${dataMode ? `?data_mode=${dataMode}` : ""}`,
    ),
  getDataModeCounts: () => request<import("./types").DataModeCounts>("/candidates/data-mode-counts"),
  getCandidate: (id: string) => request<import("./types").CandidateDetail>(`/candidates/${id}`),
  listCandidateSources: (id: string) =>
    request<import("./types").ResumeSourceInfo[]>(`/candidates/${id}/sources`),
  scanAll: () => request<import("./types").ScanJob>("/scan/all", { method: "POST" }),
  rescanMatched: (jobId: string, batchId?: string) =>
    request<import("./types").ScanJob>(
      `/matches/${jobId}/rescan-matched${batchId ? `?batch_id=${batchId}` : ""}`,
      { method: "POST" },
    ),
  rescanCandidate: (id: string) => request<import("./types").ScanJob>(`/candidates/${id}/rescan`, { method: "POST" }),
  getCandidateSourceText: (id: string, sourceId: string) =>
    request<{ origin: string; source_ref: string; date_submitted: string; text: string }>(
      `/candidates/${id}/sources/${sourceId}/text`,
    ),
  downloadCandidateSourceFile: (id: string, sourceId: string) =>
    downloadFile(`/candidates/${id}/sources/${sourceId}/file`, "resume"),
  addCandidateNote: (id: string, text: string) =>
    request<import("./types").CandidateNote[]>(`/candidates/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  deleteCandidateNote: (id: string, noteId: string) =>
    request<import("./types").CandidateNote[]>(`/candidates/${id}/notes/${noteId}`, { method: "DELETE" }),
  deleteCandidate: (id: string) => request<void>(`/candidates/${id}`, { method: "DELETE" }),

  runMatching: (jobId: string, topN: number, dataMode?: string, batchId?: string) =>
    request<import("./types").ScanJob>(
      `/matches/run/${jobId}?top_n=${topN}${dataMode ? `&data_mode=${dataMode}` : ""}${batchId ? `&batch_id=${batchId}` : ""}`,
      { method: "POST" },
    ),
  listMatches: (jobId: string, topN: number, dataMode?: string) =>
    request<import("./types").MatchListResult>(
      `/matches/${jobId}?top_n=${topN}${dataMode ? `&data_mode=${dataMode}` : ""}`,
    ),
  getMatchSummary: (jobId: string) =>
    request<import("./types").JobMatchSummary>(`/matches/summary/${jobId}`),
  flagMatch: (matchId: string, color: "green" | "red", note: string) =>
    request<import("./types").Match>(`/matches/${matchId}/flag`, {
      method: "POST",
      body: JSON.stringify({ color, note }),
    }),
  updateMatchStage: (matchId: string, stage: import("./types").PipelineStage) =>
    request<import("./types").Match>(`/matches/${matchId}/stage`, {
      method: "POST",
      body: JSON.stringify({ stage }),
    }),

  listCriteria: (jobId?: string) =>
    request<import("./types").Criterion[]>(`/criteria${jobId ? `?job_id=${jobId}` : ""}`),
  addCriterion: (
    name: string,
    description: string,
    weight: number,
    job_id: string | null,
    field_type: import("./types").CriterionFieldType = "text",
    options: string[] = [],
  ) =>
    request<import("./types").Criterion>("/criteria", {
      method: "POST",
      body: JSON.stringify({ name, description, weight, job_id, field_type, options }),
    }),
  rescan: (job_id: string, mode: "existing_data" | "full_rescan") =>
    request<{ job_id: string; mode: string }>("/criteria/rescan", {
      method: "POST",
      body: JSON.stringify({ job_id, mode }),
    }),

  getCriteriaForJob: (jobId: string) =>
    request<import("./types").JobCriterionSelection[]>(`/criteria/for-job/${jobId}`),
  setCriterionForJob: (jobId: string, criterionId: string, enabled: boolean, value: string) =>
    request<import("./types").JobCriterionSelection>(`/criteria/for-job/${jobId}/${criterionId}`, {
      method: "PUT",
      body: JSON.stringify({ enabled, value }),
    }),

  listHistory: (jobId?: string) =>
    request<import("./types").SearchHistoryEntry[]>(`/history${jobId ? `?job_id=${jobId}` : ""}`),

  listScanLogs: () => request<import("./types").IngestScanLogEntry[]>("/scan/logs"),

  draftEmail: (matchId: string) =>
    request<import("./types").DraftEmail>("/draft-email", {
      method: "POST",
      body: JSON.stringify({ match_id: matchId }),
    }),

  listEmailAccounts: () => request<import("./types").EmailAccount[]>("/email-accounts"),
  disconnectEmailAccount: (id: string) => request<void>(`/email-accounts/${id}`, { method: "DELETE" }),

  listScheduledSources: () => request<import("./types").ScheduledSource[]>("/scheduled-sources"),
  addScheduledSource: (kind: "folder" | "email_account", ref: string, includeSubfolders = true) =>
    request<import("./types").ScheduledSource>("/scheduled-sources", {
      method: "POST",
      body: JSON.stringify({ kind, ref, include_subfolders: includeSubfolders }),
    }),
  removeScheduledSource: (id: string) => request<void>(`/scheduled-sources/${id}`, { method: "DELETE" }),

  dashboardSummary: (dataMode?: string) =>
    request<import("./types").DashboardSummary>(
      `/dashboard/summary${dataMode ? `?data_mode=${dataMode}` : ""}`,
    ),

  activityLog: (limit: number, offset: number) =>
    request<import("./types").ActivityLogPage>(`/dashboard/activity?limit=${limit}&offset=${offset}`),

  generateSampleData: (initial: number, followups: number, upskill: number, seed: number) =>
    request<import("./types").GenerateSampleDataResult>("/dev-tools/generate-sample-data", {
      method: "POST",
      body: JSON.stringify({ initial, followups, upskill, seed }),
    }),
  clearData: () => request<import("./types").ClearDataResult>("/dev-tools/clear-data", { method: "POST" }),

  listSampleSessions: () => request<import("./types").SampleSession[]>("/dev-tools/sample-sessions"),
  deleteSampleSession: (sessionId: string) =>
    request<import("./types").SampleSessionDeleteResult>(
      `/dev-tools/sample-sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    ),
};
