import type { ReactNode } from "react";
import { Card } from "../ui/card";

export function SectionCard({
  title,
  subtitle,
  action,
  children,
  className = "",
  id,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <Card id={id} className={className}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">{title}</h2>
          {subtitle && <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}
