import { useLocation, useNavigate } from "react-router-dom";
import { LogOut, Moon, Sparkles, Sun } from "lucide-react";
import { NAV_ITEMS } from "../../lib/nav";
import { useSettingsStore } from "../../stores/settings-store";
import { useAuthStore } from "../../stores/auth-store";

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const theme = useSettingsStore((s) => s.theme);
  const toggleTheme = useSettingsStore((s) => s.toggleTheme);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const current = NAV_ITEMS.find((n) => n.path === location.pathname);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="flex items-center justify-between border-b border-zinc-200 bg-zinc-100 px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-white">
          <Sparkles size={15} strokeWidth={2.5} />
        </div>
        <span className="font-display text-[15px] font-semibold text-zinc-900 dark:text-white">Recruit Assistant</span>
        {current && (
          <>
            <span className="text-zinc-300 dark:text-zinc-700">/</span>
            <span className="text-sm text-zinc-500 dark:text-zinc-400">{current.label}</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={toggleTheme}
          aria-label="Toggle theme"
          className="flex h-8 w-8 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
        </button>
        {user && (
          <>
            <span className="ml-1 hidden text-xs text-zinc-400 sm:inline">{user.email}</span>
            <button
              onClick={handleLogout}
              aria-label="Sign out"
              title="Sign out"
              className="flex h-8 w-8 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-red-600 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-red-400"
            >
              <LogOut size={15} />
            </button>
          </>
        )}
      </div>
    </header>
  );
}
