import { afterEach, describe, expect, it, vi } from 'vitest'

import { approveOutbound, deliverOutbound, generateDraft, listDrafts } from './drafts.ts'

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
describe('draft mutations forward the caller correlation id', () => {
  it('generateDraft', async () => {
    const fetchMock = stubOk()
    await generateDraft('jp-1', 'recruiter_message', 'cid-generate')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/draft-artifacts/generate')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({
      job_posting_id: 'jp-1',
      kind: 'recruiter_message',
    })
    expect(headers['X-Correlation-Id']).toBe('cid-generate')
  })

  it('approveOutbound', async () => {
    const fetchMock = stubOk()
    await approveOutbound('art-1', 'cid-approve')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/draft-artifacts/art-1/approve-outbound')
    expect(init.method).toBe('POST')
    expect(headers['X-Correlation-Id']).toBe('cid-approve')
  })

  it('deliverOutbound', async () => {
    const fetchMock = stubOk()
    await deliverOutbound('art-1', 'email', 'cid-deliver')
    const { url, init, headers } = callOf(fetchMock)

    expect(url).toBe('/api/outbound/deliver')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ artifact_id: 'art-1', channel: 'email' })
    expect(headers['X-Correlation-Id']).toBe('cid-deliver')
  })
})

describe('listDrafts', () => {
  it('scopes the query to one posting and encodes the id', async () => {
    const fetchMock = stubOk()
    await listDrafts('jp/1')
    expect(callOf(fetchMock).url).toBe('/api/draft-artifacts?job_posting_id=jp%2F1')
  })
})
