import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError, apiRequest } from './client.ts'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('apiRequest', () => {
  it('returns data and meta from a successful envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'src-1' }],
          error: null,
          meta: { correlation_id: 'c1' },
        }),
      }),
    )

    const result = await apiRequest<{ id: string }[]>('/career-sources')

    expect(result.data).toEqual([{ id: 'src-1' }])
    expect(result.meta).toEqual({ correlation_id: 'c1' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/career-sources',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('throws a typed ApiClientError from an envelope error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({
          data: null,
          error: { code: 'NOTIFICATION_CHANNEL_UNKNOWN', message: 'Unknown channel.' },
          meta: { correlation_id: 'c2' },
        }),
      }),
    )

    const error = await apiRequest('/notifications/deliver', {
      method: 'POST',
      body: { kind: 'immediate_alert' },
      correlationId: 'c2',
    }).catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error).toMatchObject({
      code: 'NOTIFICATION_CHANNEL_UNKNOWN',
      message: 'Unknown channel.',
      status: 400,
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/notifications/deliver',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Correlation-Id': 'c2',
        }),
      }),
    )
  })

  it('throws NETWORK_ERROR when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const error = await apiRequest('/job-postings').catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error).toMatchObject({
      code: 'NETWORK_ERROR',
      status: 0,
    })
  })

  it('throws INVALID_RESPONSE when the body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError('Unexpected token')
        },
      }),
    )

    const error = await apiRequest('/career-sources').catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error).toMatchObject({
      code: 'INVALID_RESPONSE',
      status: 502,
    })
  })

  it('does not send a blank correlation id on mutations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: {}, error: null, meta: {} }),
      }),
    )

    await apiRequest('/career-sources', { method: 'POST', body: {}, correlationId: '   ' })

    const init = vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers['X-Correlation-Id']?.trim()).toBeTruthy()
    expect(headers['X-Correlation-Id']).not.toBe('   ')
  })

  it('rethrows AbortError instead of wrapping it as NETWORK_ERROR', async () => {
    const abort = Object.assign(new Error('Aborted'), { name: 'AbortError' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))

    const error = await apiRequest('/career-sources').catch((err: unknown) => err)

    expect(error).toBe(abort)
    expect(error).not.toBeInstanceOf(ApiClientError)
  })

  it('throws INVALID_RESPONSE when JSON is not an envelope object', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => null,
      }),
    )

    const error = await apiRequest('/career-sources').catch((err: unknown) => err)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error).toMatchObject({ code: 'INVALID_RESPONSE', status: 200 })
  })
})
