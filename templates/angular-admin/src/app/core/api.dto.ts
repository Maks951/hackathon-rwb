// Базовые DTO продукта. Qwen дописывает доменные сущности.
export interface PageMeta {
  page: number;
  pageSize: number;
  total: number;
}

export interface ListResponse<T> {
  items: T[];
  meta?: PageMeta;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}