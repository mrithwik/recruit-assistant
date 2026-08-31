import { CheckCircle2, Info, XCircle } from "lucide-react";
import { useToastStore } from "../../stores/toast-store";

const VARIANT_STYLES = {
  info: { bg: "bg-zinc-900 dark:bg-zinc-800", icon: Info },
  success: { bg: "bg-emerald-600", icon: CheckCircle2 },
  error: { bg: "bg-red-600", icon: XCircle },
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => {
        const { bg, icon: Icon } = VARIANT_STYLES[t.variant];
        return (
          <div
            key={t.id}
            className={`animate-fade-in-up flex items-center gap-2 rounded-lg px-3.5 py-2.5 text-sm text-white shadow-lg ${bg}`}
          >
            <Icon size={16} className="shrink-0" />
            {t.message}
            {t.action && (
              <button
                onClick={() => {
                  t.action?.onClick();
                  dismiss(t.id);
                }}
                className="ml-1 shrink-0 rounded-md border border-white/30 px-2 py-0.5 text-xs font-semibold hover:bg-white/10"
              >
                {t.action.label}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
