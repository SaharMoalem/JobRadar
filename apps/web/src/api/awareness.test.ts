import { afterEach, describe, expect, it, vi } from 'vitest'

import { runImmediateAlerts, saveAlertConfig } from './alerts.ts'
import { runMorningDigest } from './digests.ts'
import { deliverNotifications } from './notifications.ts'

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
describe('awareness mutations forward the caller correlation id', () => {
  it('saveAlertConfig', async () => {
    const fetchMock = stubOk()
    await saveAlertConfig(90, 'cid-alert-cfg')
    const { url, init, headers } = callOf(fetchMock)
    expect(url).toBe('/api/immediate-alert-config')
    expect(init.method).toBe('PUT')
    expect(headers['X-Correlation-Id']).toBe('cid-alert-cfg')
  })

  it('runImmediateAlerts', async () => {
    const fetchMock = stubOk()
    await runImmediateAlerts('cid-alert-run')
    expect(callOf(fetchMock).headers['X-Correlation-Id']).toBe('cid-alert-run')
  })

  it('runImmediateAlerts omits whitespace-only run_context', async () => {
    const fetchMock = stubOk()
    await runImmediateAlerts('cid-alert-blank', '   ')
    const { init, headers } = callOf(fetchMock)
    expect(JSON.parse(String(init.body))).toEqual({})
    expect(headers['X-Correlation-Id']).toBe('cid-alert-blank')
  })

  it('runMorningDigest trims run_context', async () => {
    const fetchMock = stubOk()
    await runMorningDigest('cid-digest-run', '2026-08-19')
    const { url, init, headers } = callOf(fetchMock)
    expect(url).toBe('/api/digests/morning/run')
    expect(JSON.parse(String(init.body))).toEqual({ run_context: '2026-08-19' })
    expect(headers['X-Correlation-Id']).toBe('cid-digest-run')
  })

  it('deliverNotifications omits blank optional fields', async () => {
    const fetchMock = stubOk()
    await deliverNotifications({ kind: 'morning_digest' }, 'cid-deliver')
    const { init, headers } = callOf(fetchMock)
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'morning_digest' })
    expect(headers['X-Correlation-Id']).toBe('cid-deliver')
  })
})
