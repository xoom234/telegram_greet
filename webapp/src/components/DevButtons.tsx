import { insideTelegram, useDevButtons } from "../tg";

/** Замена нативных кнопок Telegram при открытии в обычном браузере. */
export function DevButtons() {
  const { main, back } = useDevButtons();
  if (insideTelegram) return null;
  return (
    <>
      {back && (
        <button className="dev-back" onClick={back}>
          ‹ Назад
        </button>
      )}
      {main && (
        <div className="dev-main">
          <button disabled={!main.enabled || main.loading} onClick={main.onClick}>
            {main.loading ? "…" : main.text}
          </button>
        </div>
      )}
    </>
  );
}
