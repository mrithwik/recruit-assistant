export type MatchTier = "great_match" | "good_match" | "average_match" | "poor_match" | "red_flagged";

export interface AuthStatus {
  setup_complete: boolean;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

export interface Session {
  token: string;
  user: AuthUser;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  raw_text: string;
  parsed_requirements: Record<string, unknown>;
  criteria_version: number;
  active: boolean;
  created_at: string;
}

export interface Candidate {
  id: string;
  legal_first_name: string;
  legal_middle_name: string;
  legal_last_name: string;
  email: string;
  phone: string;
  employment_status: string;
  work_visa_status: string;
  skills: string[];
  experience_years: number;
  education: string[];
  semantic_summary: string;
  date_submitted: string;
  primary_file_path: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  sources: string[];
  history: { date: string; origin: string; note: string }[];
  email_link: string;
}

export interface MatchSummaryItem {
  match_id: string;
  job_id: string;
  job_title: string;
  candidate_id: string;
  candidate_name: string;
  score: number;
  tier: MatchTier;
  matched_at: string;
}

export interface CandidateMatchDetail extends MatchSummaryItem {
  reasons: { matched: string[]; gaps: string[] };
  missing_info: string[];
  flags: Flag[];
  judge_notes: string;
}

export interface CandidateDetail extends Candidate {
  matches: CandidateMatchDetail[];
}

export interface ResumeSourceInfo {
  id: string;
  origin: string;
  source_ref: string;
  date_submitted: string;
  additional_attachments: string[];
  email_link: string;
}

export interface CandidateFacets {
  skills: string[];
  employment_statuses: string[];
  work_visa_statuses: string[];
  experience_years_max: number;
}

export interface DataModeCounts {
  real: number;
  mock: number;
  total: number;
}

export interface JobMatchSummary {
  job_id: string;
  total_matches: number;
  tier_counts: Record<string, number>;
  top_candidates: MatchSummaryItem[];
  last_matched_at: string | null;
}

export interface Flag {
  color: "green" | "red";
  note: string;
}

export interface Match {
  id: string;
  job_id: string;
  candidate: Candidate;
  score: number;
  tier: MatchTier;
  reasons: { matched: string[]; gaps: string[] };
  missing_info: string[];
  flags: Flag[];
  judge_notes: string;
  criteria_version: number;
  matched_at: string;
}

export type CriterionFieldType = "text" | "number" | "boolean" | "select";

export interface Criterion {
  id: string;
  name: string;
  description: string;
  weight: number;
  job_id: string | null;
  is_builtin: boolean;
  field_type: CriterionFieldType;
  options: string[];
}

export interface JobCriterionSelection {
  criterion: Criterion;
  enabled: boolean;
  value: string;
}

export interface SearchHistoryEntry {
  id: string;
  job_id: string;
  run_at: string;
  date_range_start: string | null;
  date_range_end: string | null;
  sources_scanned: Record<string, unknown>;
  candidate_count: number;
  criteria_version: number;
}

export interface EmailAccount {
  id: string;
  provider: "gmail" | "outlook";
  email_address: string;
  connected_at: string;
  last_scanned_at: string | null;
  status: string;
}

export interface ScheduledSource {
  id: string;
  kind: "folder" | "email_account";
  ref: string;
  include_subfolders: boolean;
  created_at: string;
  last_run_at: string | null;
}

export interface ScanResult {
  resumes_found: number;
  candidates_created: number;
  candidates_updated: number;
  duplicates_skipped: number;
  errors: string[];
  elapsed_seconds: number;
}

// A scan now runs as a background job instead of blocking the triggering
// request (a real email scan can run long enough that holding one HTTP
// request open for it risks a browser/proxy timeout) — POST /scan/folders
// and /scan/email-accounts return this immediately with status "running";
// poll GET /scan/jobs/{id} for progress.
export interface ScanJob {
  id: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at?: string;
  result?: ScanResult;
  progress?: ScanResult;
  error?: string;
}

export interface OAuthStatus {
  google_configured: boolean;
  microsoft_configured: boolean;
}

export interface MaintenanceTask {
  id: string;
  label: string;
  description: string;
  pending_count: number;
}

export interface MatchListResult {
  matches: Match[];
  elapsed_seconds: number;
}

export interface CandidateListResult {
  candidates: Candidate[];
  total: number;
  elapsed_seconds: number;
}

export interface ClearDataResult {
  jobs_deleted: number;
  candidates_deleted: number;
  matches_deleted: number;
  criteria_deleted: number;
  email_accounts_deleted: number;
}

export interface GenerateSampleDataResult {
  total_items: number;
  initial_applications: number;
  followups: number;
  upskill_resubmissions: number;
  upskill_journey_candidates: number;
  resumes_dir: string;
  manifest_path: string;
}

export interface DraftEmail {
  subject: string;
  body: string;
  missing_required_fields: string[];
}

// --- Dashboard ---

export interface DashboardKPIs {
  active_jobs: number;
  total_candidates: number;
  matches_scored: number;
  needs_attention: number;
  connected_sources: number;
}

export interface InflowDay {
  date: string;
  email: number;
  folder: number;
}

export interface TierCount {
  tier: MatchTier;
  count: number;
}

export interface NamedCount {
  label: string;
  count: number;
}

export interface JobSnapshot {
  id: string;
  title: string;
  candidate_count: number;
  top_score: number | null;
  last_matched_at: string | null;
}

export interface AttentionItem {
  match_id: string;
  job_id: string;
  job_title: string;
  candidate_id: string;
  candidate_name: string;
  reason: string;
  tier: MatchTier;
}

export interface ActivityItem {
  type: "scan" | "candidate" | "ingest";
  timestamp: string;
  description: string;
  job_id: string;
  candidate_id: string;
}

export interface DashboardSummary {
  kpis: DashboardKPIs;
  inflow_trend: InflowDay[];
  tier_distribution: TierCount[];
  red_flagged_count: number;
  top_skills: NamedCount[];
  visa_breakdown: NamedCount[];
  jobs_snapshot: JobSnapshot[];
  needs_attention: AttentionItem[];
  recent_activity: ActivityItem[];
}

// Runtime mock/real toggles — live-switchable from the UI without
// restarting the backend, see backend/app/runtime_settings.py.
export interface MockMode {
  use_mock_llm: boolean;
  use_mock_email: boolean;
  real_llm_available: boolean;
  expose_toggle: boolean;
}
