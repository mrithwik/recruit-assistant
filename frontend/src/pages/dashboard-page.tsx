import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  AlertTriangle,
  Briefcase,
  FolderSearch,
  Layers,
  Loader2,
  Mail,
  Plug,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import { useAuthStore } from "../stores/auth-store";
import { useDashboardStore } from "../stores/dashboard-store";
import { useDataModeStore } from "../stores/data-mode-store";
import { StatTile } from "../components/dashboard/stat-tile";
import { SectionCard } from "../components/dashboard/section-card";
import { InflowChart } from "../components/dashboard/inflow-chart";
import { TierChart } from "../components/dashboard/tier-chart";
import { RankedBarChart } from "../components/dashboard/ranked-bar-chart";
import { JobsSnapshotList } from "../components/dashboard/jobs-snapshot-list";
import { ActivityFeed } from "../components/dashboard/activity-feed";
import { PendingUpdatesBanner } from "../components/dashboard/pending-updates-banner";
import { Button } from "../components/ui/button";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { summary, loading, fetchSummary } = useDashboardStore();
  const dataMode = useDataModeStore((s) => s.dataMode);
  const location = useLocation();

  useEffect(() => {
    fetchSummary(dataMode).catch(() => {});
  }, [dataMode]);

  useEffect(() => {
    if (location.hash === "#recent-activity") {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [location.hash, summary]);

  const firstName = user?.name?.split(" ")[0] || user?.email?.split("@")[0] || "there";
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  if (loading && !summary) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="animate-spin text-zinc-400" size={22} />
      </div>
    );
  }

  if (!summary) return null;

  const isEmpty = summary.kpis.active_jobs === 0 && summary.kpis.total_candidates === 0;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-zinc-900 dark:text-white">
            {greeting()}, {firstName}
          </h1>
          <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">{today}</p>
        </div>
        <div className="flex gap-2">
          <Link to="/app/jobs">
            <Button variant="secondary" size="sm" icon={<Briefcase size={13} />}>
              Add job
            </Button>
          </Link>
          <Link to="/app/scan">
            <Button variant="secondary" size="sm" icon={<FolderSearch size={13} />}>
              Scan sources
            </Button>
          </Link>
          <Link to="/app/email-access">
            <Button variant="secondary" size="sm" icon={<Mail size={13} />}>
              Connect email
            </Button>
          </Link>
        </div>
      </div>

      <PendingUpdatesBanner />

      {isEmpty ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-zinc-200 px-6 py-16 text-center dark:border-zinc-800">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
            <Sparkles size={22} />
          </div>
          <h2 className="font-display text-lg font-semibold text-zinc-900 dark:text-white">
            Let's set up your first search
          </h2>
          <p className="mt-1 max-w-md text-sm text-zinc-500 dark:text-zinc-400">
            Three steps and you'll have scored, color-coded candidates: add a job description, point
            it at a resume folder or mailbox, then run matching.
          </p>
          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              { icon: Briefcase, label: "1. Add a job description", to: "/app/jobs" },
              { icon: FolderSearch, label: "2. Scan folders or email", to: "/app/scan" },
              { icon: Target, label: "3. Run matching", to: "/app/results" },
            ].map((step) => (
              <Link
                key={step.label}
                to={step.to}
                className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 px-4 py-4 text-sm font-medium text-zinc-600 hover:border-indigo-300 hover:text-indigo-600 dark:border-zinc-800 dark:text-zinc-300 dark:hover:border-indigo-700"
              >
                <step.icon size={18} />
                {step.label}
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Active jobs" value={summary.kpis.active_jobs} icon={Briefcase} to="/app/jobs" />
            <StatTile label="Total candidates" value={summary.kpis.total_candidates} icon={Users} to="/app/candidates" />
            <StatTile label="Matches scored" value={summary.kpis.matches_scored} icon={Layers} to="/app/results" />
            <StatTile
              label="Needs attention"
              value={summary.kpis.needs_attention}
              icon={AlertTriangle}
              tone={summary.kpis.needs_attention > 0 ? "attention" : "default"}
              to="/app/candidates?needs_attention=true"
            />
            <StatTile label="Connected sources" value={summary.kpis.connected_sources} icon={Plug} to="/app/scan" />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <SectionCard
              title="Candidate inflow"
              subtitle="Last 30 days, by source"
              className="lg:col-span-2"
            >
              <InflowChart data={summary.inflow_trend} />
            </SectionCard>

            <SectionCard
              title="Match quality"
              subtitle={summary.red_flagged_count > 0 ? `${summary.red_flagged_count} red-flagged (excluded above)` : "Across all scored matches"}
            >
              <TierChart data={summary.tier_distribution} />
            </SectionCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SectionCard title="Top skills in your pipeline" subtitle="Most common across all candidates">
              {summary.top_skills.length > 0 ? (
                <RankedBarChart data={summary.top_skills} />
              ) : (
                <p className="py-8 text-center text-sm text-zinc-400">Not enough parsed resumes yet.</p>
              )}
            </SectionCard>

            <SectionCard title="Work authorization" subtitle="Candidate pool breakdown">
              {summary.visa_breakdown.length > 0 ? (
                <RankedBarChart data={summary.visa_breakdown} />
              ) : (
                <p className="py-8 text-center text-sm text-zinc-400">Not enough data yet.</p>
              )}
            </SectionCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SectionCard title="Jobs snapshot" subtitle="Active roles and their pipeline">
              <JobsSnapshotList jobs={summary.jobs_snapshot} />
            </SectionCard>

            <SectionCard
              title="Missing information"
              subtitle={
                <>
                  Candidates missing each kind of info —{" "}
                  <Link to="/app/candidates?needs_attention=true" className="text-indigo-600 hover:underline dark:text-indigo-400">
                    view all needing attention
                  </Link>
                </>
              }
            >
              {summary.missing_info_breakdown.length > 0 ? (
                <RankedBarChart data={summary.missing_info_breakdown} />
              ) : (
                <p className="py-8 text-center text-sm text-zinc-400">Nothing missing — every match has complete info.</p>
              )}
            </SectionCard>
          </div>

          <SectionCard id="recent-activity" title="Recent activity" subtitle="Latest scans and candidates">
            <ActivityFeed items={summary.recent_activity} />
          </SectionCard>
        </div>
      )}
    </div>
  );
}
