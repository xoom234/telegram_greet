import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { humanDate, isoToDmy, shiftIso } from "../dates";
import { haptic } from "../tg";
import type { Movement, OperationsResponse } from "../types";

export function JournalScreen({ todayIso }: { todayIso: string }) {
  const [dateIso, setDateIso] = useState(todayIso);
  const [loaded, setLoaded] = useState<{ iso: string; data?: OperationsResponse; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .operations(isoToDmy(dateIso))
      .then((data) => !cancelled && setLoaded({ iso: dateIso, data }))
      .catch((e: ApiError) => !cancelled && setLoaded({ iso: dateIso, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [dateIso]);

  const current = loaded?.iso === dateIso ? loaded : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;

  const byAuthor = useMemo(() => {
    const map = new Map<string, Movement[]>();
    for (const m of data?.items ?? []) {
      const key = m.author || "Без имени";
      map.set(key, [...(map.get(key) ?? []), m]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b, "ru"));
  }, [data]);

  const shift = (days: number) => {
    haptic.select();
    setDateIso((d) => shiftIso(d, days));
  };

  return (
    <div className="page">
      <div className="date-nav">
        <button aria-label="Предыдущий день" onClick={() => shift(-1)}>
          ‹
        </button>
        <label className="date-nav-label">
          <span>{humanDate(dateIso, todayIso)}</span>
          <small>{isoToDmy(dateIso)}</small>
          <input
            type="date"
            value={dateIso}
            max={todayIso}
            onChange={(e) => e.target.value && setDateIso(e.target.value)}
          />
        </label>
        <button aria-label="Следующий день" disabled={dateIso >= todayIso} onClick={() => shift(1)}>
          ›
        </button>
      </div>

      {error && <div className="banner error">{error}</div>}
      {!data && !error && <div className="spinner" />}

      {data && (
        <>
          <div className="summary">
            <div>
              <span className="summary-value plus-text">+{data.total_in}</span>
              <span className="summary-label">приход</span>
            </div>
            <div>
              <span className="summary-value minus-text">−{data.total_out}</span>
              <span className="summary-label">расход</span>
            </div>
            <div>
              <span className="summary-value">{data.items.length}</span>
              <span className="summary-label">операций</span>
            </div>
          </div>

          {data.items.length === 0 && (
            <div className="empty">
              <p>Операций за этот день нет</p>
            </div>
          )}

          {byAuthor.map(([author, list]) => (
            <section key={author} className="section">
              <h2 className="section-header">
                {author}
                <span>{list.length}</span>
              </h2>
              <div className="list">
                {list.map((m) => {
                  const isIn = m.kind === "Приход";
                  return (
                    <div key={m.row} className="row static">
                      <span className="row-main">
                        <span className="row-title">
                          {m.brand} · {m.flavor}
                        </span>
                        <span className="row-subtitle">
                          {m.pack} · {m.doc_no}
                        </span>
                      </span>
                      <span className={isIn ? "plus-text strong" : "minus-text strong"}>
                        {isIn ? "+" : "−"}
                        {m.qty}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}

          {data.undated > 0 && (
            <p className="footnote">Без даты в таблице: {data.undated} записей</p>
          )}
        </>
      )}
    </div>
  );
}
