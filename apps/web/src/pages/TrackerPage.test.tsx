import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TrackerPage } from './TrackerPage.tsx'

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

const trackedRow = {
  job_posting_id: 'job-1',
  tracker_state: 'new',
  bookmarked: true,
  bookmarked_at: '2026-08-10T09:00:00+00:00',
  updated_at: '2026-08-10T09:00:00+00:00',
}

const posting = {
  id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
  location: 'Tel Aviv',
  url: 'https://acme.example.com/jobs/1',
  career_source_id: 'src-1',
  lifecycle_state: 'active',
}

function defaultFetch(url: string, init?: RequestInit) {
  const path = String(url)
  const method = (init?.method ?? 'GET').toUpperCase()

  if (path.endsWith('/tracker') && method === 'GET') {
    return Promise.resolve(jsonResponse([trackedRow]))
  }
  if (path.endsWith('/job-postings')) {
    return Promise.resolve(jsonResponse([posting]))
  }
  if (path.includes('/transitions') && method === 'GET') {
    return Promise.resolve(jsonResponse([]))
  }
  return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
}

function findCall(calls: unknown[][], path: string, method = 'POST'): unknown[] | undefined {
  return calls.find((call) => {
    const init = call[1] as RequestInit | undefined
    return String(call[0]).endsWith(path) && (init?.method ?? 'GET').toUpperCase() === method
  })
}

async function waitForReady(name: string) {
  await waitFor(() => {
    const button = screen.getByRole('button', { name }) as HTMLButtonElement
    expect(button.disabled).toBe(false)
  })
}

function nextStateSelect() {
  return screen.getByLabelText('Next state for Backend Engineer')
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('TrackerPage', () => {
  it('lists tracked opportunities with resolved titles', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch))

    render(<TrackerPage />)

    expect(await screen.findByText('Backend Engineer')).toBeTruthy()
    expect(screen.getByText('state: new')).toBeTruthy()
  })

  it('keeps the displayed state when the API rejects an illegal transition', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/transitions') && method === 'POST') {
        return Promise.resolve(
          jsonResponse(null, 409, {
            code: 'TRACKER_TRANSITION_INVALID',
            message: "Cannot move from 'new' to 'submitted'.",
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<TrackerPage />)
    await waitForReady('Remove bookmark')

    await user.selectOptions(nextStateSelect(), 'submitted')
    await user.click(screen.getByRole('button', { name: 'Apply state' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('TRACKER_TRANSITION_INVALID')
    // The row must still show the server's state, not the attempted one.
    expect(screen.getByText('state: new')).toBeTruthy()
  })

  it('disables Apply until a different state is selected', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch))

    render(<TrackerPage />)
    await waitForReady('Remove bookmark')

    expect((screen.getByRole('button', { name: 'Apply state' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('sends a correlation id and applies the state the server returns', async () => {
    const user = userEvent.setup()
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'page-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/transitions') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({ ...trackedRow, tracker_state: 'review' }, 200, null, {
            correlation_id: 'tracker-cid',
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<TrackerPage />)
    await waitForReady('Remove bookmark')

    await user.selectOptions(nextStateSelect(), 'review')
    await user.click(screen.getByRole('button', { name: 'Apply state' }))

    await waitFor(() => {
      const call = findCall(fetchMock.mock.calls, '/job-1/transitions')
      expect(call).toBeTruthy()
      const init = call?.[1] as RequestInit | undefined
      expect(JSON.parse(String(init?.body))).toEqual({
        to_state: 'review',
        reason: 'Moved to review from the tracker UI',
      })
      const headers = init?.headers as Record<string, string> | undefined
      expect(headers?.['X-Correlation-Id']).toBe('page-cid')
    })
    expect(await screen.findByText('state: review')).toBeTruthy()
  })

  it('renders an initial bookmark transition as the start of the timeline', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/transitions') && method === 'GET') {
        return Promise.resolve(
          jsonResponse([
            {
              job_posting_id: 'job-1',
              from_state: null,
              to_state: 'new',
              reason: 'bookmarked',
              correlation_id: 'cid-1',
              transitioned_at: '2026-08-10T09:00:00+00:00',
            },
          ]),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<TrackerPage />)
    await waitForReady('Show history')

    await user.click(screen.getByRole('button', { name: 'Show history' }))

    expect(await screen.findByText(/initial → new · bookmarked/)).toBeTruthy()
  })

  it('explains that removing a bookmark keeps the opportunity tracked', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/tracker/bookmarks/job-1') && method === 'DELETE') {
        return Promise.resolve(
          jsonResponse({ ...trackedRow, bookmarked: false, bookmarked_at: null }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'unbookmark-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    render(<TrackerPage />)
    await waitForReady('Remove bookmark')

    await user.click(screen.getByRole('button', { name: 'Remove bookmark' }))

    await waitFor(() => {
      const call = findCall(fetchMock.mock.calls, '/tracker/bookmarks/job-1', 'DELETE')
      expect(call).toBeTruthy()
      const headers = (call?.[1] as RequestInit | undefined)?.headers as
        | Record<string, string>
        | undefined
      expect(headers?.['X-Correlation-Id']).toBe('unbookmark-cid')
    })

    const status = await screen.findByRole('status')
    expect(status.textContent).toContain('stays tracked')
    expect(await screen.findByText(/not bookmarked/)).toBeTruthy()
  })
})
