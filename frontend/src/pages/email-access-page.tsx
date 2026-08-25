import { useEffect } from "react";
import { Mail, ShieldCheck, Unplug } from "lucide-react";
import { useScanStore } from "../stores/scan-store";
import { api } from "../lib/api";
import { useToastStore } from "../stores/toast-store";
import { PageHeader } from "../components/ui/page-header";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";

export function EmailAccessPage() {
  const { emailAccounts, fetchEmailAccounts } = useScanStore();
  const push = useToastStore((s) => s.push);

  useEffect(() => {
    fetchEmailAccounts().catch(() => {});
  }, []);

  async function disconnect(id: string) {
    try {
      await api.disconnectEmailAccount(id);
      push("Account disconnected and token removed from keychain", "success");
      fetchEmailAccounts();
    } catch (e) {
      push(String(e), "error");
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Email Access" description="Connect a mailbox to scan for resume attachments." />

      <Card className="mb-6 flex items-start gap-3 border-indigo-100 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-500/5">
        <ShieldCheck size={18} className="mt-0.5 shrink-0 text-indigo-600 dark:text-indigo-400" />
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          Access is <strong className="text-zinc-800 dark:text-zinc-100">read-only</strong> mail scope. The access
          token is stored in your OS keychain — never in this app's database or a config file. Revoke access any
          time.
        </p>
      </Card>

      <div className="mb-6 flex gap-3">
        <a
          href="/api/v1/email-accounts/connect/google"
          className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          <Mail size={15} /> Connect Gmail
        </a>
        <a
          href="/api/v1/email-accounts/connect/microsoft"
          className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          <Mail size={15} /> Connect Outlook
        </a>
      </div>

      {emailAccounts.length === 0 ? (
        <EmptyState icon={<Mail size={20} />} title="No accounts connected yet" description="Connect Gmail or Outlook above to start scanning email for resumes." />
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {emailAccounts.map((a) => (
              <li key={a.id} className="flex items-center justify-between p-4 text-sm">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    <Mail size={15} />
                  </div>
                  <div>
                    <p className="font-medium text-zinc-900 dark:text-white">{a.email_address}</p>
                    <p className="text-zinc-500 dark:text-zinc-400">
                      {a.provider} · read-only · last scanned {a.last_scanned_at ?? "never"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => disconnect(a.id)}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                >
                  <Unplug size={14} /> Disconnect
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
