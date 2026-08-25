import type { HTMLAttributes, ReactNode } from "react";

export function Card({
  children,
  className = "",
  interactive = false,
  selected = false,
  ...props
}: HTMLAttributes<HTMLDivElement> & { children: ReactNode; interactive?: boolean; selected?: boolean }) {
  return (
    <div
      className={`rounded-xl border bg-white p-4 shadow-sm transition-all dark:bg-zinc-900 ${
        selected
          ? "border-indigo-400 ring-2 ring-indigo-100 dark:border-indigo-500 dark:ring-indigo-500/20"
          : "border-zinc-200 dark:border-zinc-800"
      } ${interactive ? "cursor-pointer hover:border-indigo-300 hover:shadow-md dark:hover:border-indigo-700" : ""} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardDashed({ children, className = "", ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <div
      className={`rounded-xl border-2 border-dashed border-zinc-200 p-4 dark:border-zinc-800 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
