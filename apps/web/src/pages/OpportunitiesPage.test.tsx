import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { OpportunitiesPage } from './OpportunitiesPage.tsx'

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

const sampleItem = {
  job_posting_id: 'job-1',
  title: 'Backend Engineer',
  company: 'Acme',
  location: 'Tel Aviv',
  url: 'https://acme.example.com/jobs/1',
  posted_at: '2026-07-01T08:00:00+00:00',
  lifecycle_state: 'active',
  role_family: 'engineering',
  work_model: 'hybrid',
  match_score: 72,
}

function defaultFetch(url: string, init?: RequestInit) {
  const path = String(url)
  const method = (init?.method ?? 'GET').toUpperCase()

  if (path.includes('/opportunity-filter-state') && method === 'GET') {
    return Promise.resolve(jsonResponse(null))
  }
  if (path.includes('/opportunities/search') && method === 'POST') {
    return Promise.resolve(
      jsonResponse({ items: [], total_count: 0, empty: true }, 200, null, {
        session_id: 'web-opportunities',
        applied_filter: {},
      }),
    )
  }
  if (path.endsWith('/user-profile') && method === 'GET') {
    return Promise.resolve(
      jsonResponse(null, 404, {
        code: 'PROFILE_NOT_CONFIGURED',
        message: 'User profile is not configured.',
      }),
    )
  }
  if (path.endsWith('/job-postings')) {
    return Promise.resolve(jsonResponse([]))
  }
  if (path.endsWith('/recommendations/actionable')) {
    return Promise.resolve(jsonResponse([]))
  }
  if (path.endsWith('/recommendations/top')) {
    return Promise.resolve(jsonResponse([]))
  }
  if (path.endsWith('/recommendations/explainable')) {
    return Promise.resolve(jsonResponse([]))
  }
  return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
}

function bodyOf(call: unknown[] | undefined): unknown {
  const init = call?.[1] as RequestInit | undefined
  return JSON.parse(String(init?.body ?? 'null'))
}

function findCall(calls: unknown[][], path: string, method = 'POST'): unknown[] | undefined {
  return calls.find((call) => {
    const init = call[1] as RequestInit | undefined
    return String(call[0]).endsWith(path) && (init?.method ?? 'GET').toUpperCase() === method
  })
}

