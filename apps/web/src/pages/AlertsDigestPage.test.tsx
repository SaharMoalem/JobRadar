import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AlertsDigestPage } from './AlertsDigestPage.tsx'

function jsonResponse(
  data: unknown,
  status = 200,
  error: unknown = null,
  meta: Record<string, unknown> = {},
) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({ data, error, meta }),
  }
}

const sampleAlert = {
  id: 'alert-1',
  job_posting_id: 'job-1',
  role_summary: 'Backend Engineer at Acme (Tel Aviv)',
  match_score: 92,
  deep_link: '/job-postings/job-1',
  run_context: 'run-1',
  correlation_id: 'cid-1',
  created_at: '2026-08-19T08:00:00+00:00',
}

const noopDigest = {
  id: 'digest-1',
  run_context: '2026-08-19',
  correlation_id: 'cid-2',
  digest_date: '2026-08-19',
  is_noop: true,
  skipped_below_threshold_count: 3,
  skipped_missing_score_count: 0,
  skipped_missing_posting_count: 0,
  new_items: [],
  updated_items: [],
  expired_items: [],
  top_recommendations: [],
  created_at: '2026-08-19T08:05:00+00:00',
}

function defaultFetch(url: string, init?: RequestInit) {
  const path = String(url)
  const method = (init?.method ?? 'GET').toUpperCase()

  if (path.endsWith('/immediate-alert-config') && method === 'GET') {
    return Promise.resolve(jsonResponse({ config_version: 'v1', alert_threshold: 90 }))
  }
  if (path.endsWith('/morning-digest-config') && method === 'GET') {
    return Promise.resolve(
      jsonResponse({
        config_version: 'v1',
        digest_threshold: 80,
        digest_window_hours: 24,
        top_n: 5,
      }),
    )
  }
  if (path.endsWith('/alerts/immediate') && method === 'GET') {
    return Promise.resolve(jsonResponse([]))
  }
  if (path.endsWith('/digests/morning') && method === 'GET') {
    return Promise.resolve(jsonResponse([noopDigest]))
  }
  return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
}

async function settled(container: HTMLElement) {
  const section = container.querySelector('section')
  await waitFor(() => {
    expect(section?.getAttribute('aria-busy')).toBe('false')
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AlertsDigestPage', () => {
  it('saves the alert threshold through PUT', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/immediate-alert-config') && method === 'PUT') {
        return Promise.resolve(
          jsonResponse({ config_version: 'v1', alert_threshold: 85 }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<AlertsDigestPage />)
    await settled(container)

    const input = screen.getByLabelText('Alert threshold') as HTMLInputElement
    expect(input.min).toBe('0')
    expect(input.max).toBe('100')
    expect(input.step).toBe('1')
    expect(input.required).toBe(true)
    const windowInput = screen.getByLabelText('Window hours') as HTMLInputElement
    expect(windowInput.min).toBe('1')
    expect(windowInput.max).toBe('8760')
    const topN = screen.getByLabelText('Top N') as HTMLInputElement
    expect(topN.min).toBe('1')
    expect(topN.max).toBe('10')

    await user.clear(input)
    await user.type(input, '85')
    await user.click(screen.getByRole('button', { name: 'Save alert config' }))

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([href, init]) => {
        return (
          String(href).endsWith('/immediate-alert-config') &&
          (init as RequestInit | undefined)?.method === 'PUT'
        )
      })
      expect(put).toBeTruthy()
      const init = put?.[1] as RequestInit | undefined
      expect(JSON.parse(String(init?.body))).toEqual({
        alert_threshold: 85,
        config_version: 'v1',
      })
    })
  })

  it('sends a correlation id when running alerts and lists the result', async () => {
    const user = userEvent.setup()
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'page-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    let alertListGets = 0
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/alerts/immediate/run') && method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            {
              triggered_count: 1,
              skipped_below_threshold_count: 0,
              skipped_duplicate_count: 0,
              skipped_missing_posting_count: 0,
              run_context: 'run-1',
              alerts: [sampleAlert],
            },
            200,
            null,
            { correlation_id: 'page-cid' },
          ),
        )
      }
      if (path.endsWith('/alerts/immediate') && method === 'GET') {
        alertListGets += 1
        return Promise.resolve(jsonResponse(alertListGets > 1 ? [sampleAlert] : []))
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<AlertsDigestPage />)
    await settled(container)

    expect(screen.queryByText(/Backend Engineer at Acme/)).toBeNull()
    expect(screen.getByText(/No immediate alerts yet/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Run immediate alerts' }))

    await waitFor(() => {
      const run = fetchMock.mock.calls.find(([href, init]) => {
        return (
          String(href).endsWith('/alerts/immediate/run') &&
          (init as RequestInit | undefined)?.method === 'POST'
        )
      })
      expect(run).toBeTruthy()
      const headers = (run?.[1] as RequestInit | undefined)?.headers as
        | Record<string, string>
        | undefined
      expect(headers?.['X-Correlation-Id']).toBe('page-cid')
    })
    expect(await screen.findByText(/Backend Engineer at Acme/)).toBeTruthy()
    expect(await screen.findByRole('status')).toBeTruthy()
    expect(alertListGets).toBeGreaterThanOrEqual(2)
  })

  it('keeps Run available when alert config GET fails', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/immediate-alert-config') && method === 'GET') {
        return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
      }
      if (path.endsWith('/alerts/immediate/run') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            triggered_count: 0,
            skipped_below_threshold_count: 0,
            skipped_duplicate_count: 0,
            skipped_missing_posting_count: 0,
            run_context: 'run-1',
            alerts: [],
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<AlertsDigestPage />)
    await settled(container)

    expect(screen.queryByRole('button', { name: 'Save alert config' })).toBeNull()
    const run = screen.getByRole('button', { name: 'Run immediate alerts' }) as HTMLButtonElement
    expect(run.disabled).toBe(false)

    await user.click(run)
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([href, init]) => {
        return (
          String(href).endsWith('/alerts/immediate/run') &&
          (init as RequestInit | undefined)?.method === 'POST'
        )
      })
      expect(post).toBeTruthy()
    })
  })

  it('shows a no-op digest as a sentence without an error alert', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch))

    const { container } = render(<AlertsDigestPage />)
    await settled(container)

    expect(await screen.findByText(/No-op digest/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
