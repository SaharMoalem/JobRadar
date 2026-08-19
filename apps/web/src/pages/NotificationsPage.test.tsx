import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NotificationsPage } from './NotificationsPage.tsx'

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

const inboxItem = {
  id: 'del-1',
  channel_id: 'in_app',
  kind: 'immediate_alert',
  source_id: 'alert-1',
  correlation_id: 'cid-1',
  run_context: 'run-1',
  status: 'delivered',
  detail: 'High-match alert: Backend Engineer at Acme (score 92)',
  created_at: '2026-08-19T09:00:00+00:00',
}

function defaultFetch(url: string, init?: RequestInit) {
  const path = String(url)
  const method = (init?.method ?? 'GET').toUpperCase()
  if (path.endsWith('/notifications/in-app') && method === 'GET') {
    return Promise.resolve(jsonResponse([]))
  }
  if (path.endsWith('/notifications/deliveries') && method === 'GET') {
    return Promise.resolve(jsonResponse([]))
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

describe('NotificationsPage', () => {
  it('shows failed_count on a 200 without an error banner', async () => {
    const user = userEvent.setup()
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'page-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/notifications/deliver') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            delivered_count: 1,
            failed_count: 1,
            skipped_missing_source_count: 0,
            run_context: 'run-1',
            kind: 'immediate_alert',
            deliveries: [inboxItem],
          }),
        )
      }
      if (path.endsWith('/notifications/in-app') && method === 'GET') {
        return Promise.resolve(jsonResponse([inboxItem]))
      }
      if (path.endsWith('/notifications/deliveries') && method === 'GET') {
        return Promise.resolve(jsonResponse([inboxItem]))
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<NotificationsPage />)
    await settled(container)

    await user.type(screen.getByLabelText('Run context'), 'run-1')
    await user.click(screen.getByRole('button', { name: 'Deliver' }))

    const status = await screen.findByRole('status')
    expect(status.textContent).toContain('failed 1')
    expect(screen.queryByRole('alert')).toBeNull()

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([href, init]) => {
        return (
          String(href).endsWith('/notifications/deliver') &&
          (init as RequestInit | undefined)?.method === 'POST'
        )
      })
      expect(post).toBeTruthy()
      const init = post?.[1] as RequestInit | undefined
      expect(JSON.parse(String(init?.body))).toEqual({
        kind: 'immediate_alert',
        run_context: 'run-1',
        channels: ['in_app', 'email'],
      })
      const headers = init?.headers as Record<string, string> | undefined
      expect(headers?.['X-Correlation-Id']).toBe('page-cid')
    })
  })

  it('renders in-app inbox details', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        const path = String(url)
        if (path.endsWith('/notifications/in-app')) {
          return Promise.resolve(jsonResponse([inboxItem]))
        }
        return defaultFetch(url, init)
      }),
    )

    const { container } = render(<NotificationsPage />)
    await settled(container)

    expect(await screen.findByText(/High-match alert: Backend Engineer at Acme/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('disables Deliver when no channel is selected', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(defaultFetch)
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<NotificationsPage />)
    await settled(container)

    await user.click(screen.getByRole('checkbox', { name: 'in_app' }))
    await user.click(screen.getByRole('checkbox', { name: 'email' }))

    const deliver = screen.getByRole('button', { name: 'Deliver' }) as HTMLButtonElement
    expect(deliver.disabled).toBe(true)

    await user.click(deliver)
    const posts = fetchMock.mock.calls.filter(([href, init]) => {
      return (
        String(href).endsWith('/notifications/deliver') &&
        (init as RequestInit | undefined)?.method === 'POST'
      )
    })
    expect(posts).toHaveLength(0)
  })
})
