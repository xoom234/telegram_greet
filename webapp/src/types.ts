export type Kind = "in" | "out";

export interface Meta {
  brands: string[];
  packs: string[];
  flavors: Record<string, string[]>;
  today: string;
}

export interface StockItem {
  brand: string;
  flavor: string;
  pack: string;
  qty: number;
}

export interface StockResponse {
  brand: string | null;
  items: StockItem[];
  total_positions: number;
  total_units: number;
}

export interface Movement {
  row: number;
  date: string;
  doc_no: string;
  brand: string;
  flavor: string;
  pack: string;
  qty: number;
  kind: string;
  author: string;
}

export interface OperationsResponse {
  date: string;
  items: Movement[];
  total_in: number;
  total_out: number;
  undated: number;
}

export interface NewOperation {
  kind: Kind;
  date: string;
  brand: string;
  flavor: string;
  pack: string;
  qty: number;
  author: string;
  request_id?: string;
}

export interface CreatedOperation {
  row: number;
  doc_no: string;
  operation: Omit<NewOperation, "kind" | "request_id"> & { kind: string };
  stock_after: number;
  duplicate: boolean;
}

export interface Prefill {
  brand: string;
  flavor: string;
  pack: string;
}
