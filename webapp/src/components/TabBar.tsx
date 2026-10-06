import { haptic } from "../tg";

export type Tab = "stock" | "record" | "journal";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "stock", label: "Остатки", icon: "M4 7h16M4 12h16M4 17h10" },
  { id: "record", label: "Записать", icon: "M12 5v14M5 12h14" },
  { id: "journal", label: "Журнал", icon: "M7 3v4M17 3v4M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" },
];

export function TabBar({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  return (
    <nav className="tabbar">
      {TABS.map((t) => (
        <button
          key={t.id}
          className={`tab ${active === t.id ? "active" : ""}`}
          onClick={() => {
            if (t.id !== active) haptic.select();
            onChange(t.id);
          }}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d={t.icon} />
          </svg>
          <span>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}
