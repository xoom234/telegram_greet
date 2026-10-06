import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { haptic } from "../tg";
import type { Prefill, StockItem } from "../types";

export function StockScreen({
  version,
  onPick,
}: {
  version: number;
  onPick: (p: Prefill) => void;
}) {
  const [items, setItems] = useState<StockItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hideZero, setHideZero] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .stock()
      .then((r) => !cancelled && setItems(r.items))
      .catch((e: ApiError) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [version, reload]);

  const groups = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("ru");
    const map = new Map<string, StockItem[]>();
    for (const item of items ?? []) {
      if (hideZero && item.qty === 0) continue;
      const hay = `${item.brand} ${item.flavor}`.toLocaleLowerCase("ru");
      if (q && !hay.includes(q)) continue;
      const list = map.get(item.brand) ?? [];
      list.push(item);
      map.set(item.brand, list);
    }
    return [...map.entries()];
  }, [items, query, hideZero]);

  const shown = groups.flatMap(([, list]) => list);
  const totalUnits = shown.reduce((s, i) => s + i.qty, 0);

  return (
    <div className="page">
      <div className="toolbar">
        <div className="search">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" />
            <path d="M20 20l-4.5-4.5" />
          </svg>
          <input
            type="search"
            placeholder="Бренд или вкус"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button
          className={`chip ${hideZero ? "selected" : ""}`}
          onClick={() => {
            haptic.select();
            setHideZero((v) => !v);
          }}
        >
          Без нулей
        </button>
      </div>

      {error && (
        <div className="banner error">
          {error}{" "}
          <button className="text-button" onClick={() => setReload((r) => r + 1)}>
            Повторить
          </button>
        </div>
      )}

      {items === null && !error && <div className="spinner" />}

      {items !== null && (
        <>
          <div className="summary">
            <div>
              <span className="summary-value">{shown.length}</span>
              <span className="summary-label">позиций</span>
            </div>
            <div>
              <span className="summary-value">{totalUnits}</span>
              <span className="summary-label">единиц</span>
            </div>
          </div>

          {groups.length === 0 && (
            <div className="empty">
              <p>{query ? "Ничего не найдено" : "Склад пуст"}</p>
            </div>
          )}

          {groups.map(([brand, list]) => (
            <section key={brand} className="section">
              <h2 className="section-header">
                {brand}
                <span>{list.reduce((s, i) => s + i.qty, 0)}</span>
              </h2>
              <div className="list">
                {list.map((item) => (
                  <button
                    key={`${item.flavor}|${item.pack}`}
                    className="row"
                    onClick={() => onPick({ brand: item.brand, flavor: item.flavor, pack: item.pack })}
                  >
                    <span className="row-main">
                      <span className="row-title">{item.flavor}</span>
                      <span className="row-subtitle">{item.pack}</span>
                    </span>
                    <span className={`qty ${item.qty <= 0 ? "low" : ""}`}>{item.qty}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
          <p className="footnote">Нажмите на позицию, чтобы записать приход или расход</p>
        </>
      )}
    </div>
  );
}
