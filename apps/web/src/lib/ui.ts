import { ApiClientError } from '../api/client.ts'

/** Per-section load tracking so a list never explains an emptiness it has not confirmed. */
export type LoadState = 'loading' | 'ready' | 'failed'

export function errorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    return `${err.code}: ${err.message}`
  }
  return 'Request failed'
}

export function combinedError(failures: unknown[]): string | null {
  if (failures.length === 0) {
    return null
  }
  const first = errorMessage(failures[0])
  if (failures.length === 1) {
    return first
  }
  return `${first} (and ${failures.length - 1} more request${failures.length > 2 ? 's' : ''} failed)`
}

export function rejections(results: PromiseSettledResult<unknown>[]): unknown[] {
  return results
    .filter((item): item is PromiseRejectedResult => item.status === 'rejected')
    .map((item) => item.reason)
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString()
}

/**
 * Postings come from crawled pages, so only absolute web URLs are rendered as links.
 * No base is supplied on purpose: resolving a malformed value against our own origin
 * would produce a confident link back at the dashboard.
 */
export function safeHref(raw: string): string | null {
  try {
    const parsed = new URL(raw)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null
  } catch {
    return null
  }
}

export function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}
