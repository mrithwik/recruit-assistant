import {
  Briefcase,
  FolderSearch,
  IdCard,
  Mail,
  Server,
  Users,
  SlidersHorizontal,
  History,
  Radar,
  LayoutDashboard,
  type LucideIcon,
} from "lucide-react";

// Single source of truth for the in-app tabs — the sidebar renders from
// this, grouped into "Workflow" (where a recruiter actually spends time —
// Job Descriptions is the operational hub: add/search/manage jobs, set
// criteria, trigger scans, all in one place) vs "Settings" (configured once,
// then left alone). This grouping is what makes it obvious where to start,
// per the "other tabs are just additional options" requirement — see
// architecture/project-log.md for the reasoning.
export interface NavItem {
  path: string;
  label: string;
  requirement: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Workflow",
    items: [
      { path: "/app/dashboard", label: "Dashboard", requirement: "1", icon: LayoutDashboard },
      { path: "/app/jobs", label: "Job Descriptions", requirement: "2.1", icon: Briefcase },
      { path: "/app/results", label: "Candidate Results", requirement: "2.5", icon: Users },
      { path: "/app/candidates", label: "All Candidates", requirement: "2.5", icon: IdCard },
      { path: "/app/history", label: "Search History", requirement: "2.7", icon: History },
    ],
  },
  {
    label: "Settings & Sources",
    items: [
      { path: "/app/scan", label: "Scan Sources", requirement: "2.2", icon: FolderSearch },
      { path: "/app/email-access", label: "Email Access", requirement: "2.3", icon: Mail },
      { path: "/app/connections", label: "Connection Setup", requirement: "2.4", icon: Server },
      { path: "/app/criteria", label: "Criteria Library", requirement: "5", icon: SlidersHorizontal },
      { path: "/app/screening-sources", label: "Screening Sources", requirement: "2.10", icon: Radar },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
