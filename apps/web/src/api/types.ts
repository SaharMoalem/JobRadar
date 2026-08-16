export type ApiErrorBody = {
  code: string
  message: string
}

export type ApiEnvelope<T> = {
  data: T | null
  error: ApiErrorBody | null
  meta: Record<string, unknown>
}

export type ApiSuccess<T> = {
  data: T
  meta: Record<string, unknown>
}

export type ApiRequestOptions = {
  method?: string
  body?: unknown
  correlationId?: string
  signal?: AbortSignal
}
