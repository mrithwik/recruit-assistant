import { NavLink } from "react-router-dom";
import { NAV_GROUPS } from "../../lib/nav";

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col gap-4 overflow-y-auto border-r border-zinc-200 bg-zinc-100 p-3 dark:border-zinc-800 dark:bg-zinc-900">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-600">
            {group.label}
          </p>
          <nav className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-white text-indigo-700 shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-indigo-300 dark:ring-zinc-700"
                        : "text-zinc-600 hover:bg-white/70 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/60 dark:hover:text-zinc-100"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span
                          className="absolute left-0 top-1/2 h-4 -translate-y-1/2 rounded-r-full bg-indigo-600"
                          style={{ width: 3 }}
                        />
                      )}
                      <Icon
                        size={17}
                        strokeWidth={2}
                        className={
                          isActive
                            ? "text-indigo-600 dark:text-indigo-400"
                            : "text-zinc-400 group-hover:text-zinc-600 dark:text-zinc-500 dark:group-hover:text-zinc-300"
                        }
                      />
                      {item.label}
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>
      ))}
    </aside>
  );
}
