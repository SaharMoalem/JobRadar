import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  bookmarkOpportunity,
  transitionTracked,
  unbookmarkOpportunity,
} from './tracker.ts'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function stubOk() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ data: {}, error: null, meta: {} }),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function callOf(fetchMock: ReturnType<typeof stubOk>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return { url, init, headers: init.headers as Record<string, string> }
}

/**
 * `apiRequest` invents a correlation id when a caller omits one, so asserting the
 * header is merely present proves nothing. These assert the caller's own id survives.
 */
describe('tracker mutations forward the caller correlation id', () => {
  it('bookmarkOpportunity', async () => {
    const fetchMock = stubOk()
    await bookmarkOpportunity('jp-1', 'cid-bookmark')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/tracker/bookmarks')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ job_posting_id: 'jp-1' })
    expect(headers['X-Correlation-Id']).toBe('cid-bookmark')
  })

  it('unbookmarkOpportunity', async () => {
    const fetchMock = stubOk()
    await unbookmarkOpportunity('jp-1', 'cid-unbookmark')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/tracker/bookmarks/jp-1')
    expect(init.method).toBe('DELETE')
    expect(headers['X-Correlation-Id']).toBe('cid-unbookmark')
  })

  it('transitionTracked', async () => {
    const fetchMock = stubOk()
    await transitionTracked('jp-1', 'review', 'looks promising', 'cid-transition')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/tracker/jp-1/transitions')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      to_state: 'review',
      reason: 'looks promising',
    })
    expect(headers['X-Correlation-Id']).toBe('cid-transition')
  })

  it('encodes ids that need escaping', async () => {
    const fetchMock = stubOk()
    await unbookmarkOpportunity('jp/1 2', 'cid-encode')
    expect(callOf(fetchMock).url).toBe('/api/tracker/bookmarks/jp%2F1%202')
  })
})
