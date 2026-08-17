import { describe, expect, it } from 'vitest'

import { ApiClientError } from '../api/client.ts'
import {
  combinedError,
  errorMessage,
  formatDate,
  formatTimestamp,
  rejections,
  safeHref,
  splitCsv,
} from './ui.ts'

describe('errorMessage', () => {
  it('surfaces the API code and message', () => {
    const err = new ApiClientError('TRACKER_TRANSITION_UNCHANGED', 'already in review', 409)
    expect(errorMessage(err)).toBe('TRACKER_TRANSITION_UNCHANGED: already in review')
  })

  it('falls back for unknown failures', () => {
    expect(errorMessage(new TypeError('fetch failed'))).toBe('Request failed')
  })
})

describe('combinedError', () => {
  it('returns null when nothing failed', () => {
    expect(combinedError([])).toBeNull()
  })

  it('returns the single failure verbatim', () => {
    const err = new ApiClientError('TRACKER_NOT_FOUND', 'missing', 404)
    expect(combinedError([err])).toBe('TRACKER_NOT_FOUND: missing')
  })

  it('counts additional failures with plural agreement', () => {
    const err = new ApiClientError('A', 'first', 500)
    const other = new ApiClientError('B', 'second', 500)
    expect(combinedError([err, other])).toBe('A: first (and 1 more request failed)')
    expect(combinedError([err, other, other])).toBe('A: first (and 2 more requests failed)')
  })
})

describe('rejections', () => {
  it('keeps only the rejected reasons, in order', () => {
    const results: PromiseSettledResult<unknown>[] = [
      { status: 'fulfilled', value: 1 },
      { status: 'rejected', reason: 'first' },
      { status: 'rejected', reason: 'second' },
    ]
    expect(rejections(results)).toEqual(['first', 'second'])
  })
})

describe('formatTimestamp / formatDate', () => {
  it('renders a parseable instant', () => {
    expect(formatTimestamp('2026-08-16T10:30:00Z')).not.toBe('2026-08-16T10:30:00Z')
    expect(formatDate('2026-08-16T10:30:00Z')).not.toBe('2026-08-16T10:30:00Z')
  })

  it('passes unparseable input through rather than showing "Invalid Date"', () => {
    expect(formatTimestamp('whenever')).toBe('whenever')
    expect(formatDate('')).toBe('')
  })
})

describe('safeHref', () => {
  it('allows absolute web URLs', () => {
    expect(safeHref('https://example.com/jobs/1')).toBe('https://example.com/jobs/1')
    expect(safeHref('http://example.com')).toBe('http://example.com/')
  })

  it('rejects non-web schemes', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull()
    expect(safeHref('data:text/html,<script></script>')).toBeNull()
    expect(safeHref('file:///etc/passwd')).toBeNull()
  })

  it('rejects relative values instead of pointing them at our own origin', () => {
    expect(safeHref('/jobs/1')).toBeNull()
    expect(safeHref('not a url')).toBeNull()
    expect(safeHref('')).toBeNull()
  })
})

describe('splitCsv', () => {
  it('trims parts and drops empties', () => {
    expect(splitCsv(' python , , rust ')).toEqual(['python', 'rust'])
    expect(splitCsv('')).toEqual([])
  })
})
