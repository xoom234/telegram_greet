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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Authorization: `tma ${initData()}`,
        "Content-Type": "application/json",
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверьте интернет.");
  }
  const body = await response.json().catch(() => ({}));
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
