import type {
  CreatedOperation,
  Meta,
  NewOperation,
  OperationsResponse,
  StockResponse,
} from "./types";
import { initData } from "./tg";

export class ApiError extends Error {
  status: number;
  fields: Record<string, string>;

  constructor(status: number, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

const TIMEOUT_MS = 25_000;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  let body: { error?: string; fields?: Record<string, string> };
  try {
    response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        Authorization: `tma ${initData()}`,
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
    body = await response.json().catch(() => ({}));
  } catch {
    throw new ApiError(
      0,
      controller.signal.aborted
        ? "Сервер не ответил вовремя. Проверьте интернет и повторите."
        : "Нет связи с сервером. Проверьте интернет.",
    );
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      body.error || `Ошибка сервера (${response.status})`,
      body.fields || {},
    );
  }
  return body as T;
}

export const api = {
  meta: () => request<Meta>("/api/v1/meta"),
  stock: () => request<StockResponse>("/api/v1/stock"),
  operations: (date: string) =>
    request<OperationsResponse>(`/api/v1/operations?date=${encodeURIComponent(date)}`),
  create: (op: NewOperation) =>
    request<CreatedOperation>("/api/v1/operations", {
      method: "POST",
      body: JSON.stringify(op),
    }),
};
