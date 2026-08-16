import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SourcesPage } from './SourcesPage.tsx'

function jsonResponse(data: unknown, status = 200, error: unknown = null, meta: Record<string, unknown> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({ data, error, meta }),
  }
}

const sampleSource = {
  id: 'src-1',
  name: 'Acme Careers',
  base_url: 'https://acme.example.com/jobs',
  plugin_id: 'generic',
  status: 'disabled',
  compliance_status: 'pending',
  compliance_reason: null,
  robots_check_passed: null,
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('SourcesPage', () => {
  it('lists sources from GET /career-sources', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (String(url).endsWith('/career-sources')) {
          return Promise.resolve(jsonResponse([sampleSource]))
        }
        if (String(url).endsWith('/job-postings')) {
          return Promise.resolve(jsonResponse([]))
        }
        return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
      }),
    )

    render(<SourcesPage />)

    expect(await screen.findByText('Acme Careers')).toBeTruthy()
    expect(screen.getByText(/compliance pending/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Enable' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect((screen.getByRole('button', { name: 'Execute' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('creates a source then refreshes the list', async () => {
    const user = userEvent.setup()
    const created = { ...sampleSource, id: 'src-2', name: 'Globex' }
    let createdOnce = false
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.endsWith('/job-postings')) {
        return Promise.resolve(jsonResponse([]))
      }
      if (path.endsWith('/career-sources') && init?.method === 'POST') {
        createdOnce = true
        return Promise.resolve(jsonResponse(created))
      }
      if (path.endsWith('/career-sources')) {
        return Promise.resolve(jsonResponse(createdOnce ? [created] : []))
      }
      return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<SourcesPage />)
    expect(await screen.findByText('No career sources yet.')).toBeTruthy()

    await user.type(screen.getByLabelText('Name'), 'Globex')
    await user.type(screen.getByLabelText('Base URL'), 'https://globex.example.com/jobs')
    await user.click(screen.getByRole('button', { name: 'Create source' }))

    expect(await screen.findByText('Globex')).toBeTruthy()
    const createCall = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(createCall?.[0]).toBe('/api/career-sources')
    expect(JSON.parse(String((createCall?.[1] as RequestInit).body))).toEqual({
      name: 'Globex',
      base_url: 'https://globex.example.com/jobs',
      plugin_id: 'generic',
    })
  })

  it('keeps the sources list when job-postings fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (String(url).endsWith('/career-sources')) {
          return Promise.resolve(jsonResponse([sampleSource]))
        }
        if (String(url).endsWith('/job-postings')) {
          return Promise.resolve(
            jsonResponse(null, 500, { code: 'HTTP_ERROR', message: 'postings down' }),
          )
        }
        return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
      }),
    )

    render(<SourcesPage />)

    expect(await screen.findByText('Acme Careers')).toBeTruthy()
    expect((await screen.findByRole('alert')).textContent).toContain('HTTP_ERROR')
  })

  it('does not enable a pending source from the UI', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        const path = String(url)
        if (path.endsWith('/job-postings')) {
          return Promise.resolve(jsonResponse([]))
        }
        if (path.endsWith('/career-sources')) {
          return Promise.resolve(jsonResponse([sampleSource]))
        }
        return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
      }),
    )

    render(<SourcesPage />)
    await screen.findByText('Acme Careers')
    expect((screen.getByRole('button', { name: 'Enable' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('sends X-Correlation-Id when executing an approved enabled source', async () => {
    const user = userEvent.setup()
    const ready = {
      ...sampleSource,
      status: 'enabled',
      compliance_status: 'approved',
    }
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const path = String(url)
      if (path.endsWith('/job-postings')) {
        return Promise.resolve(jsonResponse([]))
      }
      if (path.endsWith('/execute') && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            {
              source_id: ready.id,
              plugin_id: 'generic',
              status: 'succeeded',
              error_code: null,
              error_message: null,
              duration_ms: 12,
            },
            200,
            null,
            { correlation_id: 'server-cid' },
          ),
        )
      }
      if (path.endsWith('/career-sources')) {
        return Promise.resolve(jsonResponse([ready]))
      }
      return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<SourcesPage />)
    await screen.findByText('Acme Careers')
    await user.click(screen.getByRole('button', { name: 'Execute' }))

    await waitFor(() => {
      const executeCall = fetchMock.mock.calls.find(([path]) => String(path).endsWith('/execute'))
      expect(executeCall).toBeTruthy()
      const headers = (executeCall?.[1] as RequestInit).headers as Record<string, string>
      expect(headers['X-Correlation-Id']?.trim()).toBeTruthy()
    })
    expect(await screen.findByText(/Correlation server-cid/)).toBeTruthy()
  })

  it('shows crawl outcome and error when execute returns both', async () => {
    const user = userEvent.setup()
    const ready = {
      ...sampleSource,
      status: 'enabled',
      compliance_status: 'approved',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        const path = String(url)
        if (path.endsWith('/job-postings')) {
          return Promise.resolve(jsonResponse([]))
        }
        if (path.endsWith('/execute') && init?.method === 'POST') {
          return Promise.resolve(
            jsonResponse(
              {
                source_id: ready.id,
                plugin_id: 'generic',
                status: 'failed',
                error_code: 'CRAWL_PLUGIN_FAILED',
                error_message: 'timeout',
                duration_ms: 9,
              },
              502,
              { code: 'CRAWL_PLUGIN_FAILED', message: 'timeout' },
              { correlation_id: 'failed-cid' },
            ),
          )
        }
        if (path.endsWith('/career-sources')) {
          return Promise.resolve(jsonResponse([ready]))
        }
        return Promise.resolve(jsonResponse(null, 404, { code: 'HTTP_ERROR', message: 'missing' }))
      }),
    )

    render(<SourcesPage />)
    await screen.findByText('Acme Careers')
    await user.click(screen.getByRole('button', { name: 'Execute' }))

    expect(await screen.findByText(/Correlation failed-cid/)).toBeTruthy()
    expect((await screen.findByRole('alert')).textContent).toContain('CRAWL_PLUGIN_FAILED')
  })
})
