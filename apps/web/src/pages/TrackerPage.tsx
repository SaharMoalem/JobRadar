import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { isAbortError, newCorrelationId } from '../api/client.ts'
import { listJobTitles } from '../api/opportunities.ts'
import {
  TRACKER_STATES,
  bookmarkOpportunity,
  listTracked,
  listTransitions,
  transitionTracked,
  unbookmarkOpportunity,
  type TrackedOpportunity,
  type TrackerState,
  type TrackerTransition,
} from '../api/tracker.ts'
import {
  type LoadState,
  combinedError,
  errorMessage,
  formatTimestamp,
  rejections,
} from '../lib/ui.ts'

type HistoryEntry = {
  state: LoadState
  items: TrackerTransition[]
}

export function TrackerPage() {
  const [tracked, setTracked] = useState<TrackedOpportunity[]>([])
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [history, setHistory] = useState<Record<string, HistoryEntry>>({})
  const [pendingState, setPendingState] = useState<Record<string, TrackerState>>({})
  const [bookmarkId, setBookmarkId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [trackedState, setTrackedState] = useState<LoadState>('loading')

  const busy = initializing || actionBusy

  const loadWorkspace = useCallback(async (signal?: AbortSignal): Promise<unknown[]> => {
    const [trackedResult, titleResult] = await Promise.allSettled([
      listTracked({ signal }),
      listJobTitles({ signal }),
    ])
    if (signal?.aborted) {
      return []
    }
    if (trackedResult.status === 'fulfilled') {
      setTracked(trackedResult.value.data ?? [])
      setTrackedState('ready')
    } else {
      setTrackedState('failed')
    }
    if (titleResult.status === 'fulfilled') {
      setTitles(titleResult.value)
    }
    return rejections([trackedResult, titleResult])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void loadWorkspace(controller.signal)
      .then((failures) => {
        if (controller.signal.aborted) {
          return
        }
        setError(combinedError(failures.filter((err) => !isAbortError(err))))
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbortError(err)) {
          return
        }
        setError(errorMessage(err))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setInitializing(false)
        }
      })
    return () => controller.abort()
  }, [loadWorkspace])

  /** `keepSummary` is for pure reads, which must not erase the last write's confirmation. */
  async function runAction(action: () => Promise<unknown>, options?: { keepSummary?: boolean }) {
    setActionBusy(true)
    setError(null)
    if (!options?.keepSummary) {
      setSummary(null)
    }
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
      if (!options?.keepSummary) {
        setSummary(null)
      }
    } finally {
      setActionBusy(false)
    }
  }

  /** Replace a row with what the server returned; never guess the new state locally. */
  function upsertTracked(row: TrackedOpportunity) {
    // A write proves the list is reachable, so a stale failure must not outlive it.
    setTrackedState('ready')
    setTracked((current) => {
      const index = current.findIndex((item) => item.job_posting_id === row.job_posting_id)
      if (index === -1) {
        return [...current, row].sort((a, b) => a.job_posting_id.localeCompare(b.job_posting_id))
      }
      const next = [...current]
      next[index] = row
      return next
    })
  }

  async function refreshHistory(jobPostingId: string) {
    setHistory((current) => ({
      ...current,
      [jobPostingId]: { state: 'loading', items: current[jobPostingId]?.items ?? [] },
    }))
    try {
      const result = await listTransitions(jobPostingId)
      setHistory((current) => ({
        ...current,
        [jobPostingId]: { state: 'ready', items: result.data ?? [] },
      }))
    } catch (err) {
      setHistory((current) => ({
        ...current,
        [jobPostingId]: { state: 'failed', items: current[jobPostingId]?.items ?? [] },
      }))
      throw err
    }
  }

  function onBookmark(event: FormEvent) {
    event.preventDefault()
    const jobPostingId = bookmarkId.trim()
    if (!jobPostingId) {
      return
    }
    void runAction(async () => {
      const result = await bookmarkOpportunity(jobPostingId, newCorrelationId())
      if (!result.data) {
        setError(`${jobPostingId} may have been bookmarked, but the API returned no record.`)
        return
      }
      upsertTracked(result.data)
      setBookmarkId('')
      setSummary(`Bookmarked ${titleFor(result.data.job_posting_id)}.`)
    })
  }

  function onToggleBookmark(row: TrackedOpportunity) {
    void runAction(async () => {
      const correlationId = newCorrelationId()
      const result = row.bookmarked
        ? await unbookmarkOpportunity(row.job_posting_id, correlationId)
        : await bookmarkOpportunity(row.job_posting_id, correlationId)
      if (!result.data) {
        setError(
          `The bookmark change on ${titleFor(row.job_posting_id)} may have been applied, but the API returned no record.`,
        )
        return
      }
      upsertTracked(result.data)
      setSummary(
        row.bookmarked
          ? `Removed the bookmark on ${titleFor(row.job_posting_id)}. It stays tracked in state ${result.data.tracker_state}.`
          : `Bookmarked ${titleFor(row.job_posting_id)}.`,
      )
    })
  }

  function onTransition(row: TrackedOpportunity) {
    const toState = pendingState[row.job_posting_id] ?? row.tracker_state
    void runAction(async () => {
      const result = await transitionTracked(
        row.job_posting_id,
        toState,
        `Moved to ${toState} from the tracker UI`,
        newCorrelationId(),
      )
      if (!result.data) {
        setError(
          `The transition on ${titleFor(row.job_posting_id)} may have been recorded, but the API returned no record.`,
        )
        return
      }
      upsertTracked(result.data)
      setSummary(`${titleFor(row.job_posting_id)} is now ${result.data.tracker_state}.`)
      if (history[row.job_posting_id]) {
        // The transition is already committed, so a failed refresh is a stale view, not a failure.
        try {
          await refreshHistory(row.job_posting_id)
        } catch (err) {
          setError(`The transition was recorded, but its history did not reload. ${errorMessage(err)}`)
        }
      }
    })
  }

  function onToggleHistory(jobPostingId: string) {
    if (history[jobPostingId]) {
      setHistory((current) => {
        const next = { ...current }
        delete next[jobPostingId]
        return next
      })
      return
    }
    void runAction(() => refreshHistory(jobPostingId), { keepSummary: true })
  }

  function titleFor(jobPostingId: string): string {
    return titles[jobPostingId] ?? jobPostingId
  }

  return (
    <section className="page sources-page tracker-page" aria-busy={busy}>
      <h1>Tracker</h1>
      <p>Bookmark opportunities and move them through the application tracker.</p>

      {error ? (
        <p className="banner-error" role="alert">
          {error}
        </p>
      ) : null}
      {summary ? (
        <p className="banner-ok" role="status">
          {summary}
        </p>
      ) : null}

      <form className="source-form" onSubmit={onBookmark}>
        <h2>Bookmark an opportunity</h2>
        <label>
          Job posting id
          <input
            name="job_posting_id"
            value={bookmarkId}
            onChange={(event) => setBookmarkId(event.target.value)}
          />
        </label>
        <p className="hint">
          Bookmark straight from a result row on the Opportunities page, or paste an id here. New
          bookmarks start in the <code>new</code> state.
        </p>
        <div className="form-actions">
          <button type="submit" disabled={busy || bookmarkId.trim() === ''}>
            Bookmark
          </button>
        </div>
      </form>

      <h2>Tracked opportunities{trackedState === 'ready' ? ` (${tracked.length})` : ''}</h2>
      {trackedState === 'loading' ? <p>Loading…</p> : null}
      {trackedState === 'failed' ? <p>Could not load the tracker — see the error above.</p> : null}
      {trackedState === 'ready' && tracked.length === 0 ? (
        <p>Nothing is tracked yet. Bookmark an opportunity to start.</p>
      ) : null}

      {trackedState === 'ready' && tracked.length > 0 ? (
        <ul className="posting-list">
          {tracked.map((row) => {
            const entry = history[row.job_posting_id]
            const selected = pendingState[row.job_posting_id] ?? row.tracker_state
            // The API rejects a move to the state a row already holds, so do not offer it.
            const unchanged = selected === row.tracker_state
            return (
              <li key={row.job_posting_id} className="tracker-row">
                <div>
                  <strong>{titleFor(row.job_posting_id)}</strong> ·{' '}
                  <span className="tracker-state">{`state: ${row.tracker_state}`}</span> ·{' '}
                  {row.bookmarked
                    ? row.bookmarked_at
                      ? `bookmarked ${formatTimestamp(row.bookmarked_at)}`
                      : 'bookmarked'
                    : 'not bookmarked'}{' '}
                  · updated {formatTimestamp(row.updated_at)}
                </div>
                <div className="row-actions">
                  <select
                    aria-label={`Next state for ${titleFor(row.job_posting_id)}`}
                    value={selected}
                    onChange={(event) =>
                      setPendingState((current) => ({
                        ...current,
                        [row.job_posting_id]: event.target.value as TrackerState,
                      }))
                    }
                  >
                    {TRACKER_STATES.map((state) => (
                      <option key={state} value={state}>
                        {state}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={busy || unchanged}
                    onClick={() => onTransition(row)}
                  >
                    Apply state
                  </button>
                  <button type="button" disabled={busy} onClick={() => onToggleBookmark(row)}>
                    {row.bookmarked ? 'Remove bookmark' : 'Bookmark'}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onToggleHistory(row.job_posting_id)}
                  >
                    {entry ? 'Hide history' : 'Show history'}
                  </button>
                </div>
                {unchanged ? (
                  <p className="hint">Pick a different state to move this opportunity.</p>
                ) : null}
                {entry ? (
                  <div className="tracker-history">
                    {entry.state === 'loading' ? <p>Loading…</p> : null}
                    {entry.state === 'failed' ? (
                      <p>Could not load history — see the error above.</p>
                    ) : null}
                    {entry.state === 'ready' && entry.items.length === 0 ? (
                      <p>No transitions recorded.</p>
                    ) : null}
                    {entry.state === 'ready' && entry.items.length > 0 ? (
                      <ol>
                        {entry.items.map((item) => (
                          <li key={item.correlation_id}>
                            {item.from_state ?? 'initial'} → {item.to_state} · {item.reason} ·{' '}
                            {formatTimestamp(item.transitioned_at)}
                          </li>
                        ))}
                      </ol>
                    ) : null}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}
