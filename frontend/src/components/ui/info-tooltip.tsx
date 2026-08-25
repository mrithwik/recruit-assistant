import { useState } from "react";
import { Info } from "lucide-react";

export function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-label="More info"
        className="flex h-4 w-4 items-center justify-center rounded-full text-zinc-400 hover:text-indigo-600 dark:hover:text-indigo-400"
      >
        <Info size={13} />
      </button>
      {open && (
        <span className="absolute left-1/2 top-full z-10 mt-1.5 w-56 -translate-x-1/2 rounded-lg bg-zinc-900 px-2.5 py-2 text-xs font-normal normal-case leading-snug text-white shadow-lg dark:bg-zinc-700">
          {text}
        </span>
      )}
    </span>
  );
}
