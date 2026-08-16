import type { ApiEnvelope, ApiRequestOptions, ApiSuccess } from './types.ts'

export class ApiClientError extends Error {
  readonly code: string
  readonly status: number
  readonly meta: Record<string, unknown>

  constructor(
    code: string,
    message: string,
    status = 0,
    meta: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.status = status
    this.meta = meta
  }
}

export function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || String(raw).trim() === '') {
    return '/api'
  }
  return String(raw).replace(/\/$/, '')
}

export function newCorrelationId(): string {
  return crypto.randomUUID()
}

export function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'name' in err &&
    (err as { name: unknown }).name === 'AbortError'
  )
}

function isMutation(method: string): boolean {
  return !['GET', 'HEAD'].includes(method)
}

function parseEnvelope<T>(value: unknown, status: number): ApiEnvelope<T> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiClientError(
      'INVALID_RESPONSE',
      `Response was not a JSON object (HTTP ${status})`,
      status,
    )
  }
  return value as ApiEnvelope<T>
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<ApiSuccess<T>> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (isMutation(method)) {
    const correlation = (options.correlationId ?? newCorrelationId()).trim()
    headers['X-Correlation-Id'] = correlation || newCorrelationId()
  }

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const url = `${apiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    })
  } catch (err) {
    if (isAbortError(err)) {
      throw err
    }
    const message = err instanceof Error ? err.message : 'Network request failed'
    throw new ApiClientError('NETWORK_ERROR', message, 0)
  }

  let envelope: ApiEnvelope<T>
  try {
    envelope = parseEnvelope<T>(await response.json(), response.status)
  } catch (err) {
    if (err instanceof ApiClientError) {
      throw err
    }
    throw new ApiClientError(
      'INVALID_RESPONSE',
      `Response was not valid JSON (HTTP ${response.status})`,
      response.status,
    )
  }

  if (envelope.error?.code) {
    throw new ApiClientError(
      envelope.error.code,
      envelope.error.message,
      response.status,
      envelope.meta ?? {},
    )
  }

  if (!response.ok) {
    throw new ApiClientError(
      'HTTP_ERROR',
      `Request failed with HTTP ${response.status}`,
      response.status,
      envelope.meta ?? {},
    )
  }

  return {
    data: envelope.data as T,
    meta: envelope.meta ?? {},
  }
}