async function waitForReady() {
  await waitFor(() => {
    const search = screen.getByRole('button', { name: 'Search' }) as HTMLButtonElement
    expect(search.disabled).toBe(false)
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('OpportunitiesPage', () => {
  it('restores filter state then searches with that session', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunity-filter-state') && method === 'GET') {
        return Promise.resolve(
          jsonResponse({
            session_id: 'web-opportunities',
            criteria: { location: 'Tel Aviv' },
            updated_at: '2026-08-16T00:00:00+00:00',
          }),
        )
      }
      if (path.includes('/opportunities/search') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({ items: [sampleItem], total_count: 1, empty: false }, 200, null, {
            session_id: 'web-opportunities',
            applied_filter: { location: 'Tel Aviv' },
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)

    expect(await screen.findByDisplayValue('Tel Aviv')).toBeTruthy()
    expect(await screen.findByText('Backend Engineer')).toBeTruthy()

    await waitFor(() => {
      const searchCall = findCall(fetchMock.mock.calls, '/opportunities/search')
      expect(searchCall).toBeTruthy()
      expect(bodyOf(searchCall)).toEqual({
        location: 'Tel Aviv',
        session_id: 'web-opportunities',
      })
    })
  })

  it('shows an empty search sentence without an error alert', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch))

    render(<OpportunitiesPage />)

    expect(await screen.findByText('No opportunities match these filters.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('does not claim an empty result before the first search resolves', async () => {
    let releaseSearch = () => {}
    const searchGate = new Promise<void>((resolve) => {
      releaseSearch = resolve
    })
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        await searchGate
        return jsonResponse({ items: [sampleItem], total_count: 1, empty: false })
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)

    expect(await screen.findAllByText('Loading…')).toBeTruthy()
    expect(screen.queryByText('No opportunities match these filters.')).toBeNull()

    releaseSearch()
    expect(await screen.findByText('Backend Engineer')).toBeTruthy()
    expect(screen.queryByText('No opportunities match these filters.')).toBeNull()
  })

  it('does not claim an empty result when the search fails', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        return Promise.resolve(
          jsonResponse(null, 500, { code: 'SEARCH_FAILED', message: 'boom' }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('SEARCH_FAILED')
    expect(screen.queryByText('No opportunities match these filters.')).toBeNull()
  })

  it('reports the filter-state failure even when recommendations also fail', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunity-filter-state') && method === 'GET') {
        return Promise.resolve(
          jsonResponse(null, 500, { code: 'FILTER_STATE_FAILED', message: 'boom' }),
        )
      }
      if (path.endsWith('/recommendations/actionable')) {
        return Promise.resolve(jsonResponse(null, 500, { code: 'RECS_FAILED', message: 'boom' }))
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('FILTER_STATE_FAILED')
    expect(alert.textContent).toContain('1 more request failed')
  })

  it('shows SEARCH_SCORE_RANGE_INVALID when min score is above max', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        const body = JSON.parse(String(init?.body ?? '{}')) as {
          min_score?: number
          max_score?: number
        }
        if (body.min_score === 90 && body.max_score === 10) {
          return Promise.resolve(
            jsonResponse(null, 400, {
              code: 'SEARCH_SCORE_RANGE_INVALID',
              message: 'min_score cannot exceed max_score.',
            }),
          )
        }
        return Promise.resolve(jsonResponse({ items: [], total_count: 0, empty: true }))
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)
    await screen.findByText('No opportunities match these filters.')
    await waitForReady()

    await user.type(screen.getByLabelText('Min score'), '90')
    await user.type(screen.getByLabelText('Max score'), '10')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('SEARCH_SCORE_RANGE_INVALID')
  })

  it('saves the selected lifecycle states through PUT filter-state', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunity-filter-state') && method === 'PUT') {
        return Promise.resolve(
          jsonResponse({
            session_id: 'web-opportunities',
            criteria: {},
            updated_at: '2026-08-16T00:00:00+00:00',
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)
    await waitForReady()

    await user.click(screen.getByLabelText('archived'))
    await user.click(screen.getByRole('button', { name: 'Save filters' }))

    await waitFor(() => {
      const putCall = findCall(fetchMock.mock.calls, '/opportunity-filter-state', 'PUT')
      expect(putCall).toBeTruthy()
      expect(bodyOf(putCall)).toEqual({
        session_id: 'web-opportunities',
        lifecycle_states: ['archived'],
      })
    })
    expect(await screen.findByRole('status')).toBeTruthy()
  })

  it('maps comma-separated profile fields onto the PUT payload', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.endsWith('/user-profile') && method === 'PUT') {
        return Promise.resolve(jsonResponse(JSON.parse(String(init?.body ?? '{}'))))
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)
    await waitForReady()

    await user.type(screen.getByLabelText('Skills'), 'python , fastapi ,')
    await user.type(screen.getByLabelText('Target seniority'), 'senior')
    await user.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => {
      const putCall = findCall(fetchMock.mock.calls, '/user-profile', 'PUT')
      expect(putCall).toBeTruthy()
      expect(bodyOf(putCall)).toEqual({
        skills: ['python', 'fastapi'],
        preferred_locations: [],
        preferred_languages: [],
        target_seniority: 'senior',
      })
    })
  })

  it('sends X-Correlation-Id when running scoring and renders rec lists', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({ items: [sampleItem], total_count: 1, empty: false }),
        )
      }
      if (path.endsWith('/match-scores/run') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({ scored_count: 1, skipped_count: 0, scores: [] }, 200, null, {
            correlation_id: 'score-cid',
          }),
        )
      }
      if (path.endsWith('/recommendations/actionable')) {
        return Promise.resolve(
          jsonResponse([
            {
              job_posting_id: 'job-1',
              match_score: 72,
              actionable: true,
              gate_trace: [{ gate: 'freshness', passed: true, message: 'Posted 3 days ago.' }],
            },
          ]),
        )
      }
      if (path.endsWith('/recommendations/top')) {
        return Promise.resolve(
          jsonResponse([
            {
              job_posting_id: 'job-1',
              match_score: 72,
              rank: 1,
              suppressed: false,
            },
          ]),
        )
      }
      if (path.endsWith('/recommendations/explainable')) {
        return Promise.resolve(
          jsonResponse([
            {
              job_posting_id: 'job-1',
              match_score: 72,
              promoted: true,
              note: {
                match_rationale: 'Strong skill overlap.',
                missing_skills: ['k8s'],
                interview_probability_pct: 40,
                effort_estimate: 'medium',
              },
            },
          ]),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)
    expect((await screen.findAllByText('Backend Engineer')).length).toBeGreaterThan(0)
    expect(await screen.findByText(/Strong skill overlap/)).toBeTruthy()
    expect(await screen.findByText(/freshness: passed/)).toBeTruthy()
    await waitForReady()

    const searchesBefore = fetchMock.mock.calls.filter(([href]) =>
      String(href).endsWith('/opportunities/search'),
    ).length

    await user.click(screen.getByRole('button', { name: 'Run scoring' }))

    await waitFor(() => {
      const runCall = findCall(fetchMock.mock.calls, '/match-scores/run')
      expect(runCall).toBeTruthy()
      const headers = (runCall?.[1] as RequestInit | undefined)?.headers as
        | Record<string, string>
        | undefined
      expect(headers?.['X-Correlation-Id']?.trim()).toBeTruthy()
    })
    expect(await screen.findByText(/Correlation score-cid/)).toBeTruthy()

    // AC 4: the run must refresh the search and the recommendation lists.
    await waitFor(() => {
      const searchesAfter = fetchMock.mock.calls.filter(([href]) =>
        String(href).endsWith('/opportunities/search'),
      ).length
      expect(searchesAfter).toBeGreaterThan(searchesBefore)
    })
  })

  it('resolves recommendation titles that are absent from the filtered results', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        return Promise.resolve(jsonResponse({ items: [], total_count: 0, empty: true }))
      }
      if (path.endsWith('/job-postings')) {
        return Promise.resolve(
          jsonResponse([
            {
              id: 'job-9',
              title: 'Platform Engineer',
              company: 'Acme',
              location: 'Remote',
              url: 'https://acme.example.com/jobs/9',
              career_source_id: 'src-1',
              lifecycle_state: 'active',
            },
          ]),
        )
      }
      if (path.endsWith('/recommendations/top')) {
        return Promise.resolve(
          jsonResponse([{ job_posting_id: 'job-9', match_score: 80, rank: 1, suppressed: false }]),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)

    expect(await screen.findByText('Platform Engineer')).toBeTruthy()
    expect(screen.queryByText('job-9')).toBeNull()
  })

  it('bookmarks a result row through POST /tracker/bookmarks', async () => {
    const user = userEvent.setup()
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(
      'bookmark-cid' as ReturnType<typeof crypto.randomUUID>,
    )
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path.includes('/opportunities/search') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({ items: [sampleItem], total_count: 1, empty: false }),
        )
      }
      if (path.endsWith('/tracker/bookmarks') && method === 'POST') {
        return Promise.resolve(
          jsonResponse({
            job_posting_id: 'job-1',
            tracker_state: 'new',
            bookmarked: true,
            bookmarked_at: '2026-08-16T12:00:00+00:00',
            updated_at: '2026-08-16T12:00:00+00:00',
          }),
        )
      }
      return defaultFetch(url, init)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<OpportunitiesPage />)
    expect(await screen.findByText('Backend Engineer')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Bookmark' }))

    await waitFor(() => {
      const call = findCall(fetchMock.mock.calls, '/tracker/bookmarks')
      expect(call).toBeTruthy()
      expect(bodyOf(call)).toEqual({ job_posting_id: 'job-1' })
      const headers = (call?.[1] as RequestInit | undefined)?.headers as
        | Record<string, string>
        | undefined
      expect(headers?.['X-Correlation-Id']).toBe('bookmark-cid')
    })
    expect(await screen.findByRole('status')).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: 'Bookmarked' }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})
