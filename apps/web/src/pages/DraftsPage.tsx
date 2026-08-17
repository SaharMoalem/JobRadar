import { useCallback, useEffect, useState } from 'react'

import { ApiClientError, isAbortError, newCorrelationId } from '../api/client.ts'
import {
  DRAFTABLE_TRACKER_STATES,
  DRAFT_KINDS,
  approveOutbound,
  deliverOutbound,
  generateDraft,
  listDeliveries,
  listDrafts,
  type DraftArtifact,
  type DraftKind,
  type OutboundDelivery,
} from '../api/drafts.ts'
import { listJobTitles } from '../api/opportunities.ts'
import { listTracked, type TrackedOpportunity } from '../api/tracker.ts'
import {
  type LoadState,
  combinedError,
  errorMessage,
  formatTimestamp,
  rejections,
} from '../lib/ui.ts'

const DELIVERY_CHANNEL = 'manual_export'

export function DraftsPage() {
  const [tracked, setTracked] = useState<TrackedOpportunity[]>([])
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [deliveries, setDeliveries] = useState<OutboundDelivery[]>([])
  const [drafts, setDrafts] = useState<DraftArtifact[]>([])
  const [selectedPosting, setSelectedPosting] = useState('')
  const [kind, setKind] = useState<DraftKind>(DRAFT_KINDS[0])
  // The API exposes no way to read approvals back, so this cannot survive a reload.
  const [approvedIds, setApprovedIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [trackedState, setTrackedState] = useState<LoadState>('loading')
  const [draftsState, setDraftsState] = useState<LoadState>('loading')
  const [deliveriesState, setDeliveriesState] = useState<LoadState>('loading')

  const busy = initializing || actionBusy
  const selected = tracked.find((row) => row.job_posting_id === selectedPosting)
  const canGenerate =
    selected !== undefined && DRAFTABLE_TRACKER_STATES.includes(selected.tracker_state)

  const loadDrafts = useCallback(async (jobPostingId: string, signal?: AbortSignal) => {
    if (!jobPostingId) {
      setDrafts([])
      setDraftsState('ready')
      return
    }
    setDraftsState('loading')
    try {
      const result = await listDrafts(jobPostingId, { signal })
      if (signal?.aborted) {
        return
      }
      setDrafts(result.data ?? [])
      setDraftsState('ready')
    } catch (err) {
      if (signal?.aborted || isAbortError(err)) {
        return
      }
      setDraftsState('failed')
      throw err
    }
  }, [])

  const loadWorkspace = useCallback(async (signal?: AbortSignal): Promise<unknown[]> => {
    const [trackedResult, titleResult, deliveryResult] = await Promise.allSettled([
      listTracked({ signal }),
      listJobTitles({ signal }),
      listDeliveries({ signal }),
    ])
    if (signal?.aborted) {
      return []
    }
    if (trackedResult.status === 'fulfilled') {
      const rows = trackedResult.value.data ?? []
      setTracked(rows)
      setTrackedState('ready')
      const draftable = rows.find((row) => DRAFTABLE_TRACKER_STATES.includes(row.tracker_state))
      const first = draftable ?? rows[0]
      if (first) {
        setSelectedPosting(first.job_posting_id)
      }
    } else {
      // No drafts request is issued without a posting, so draftsState stays unclaimed.
      setTrackedState('failed')
    }
    if (titleResult.status === 'fulfilled') {
      setTitles(titleResult.value)
    }
    if (deliveryResult.status === 'fulfilled') {
      setDeliveries(deliveryResult.value.data ?? [])
      setDeliveriesState('ready')
    } else {
      setDeliveriesState('failed')
    }
    return rejections([trackedResult, titleResult, deliveryResult])
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

  useEffect(() => {
    if (!selectedPosting) {
      return
    }
    const controller = new AbortController()
    void loadDrafts(selectedPosting, controller.signal).catch((err: unknown) => {
      if (controller.signal.aborted || isAbortError(err)) {
        return
      }
      // Mount failures are already summarized in the banner; do not discard them.
      setError((current) => current ?? errorMessage(err))
    })
    return () => controller.abort()
  }, [loadDrafts, selectedPosting])

  async function runAction(action: () => Promise<unknown>) {
    setActionBusy(true)
    setError(null)
    setSummary(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
      setSummary(null)
    } finally {
      setActionBusy(false)
    }
  }

  function onGenerate() {
    // Pinned so a reload triggered here cannot paint under a different opportunity.
    const jobPostingId = selectedPosting
    const requestedKind = kind
    void runAction(async () => {
      const result = await generateDraft(jobPostingId, requestedKind, newCorrelationId())
      if (!result.data) {
        setError(`The ${requestedKind} draft may have been generated, but the API returned no record.`)
        return
      }
      setSummary(
        `Generated a ${result.data.kind} draft. Earlier drafts of this kind are no longer the latest.`,
      )
      // The draft exists either way, so a failed reload is a stale list, not a failed generate.
      const controller = new AbortController()
      try {
        await loadDrafts(jobPostingId, controller.signal)
      } catch (err) {
        if (isAbortError(err)) {
          return
        }
        setError(`The draft was generated, but the list did not reload. ${errorMessage(err)}`)
      }
    })
  }

  function onApprove(artifact: DraftArtifact) {
    void runAction(async () => {
      const result = await approveOutbound(artifact.id, newCorrelationId())
      if (!result.data) {
        setError('The approval may have been recorded, but the API returned no record.')
        return
      }
      setApprovedIds((current) =>
        current.includes(artifact.id) ? current : [...current, artifact.id],
      )
      setSummary(
        'Outbound delivery approved for this draft. The approval is not stored by the API, so it is lost on reload and consumed by the first delivery.',
      )
    })
  }

  function onDeliver(artifact: DraftArtifact) {
    void runAction(async () => {
      try {
        const result = await deliverOutbound(artifact.id, DELIVERY_CHANNEL, newCorrelationId())
        setApprovedIds((current) => current.filter((id) => id !== artifact.id))
        const delivery = result.data
        if (!delivery) {
          setError('The delivery may have been recorded, but the API returned no record.')
          return
        }
        // A write proves the log is reachable, so a stale failure must not outlive it.
        setDeliveries((current) => [...current, delivery])
        setDeliveriesState('ready')
        setSummary(
          `Recorded a ${DELIVERY_CHANNEL} delivery locally. Nothing was sent externally; approve again to record another.`,
        )
      } catch (err) {
        // The API is the authority here — any outbound rejection means our flag was wrong.
        if (
          err instanceof ApiClientError &&
          (err.code === 'OUTBOUND_APPROVAL_REQUIRED' || err.code.startsWith('OUTBOUND_ARTIFACT_'))
        ) {
          setApprovedIds((current) => current.filter((id) => id !== artifact.id))
        }
        throw err
      }
    })
  }

  function titleFor(jobPostingId: string): string {
    return titles[jobPostingId] ?? jobPostingId
  }

  return (
    <section className="page sources-page drafts-page" aria-busy={busy}>
      <h1>Drafts</h1>
      <p>
        Generate draft artifacts and record outbound delivery. Every draft stays a draft until you
        approve it, and delivery is recorded locally — nothing is ever sent for you.
      </p>
      <p className="hint">
        Approvals live in this browser tab only: the API stores no approval you can read back, so
        reloading clears them and each delivery consumes the one that allowed it.
      </p>

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

      <div className="source-form">
        <h2>Generate a draft</h2>
        {trackedState === 'loading' ? <p>Loading…</p> : null}
        {trackedState === 'failed' ? (
          <p>Could not load tracked opportunities — see the error above.</p>
        ) : null}
        {trackedState === 'ready' && tracked.length === 0 ? (
          <p>Nothing is tracked yet. Bookmark an opportunity on the Tracker page first.</p>
        ) : null}
        {trackedState === 'ready' && tracked.length > 0 ? (
          <>
            <label>
              Opportunity
              <select
                name="job_posting_id"
                value={selectedPosting}
                disabled={busy}
                onChange={(event) => setSelectedPosting(event.target.value)}
              >
                {tracked.map((row) => (
                  <option key={row.job_posting_id} value={row.job_posting_id}>
                    {titleFor(row.job_posting_id)} ({row.tracker_state})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Kind
              <select
                name="kind"
                value={kind}
                disabled={busy}
                onChange={(event) => setKind(event.target.value as DraftKind)}
              >
                {DRAFT_KINDS.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            {canGenerate ? null : (
              <p className="hint">
                Drafts need tracker state <code>review</code> or <code>apply</code>. This
                opportunity is <code>{selected?.tracker_state}</code> — move it on the Tracker page
                first.
              </p>
            )}
            <div className="form-actions">
              <button type="button" disabled={busy || !canGenerate} onClick={onGenerate}>
                Generate draft
              </button>
            </div>
          </>
        ) : null}
      </div>

      <h2>
        {selectedPosting ? `Drafts for ${titleFor(selectedPosting)}` : 'Drafts'}
        {selectedPosting && draftsState === 'ready' ? ` (${drafts.length})` : ''}
      </h2>
      {!selectedPosting ? <p>Select a tracked opportunity to see its drafts.</p> : null}
      {selectedPosting && draftsState === 'loading' ? <p>Loading…</p> : null}
      {selectedPosting && draftsState === 'failed' ? (
        <p>Could not load drafts — see the error above.</p>
      ) : null}
      {selectedPosting && draftsState === 'ready' && drafts.length === 0 ? (
        <p>No drafts generated for this opportunity yet.</p>
      ) : null}
      {selectedPosting && draftsState === 'ready' && drafts.length > 0 ? (
        <ul className="posting-list">
          {drafts.map((artifact) => {
            const approved = approvedIds.includes(artifact.id)
            return (
              <li key={artifact.id} className="draft-row">
                <div>
                  <strong>{artifact.kind}</strong> · {artifact.is_latest ? 'latest' : 'superseded'}{' '}
                  · {formatTimestamp(artifact.created_at)} · source {artifact.source_reference}
                </div>
                <pre className="draft-content">{artifact.content}</pre>
                <div className="row-actions">
                  {approved ? (
                    <button type="button" disabled={busy} onClick={() => onDeliver(artifact)}>
                      Deliver
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={busy || !artifact.is_latest}
                      onClick={() => onApprove(artifact)}
                    >
                      Approve outbound
                    </button>
                  )}
                  {approved ? (
                    <span className="hint">Approved in this tab — delivery consumes it.</span>
                  ) : artifact.is_latest ? (
                    <span className="hint">Approve to enable delivery.</span>
                  ) : (
                    <span className="hint">
                      Superseded by a newer {artifact.kind} draft — only the latest can be
                      approved.
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      ) : null}

      <h2>Delivery log{deliveriesState === 'ready' ? ` (${deliveries.length})` : ''}</h2>
      {deliveriesState === 'loading' ? <p>Loading…</p> : null}
      {deliveriesState === 'failed' ? (
        <p>Could not load deliveries — see the error above.</p>
      ) : null}
      {deliveriesState === 'ready' && deliveries.length === 0 ? (
        <p>No deliveries recorded.</p>
      ) : null}
      {deliveriesState === 'ready' && deliveries.length > 0 ? (
        <ul className="posting-list">
          {deliveries.map((delivery) => {
            const artifact = drafts.find((item) => item.id === delivery.artifact_id)
            return (
              <li key={delivery.id} className="draft-row">
                <div>
                  {delivery.channel} ·{' '}
                  {artifact
                    ? `${artifact.kind} for ${titleFor(artifact.job_posting_id)}`
                    : `artifact ${delivery.artifact_id}`}{' '}
                  · {formatTimestamp(delivery.delivered_at)} · correlation{' '}
                  <code>{delivery.correlation_id}</code>
                </div>
                <details>
                  <summary>What was recorded as sent</summary>
                  <pre className="draft-content">{delivery.content_snapshot}</pre>
                </details>
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}
