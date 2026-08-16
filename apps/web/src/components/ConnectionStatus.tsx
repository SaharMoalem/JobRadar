import { useEffect, useState } from 'react'

import { ApiClientError, apiRequest, isAbortError } from '../api/client.ts'

type ConnectionState =
  | { status: 'checking' }
  | { status: 'connected' }
  | { status: 'failed'; message: string }

export function ConnectionStatus() {
  const [state, setState] = useState<ConnectionState>({ status: 'checking' })

  useEffect(() => {
    const controller = new AbortController()

    void apiRequest<unknown>('/career-sources', { signal: controller.signal })
      .then(() => {
        if (controller.signal.aborted) {
          return
        }
        setState({ status: 'connected' })
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbortError(err)) {
          return
        }
        const message =
          err instanceof ApiClientError ? `${err.code}: ${err.message}` : 'API request failed'
        setState({ status: 'failed', message })
      })

    return () => controller.abort()
  }, [])

  if (state.status === 'checking') {
    return <p className="status status-checking">Checking API…</p>
  }

  if (state.status === 'connected') {
    return <p className="status status-ok">Connected</p>
  }

  return (
    <p className="status status-error" title={state.message}>
      API unavailable
      <span className="status-detail"> · {state.message}</span>
    </p>
  )
}
