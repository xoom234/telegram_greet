import { useEffect, useRef, useSyncExternalStore } from "react";
import type { WebApp } from "telegram-web-app";

const webApp: WebApp | undefined = window.Telegram?.WebApp;

/** true, когда приложение открыто внутри Telegram, а не в обычном браузере. */
export const insideTelegram = Boolean(webApp && webApp.platform !== "unknown" && webApp.initData);

export function initData(): string {
  return webApp?.initData || import.meta.env.VITE_DEV_INIT_DATA || "";
}

export function telegramUserName(): string {
  return webApp?.initDataUnsafe?.user?.first_name ?? "";
}

export function initTelegram(): void {
  if (!insideTelegram || !webApp) return;
  webApp.ready();
  webApp.expand();
  if (webApp.isVersionAtLeast("7.7")) webApp.disableVerticalSwipes();
  if (webApp.isVersionAtLeast("6.1")) {
    webApp.setHeaderColor("secondary_bg_color");
    webApp.setBackgroundColor("secondary_bg_color");
  }
  if (webApp.isVersionAtLeast("7.10")) webApp.setBottomBarColor("secondary_bg_color");
}

export const haptic = {
  success: () => webApp?.HapticFeedback?.notificationOccurred("success"),
  error: () => webApp?.HapticFeedback?.notificationOccurred("error"),
  warning: () => webApp?.HapticFeedback?.notificationOccurred("warning"),
  select: () => webApp?.HapticFeedback?.selectionChanged(),
};

export interface MainButtonConfig {
  text: string;
  visible: boolean;
  enabled: boolean;
  loading: boolean;
  onClick: () => void;
}

/** Состояние кнопок для браузерной замены нативных кнопок Telegram. */
interface DevButtons {
  main: MainButtonConfig | null;
  back: (() => void) | null;
}

let devState: DevButtons = { main: null, back: null };
const listeners = new Set<() => void>();

function setDev(patch: Partial<DevButtons>): void {
  devState = { ...devState, ...patch };
  listeners.forEach((l) => l());
}

export function useDevButtons(): DevButtons {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => devState,
  );
}

export function useMainButton(config: MainButtonConfig): void {
  const onClickRef = useRef(config.onClick);
  onClickRef.current = config.onClick;
  const { text, visible, enabled, loading } = config;

  useEffect(() => {
    if (!insideTelegram || !webApp) return;
    const handler = () => onClickRef.current();
    webApp.MainButton.onClick(handler);
    return () => {
      webApp.MainButton.offClick(handler);
      webApp.MainButton.hideProgress().hide();
    };
  }, []);

  useEffect(() => {
    if (insideTelegram && webApp) {
      const button = webApp.MainButton;
      button.setParams({
        text,
        is_visible: visible,
        is_active: enabled && !loading,
        color: enabled ? webApp.themeParams.button_color : webApp.themeParams.hint_color,
        text_color: webApp.themeParams.button_text_color,
      });
      if (loading) button.showProgress(false);
      else button.hideProgress();
      return;
    }
    setDev({
      main: visible ? { text, visible, enabled, loading, onClick: () => onClickRef.current() } : null,
    });
  }, [text, visible, enabled, loading]);

  useEffect(() => () => setDev({ main: null }), []);
}

export function useBackButton(onBack: (() => void) | null): void {
  const onBackRef = useRef(onBack);
  onBackRef.current = onBack;
  const visible = onBack !== null;

  useEffect(() => {
    if (!insideTelegram || !webApp) {
      setDev({ back: visible ? () => onBackRef.current?.() : null });
      return;
    }
    if (!visible) {
      webApp.BackButton.hide();
      return;
    }
    const handler = () => onBackRef.current?.();
    webApp.BackButton.onClick(handler);
    webApp.BackButton.show();
    return () => {
      webApp.BackButton.offClick(handler);
    };
  }, [visible]);
}
