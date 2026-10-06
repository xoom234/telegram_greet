import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { dmyToIso } from "./dates";
import { DevButtons } from "./components/DevButtons";
import { TabBar, type Tab } from "./components/TabBar";
import { JournalScreen } from "./screens/JournalScreen";
import { RecordScreen } from "./screens/RecordScreen";
import { StockScreen } from "./screens/StockScreen";
import { insideTelegram, useBackButton } from "./tg";
import type { Meta, Prefill } from "./types";

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("stock");
  const [cameFrom, setCameFrom] = useState<Tab | null>(null);
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  const [stockVersion, setStockVersion] = useState(0);

  const loadMeta = useCallback(() => {
    setError(null);
    api
      .meta()
      .then(setMeta)
      .catch((e: ApiError) => setError(e.message));
  }, []);

  useEffect(loadMeta, [loadMeta]);

  const openTab = (next: Tab) => {
    setCameFrom(null);
    setPrefill(null);
    setTab(next);
  };

  const recordFromStock = (p: Prefill) => {
    setPrefill(p);
    setCameFrom("stock");
    setTab("record");
  };

  const goBack = () => {
    setTab(cameFrom ?? "stock");
    setCameFrom(null);
    setPrefill(null);
  };

  useBackButton(tab === "stock" ? null : goBack);

  const onRecorded = () => {
    setStockVersion((v) => v + 1);
    loadMeta();
  };

  if (error && !meta) {
    return (
      <div className="screen center">
        <div className="empty">
          <div className="empty-icon">⚠️</div>
          <p>{error}</p>
          {!insideTelegram && (
            <p className="hint">Откройте приложение через кнопку меню в боте @sklad_tabak_bot.</p>
          )}
          <button className="text-button" onClick={loadMeta}>
            Повторить
          </button>
        </div>
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="screen center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <>
      <main className="screen">
        {tab === "stock" && (
          <StockScreen version={stockVersion} onPick={recordFromStock} />
        )}
        {tab === "record" && (
          <RecordScreen
            key={prefill ? `${prefill.brand}|${prefill.flavor}|${prefill.pack}` : "new"}
            meta={meta}
            prefill={prefill}
            onRecorded={onRecorded}
          />
        )}
        {tab === "journal" && <JournalScreen todayIso={dmyToIso(meta.today)} />}
      </main>
      <TabBar active={tab} onChange={openTab} />
      <DevButtons />
    </>
  );
}
