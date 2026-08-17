import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DraftsPage } from './DraftsPage.tsx'

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

const posting = {
  id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
  location: 'Tel Aviv',
  url: 'https://acme.example.com/jobs/1',
  career_source_id: 'src-1',
  lifecycle_state: 'active',
}

const draft = {
  id: 'draft-1',
  job_posting_id: 'job-1',
  kind: 'recruiter_message',
  content: '[DRAFT] Hello there.',
  source_reference: 'job-1',
  status: 'draft',
  is_latest: true,
  correlation_id: 'cid-1',
  created_at: '2026-08-12T10:00:00+00:00',
}

function trackedIn(state: string) {
  return {
    job_posting_id: 'job-1',
    tracker_state: state,
    bookmarked: true,
    bookmarked_at: '2026-08-10T09:00:00+00:00',
    updated_at: '2026-08-10T09:00:00+00:00',
  }
}

function fetchFor(trackerState: string, drafts: unknown[] = []) {
  return (url: string, init?: RequestInit) => {
    const path = String(url)
    const method = (init?.method ?? 'GET').toUpperCase()

    if (path.endsWith('/tracker') && method === 'GET') {
      return Promise.resolve(jsonResponse([trackedIn(trackerState)]))
    }
    if (path.endsWith('/job-postings')) {
      return Promise.resolve(jsonResponse([posting]))
    }
    if (path.endsWith('/outbound/deliveries') && method === 'GET') {
      return Promise.resolve(jsonResponse([]))
    }
    if (path.includes('/draft-artifacts?job_posting_id=')) {
      return Promise.resolve(jsonResponse(drafts))
    }
    return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/**
 * Every control is disabled while `busy`, and the button renders before the initial load
 * settles. Waiting for `aria-busy="false"` is what makes a `disabled` assertion mean the
 * tracker-state gate rather than the load that was still running.
 */
async function settled(container: HTMLElement) {
  const section = container.querySelector('section')
  await waitFor(() => {
    expect(section?.getAttribute('aria-busy')).toBe('false')
  })
}

describe('DraftsPage', () => {
  it('disables generation and says why when the tracker state is not draftable', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchFor('new')))

    const { container } = render(<DraftsPage />)

    const button = (await screen.findByRole('button', {
      name: 'Generate draft',
    })) as HTMLButtonElement
    await settled(container)

    expect(button.disabled).toBe(true)
    expect(screen.getByText(/Drafts need tracker state/)).toBeTruthy()
  })

  it('refuses approval for a superseded draft', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchFor('review', [{ ...draft, is_latest: false }])))

    const { container } = render(<DraftsPage />)

    const approve = (await screen.findByRole('button', {
      name: 'Approve outbound',
    })) as HTMLButtonElement
    await settled(container)

    expect(approve.disabled).toBe(true)
    expect(screen.getByText(/Superseded by a newer/)).toBeTruthy()
  })

  it('keeps the workspace error when the drafts request fails too', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        const path = String(url)
        if (path.endsWith('/outbound/deliveries')) {
          return Promise.resolve(
            jsonResponse(null, 500, { code: 'DELIVERIES_DOWN', message: 'no log' }),
          )
        }
        if (path.includes('/draft-artifacts?job_posting_id=')) {
          return Promise.resolve(
            jsonResponse(null, 500, { code: 'DRAFTS_DOWN', message: 'no drafts' }),
          )
        }
        return fetchFor('review')(url, init)
      }),
    )

    const { container } = render(<DraftsPage />)
    await settled(container)

    // The deliveries failure must survive; its section points at this banner.
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('DELIVERIES_DOWN')
    expect(screen.getByText('Could not load deliveries — see the error above.')).toBeTruthy()
    expect(screen.getByText('Could not load drafts — see the error above.')).toBeTruthy()
  })

  it('enables generation at review and posts the selected kind', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/draft-artifacts/generate') && method === 'POST') {
        return Promise.resolve(jsonResponse(draft, 200, null, { correlation_id: 'draft-cid' }))
      }
      return fetchFor('review')(url, init)
    })
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'page-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<DraftsPage />)

    const button = (await screen.findByRole('button', {
      name: 'Generate draft',
    })) as HTMLButtonElement
    await waitFor(() => {
      expect(button.disabled).toBe(false)
    })

    await user.selectOptions(screen.getByLabelText('Kind'), 'interview_prep')
    await user.click(button)

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([href, init]) => {
        return (
          String(href).endsWith('/draft-artifacts/generate') &&
          (init as RequestInit | undefined)?.method === 'POST'
        )
      })
      expect(call).toBeTruthy()
      const init = call?.[1] as RequestInit | undefined
      expect(JSON.parse(String(init?.body))).toEqual({
        job_posting_id: 'job-1',
        kind: 'interview_prep',
      })
      const headers = init?.headers as Record<string, string> | undefined
      expect(headers?.['X-Correlation-Id']).toBe('page-cid')
    })
  })

  it('offers Deliver only after approval and withdraws it once delivery consumes the approval', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/approve-outbound') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            id: 'approval-1',
            artifact_id: 'draft-1',
            correlation_id: 'cid-2',
            approved_at: '2026-08-12T10:05:00+00:00',
          }),
        )
      }
      if (path.endsWith('/outbound/deliver') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            id: 'delivery-1',
            artifact_id: 'draft-1',
            approval_id: 'approval-1',
            channel: 'manual_export',
            correlation_id: 'cid-3',
            content_snapshot: '[DRAFT] Hello there.',
            delivered_at: '2026-08-12T10:06:00+00:00',
          }),
        )
      }
      return fetchFor('review', [draft])(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<DraftsPage />)

    expect(await screen.findByText('[DRAFT] Hello there.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Deliver' })).toBeNull()

    await user.click(await screen.findByRole('button', { name: 'Approve outbound' }))

    const deliver = await screen.findByRole('button', { name: 'Deliver' })
    await user.click(deliver)

    // Delivering consumes the approval server-side, so the button must go away again.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Deliver' })).toBeNull()
    })
    expect(await screen.findByText(/recruiter_message for Backend Engineer/)).toBeTruthy()
    expect(screen.getByText('Delivery log (1)')).toBeTruthy()
  })

  it('clears the local approval when the API reports it is missing', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/approve-outbound') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            id: 'approval-1',
            artifact_id: 'draft-1',
            correlation_id: 'cid-2',
            approved_at: '2026-08-12T10:05:00+00:00',
          }),
        )
      }
      if (path.endsWith('/outbound/deliver') && method === 'POST') {
        return Promise.resolve(
          jsonResponse(null, 409, {
            code: 'OUTBOUND_APPROVAL_REQUIRED',
            message: 'Outbound delivery requires an approval.',
          }),
        )
      }
      return fetchFor('review', [draft])(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<DraftsPage />)

    await user.click(await screen.findByRole('button', { name: 'Approve outbound' }))
    await user.click(await screen.findByRole('button', { name: 'Deliver' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('OUTBOUND_APPROVAL_REQUIRED')
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Deliver' })).toBeNull()
    })
  })
})
