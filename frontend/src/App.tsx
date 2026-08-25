import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/app-shell";
import { RequireAuth } from "./components/auth/require-auth";
import { useAuthStore } from "./stores/auth-store";
import { LandingPage } from "./pages/landing-page";
import { LoginPage } from "./pages/login-page";
import { DashboardPage } from "./pages/dashboard-page";
import { JobsPage } from "./pages/jobs-page";
import { ScanPage } from "./pages/scan-page";
import { EmailAccessPage } from "./pages/email-access-page";
import { ConnectionsPage } from "./pages/connections-page";
import { ResultsPage } from "./pages/results-page";
import { CandidateDetailPage } from "./pages/candidate-detail-page";
import { AllCandidatesPage } from "./pages/all-candidates-page";
import { CriteriaPage } from "./pages/criteria-page";
import { HistoryPage } from "./pages/history-page";
import { ScreeningSourcesPage } from "./pages/screening-sources-page";

export default function App() {
  const checkAuthStatus = useAuthStore((s) => s.checkAuthStatus);

  useEffect(() => {
    checkAuthStatus().catch(() => {});
  }, []);

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell>
              <Routes>
                <Route path="/" element={<Navigate to="/app/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="jobs" element={<JobsPage />} />
                <Route path="scan" element={<ScanPage />} />
                <Route path="email-access" element={<EmailAccessPage />} />
                <Route path="connections" element={<ConnectionsPage />} />
                <Route path="results" element={<ResultsPage />} />
                <Route path="candidates" element={<AllCandidatesPage />} />
                <Route path="candidates/:id" element={<CandidateDetailPage />} />
                <Route path="criteria" element={<CriteriaPage />} />
                <Route path="history" element={<HistoryPage />} />
                <Route path="screening-sources" element={<ScreeningSourcesPage />} />
              </Routes>
            </AppShell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
