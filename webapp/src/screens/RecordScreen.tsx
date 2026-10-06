import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { Segmented } from "../components/Segmented";
import { dmyToIso, humanDate, isoToDmy } from "../dates";
import { haptic, telegramUserName, useMainButton } from "../tg";
import type { CreatedOperation, Kind, Meta, Prefill, StockItem } from "../types";

const AUTHOR_KEY = "sklad.author";
const MAX_QTY = 10000;

function stockOf(items: StockItem[] | null, brand: string, flavor: string, pack: string): number | null {
  if (!items || !brand || !flavor || !pack) return null;
  const f = flavor.trim().toLocaleLowerCase("ru");
  const hit = items.find(
    (i) => i.brand === brand && i.pack === pack && i.flavor.toLocaleLowerCase("ru") === f,
  );
  return hit ? hit.qty : 0;
}

export function RecordScreen({
  meta,
  prefill,
  onRecorded,
}: {
  meta: Meta;
  prefill: Prefill | null;
  onRecorded: () => void;
}) {
  const todayIso = dmyToIso(meta.today);
  const [kind, setKind] = useState<Kind>(prefill ? "out" : "in");
  const [dateIso, setDateIso] = useState(todayIso);
  const [brand, setBrand] = useState(prefill?.brand ?? "");
  const [flavor, setFlavor] = useState(prefill?.flavor ?? "");
  const [pack, setPack] = useState(prefill?.pack ?? "");
  const [qty, setQty] = useState("1");
  const [author, setAuthor] = useState(
    () => localStorage.getItem(AUTHOR_KEY) || telegramUserName(),
  );
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreatedOperation | null>(null);
  const [stock, setStock] = useState<StockItem[] | null>(null);

  useEffect(() => {
    api.stock().then((r) => setStock(r.items)).catch(() => setStock(null));
  }, [result]);

  const qtyNum = Number(qty);
  const qtyValid = Number.isInteger(qtyNum) && qtyNum > 0 && qtyNum <= MAX_QTY;
  const valid = Boolean(brand && flavor.trim() && pack && qtyValid && dateIso);

  const current = stockOf(stock, brand, flavor, pack);
  const after = current === null || !qtyValid ? null : kind === "in" ? current + qtyNum : current - qtyNum;

  const flavorSuggestions = useMemo(() => {
    const known = meta.flavors[brand] ?? [];
    const q = flavor.trim().toLocaleLowerCase("ru");
    return known
      .filter((f) => f.toLocaleLowerCase("ru") !== q && (!q || f.toLocaleLowerCase("ru").includes(q)))
      .slice(0, 12);
  }, [meta.flavors, brand, flavor]);

  const submit = async () => {
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    setFieldErrors({});
    try {
      const created = await api.create({
        kind,
        date: isoToDmy(dateIso),
        brand,
        flavor: flavor.trim(),
        pack,
        qty: qtyNum,
        author: author.trim(),
      });
      if (author.trim()) localStorage.setItem(AUTHOR_KEY, author.trim());
      haptic.success();
      setResult(created);
      onRecorded();
    } catch (e) {
      haptic.error();
      const err = e as ApiError;
      setError(err.message);
      setFieldErrors(err.fields ?? {});
    } finally {
      setSubmitting(false);
    }
  };

  const startNew = () => {
    setResult(null);
    setQty("1");
    setFlavor("");
  };

  useMainButton({
    text: result ? "Новая запись" : kind === "in" ? "Записать приход" : "Записать расход",
    visible: true,
    enabled: result ? true : valid,
    loading: submitting,
    onClick: result ? startNew : submit,
  });

  if (result) {
    const op = result.operation;
    const isIn = op.kind === "Приход";
    return (
      <div className="page">
        <div className="result">
          <div className={`result-icon ${isIn ? "plus" : "minus"}`}>✓</div>
          <h1>{op.kind} записан</h1>
          <p className="hint">
            Накладная {result.doc_no} · строка {result.row}
          </p>
        </div>
        <div className="list">
          <div className="row static"><span className="row-label">Бренд</span><span>{op.brand}</span></div>
          <div className="row static"><span className="row-label">Вкус</span><span>{op.flavor}</span></div>
          <div className="row static"><span className="row-label">Фасовка</span><span>{op.pack}</span></div>
          <div className="row static">
            <span className="row-label">Количество</span>
            <span className={isIn ? "plus-text" : "minus-text"}>{isIn ? "+" : "−"}{op.qty}</span>
          </div>
          <div className="row static"><span className="row-label">Дата</span><span>{op.date}</span></div>
          <div className="row static"><span className="row-label">Внёс</span><span>{op.author}</span></div>
          <div className="row static">
            <span className="row-label">Остаток теперь</span>
            <span className={`qty ${result.stock_after <= 0 ? "low" : ""}`}>{result.stock_after}</span>
          </div>
        </div>
        {result.stock_after <= 0 && (
          <p className="footnote">Остаток {result.stock_after}, вкус сохранён в учёте.</p>
        )}
      </div>
    );
  }

  return (
    <div className="page form">
      <Segmented<Kind>
        value={kind}
        onChange={setKind}
        options={[
          { value: "in", label: "Приход", tone: "plus" },
          { value: "out", label: "Расход", tone: "minus" },
        ]}
      />

      {error && <div className="banner error">{error}</div>}

      <div className="list">
        <label className="field">
          <span className="field-label">Дата</span>
          <span className="field-control date-control">
            <span className="date-human">{humanDate(dateIso, todayIso)}</span>
            <input
              type="date"
              value={dateIso}
              max={todayIso}
              onChange={(e) => e.target.value && setDateIso(e.target.value)}
            />
          </span>
        </label>
        <label className="field">
          <span className="field-label">Бренд</span>
          <select
            className="field-control"
            value={brand}
            onChange={(e) => {
              setBrand(e.target.value);
              setFlavor("");
            }}
          >
            <option value="" disabled>
              Выберите
            </option>
            {meta.brands.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Вкус</span>
          <input
            className="field-control"
            value={flavor}
            placeholder={brand ? "Название вкуса" : "Сначала бренд"}
            disabled={!brand}
            autoComplete="off"
            enterKeyHint="done"
            onChange={(e) => setFlavor(e.target.value)}
          />
        </label>
      </div>
      {fieldErrors.brand && <p className="field-error">{fieldErrors.brand}</p>}
      {fieldErrors.flavor && <p className="field-error">{fieldErrors.flavor}</p>}

      {brand && flavorSuggestions.length > 0 && (
        <div className="chips scroll">
          {flavorSuggestions.map((f) => (
            <button
              key={f}
              className="chip"
              onClick={() => {
                haptic.select();
                setFlavor(f);
              }}
            >
              {f}
            </button>
          ))}
        </div>
      )}

      <h2 className="section-header">Фасовка</h2>
      <div className="chips grid">
        {meta.packs.map((p) => (
          <button
            key={p}
            className={`chip ${pack === p ? "selected" : ""}`}
            onClick={() => {
              haptic.select();
              setPack(p);
            }}
          >
            {p}
          </button>
        ))}
      </div>
      {fieldErrors.pack && <p className="field-error">{fieldErrors.pack}</p>}

      <h2 className="section-header">Количество</h2>
      <div className="stepper">
        <button
          aria-label="Меньше"
          disabled={!qtyValid || qtyNum <= 1}
          onClick={() => {
            haptic.select();
            setQty(String(Math.max(1, qtyNum - 1)));
          }}
        >
          −
        </button>
        <input
          inputMode="numeric"
          pattern="[0-9]*"
          value={qty}
          onChange={(e) => setQty(e.target.value.replace(/\D/g, "").slice(0, 5))}
        />
        <button
          aria-label="Больше"
          disabled={qtyValid && qtyNum >= MAX_QTY}
          onClick={() => {
            haptic.select();
            setQty(String(qtyValid ? qtyNum + 1 : 1));
          }}
        >
          +
        </button>
      </div>
      {fieldErrors.qty && <p className="field-error">{fieldErrors.qty}</p>}

      {current !== null && (
        <div className="stock-hint">
          <span>На складе: {current}</span>
          {after !== null && (
            <span className={after <= 0 ? "minus-text" : ""}>
              После записи: {after}
              {after <= 0 && kind === "out" ? " — вкус останется в учёте" : ""}
            </span>
          )}
        </div>
      )}

      <div className="list">
        <label className="field">
          <span className="field-label">Кто внёс</span>
          <input
            className="field-control"
            value={author}
            placeholder="Имя"
            autoComplete="off"
            enterKeyHint="done"
            onChange={(e) => setAuthor(e.target.value)}
          />
        </label>
      </div>
      {fieldErrors.date && <p className="field-error">{fieldErrors.date}</p>}
    </div>
  );
}
