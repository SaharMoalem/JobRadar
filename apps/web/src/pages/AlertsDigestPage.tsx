import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { isAbortError, newCorrelationId } from '../api/client.ts'
import {
  getAlertConfig,
  listImmediateAlerts,
  runImmediateAlerts,
  saveAlertConfig,
  type ImmediateAlert,
} from '../api/alerts.ts'
import {
  getDigestConfig,
  listMorningDigests,
  runMorningDigest,
  saveDigestConfig,
  type DigestJobItem,
  type MorningDigest,
} from '../api/digests.ts'
import {
  type LoadState,
  combinedError,
  errorMessage,
  formatTimestamp,
  rejections,
} from '../lib/ui.ts'

function optionalInt(raw: string): number | undefined {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return undefined
  }
  const parsed = Number(trimmed)
  return Number.isInteger(parsed) && Number.isFinite(parsed) ? parsed : undefined
}

function renderItems(title: string, items: DigestJobItem[]) {
  if (items.length === 0) {
    return null
  }
  return (
    <div>
      <h3>{title}</h3>
      <ul className="posting-list">
        {items.map((item, index) => (
          <li key={`${item.job_posting_id}-${item.rank ?? item.lifecycle_state}-${index}`}>
            {item.role_summary} · score {item.match_score}
            {item.rank != null ? ` · rank ${item.rank}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function AlertsDigestPage() {
  const [alertThreshold, setAlertThreshold] = useState('90')
  const [digestThreshold, setDigestThreshold] = useState('80')
  const [digestWindow, setDigestWindow] = useState('24')
  const [topN, setTopN] = useState('5')
  const [alerts, setAlerts] = useState<ImmediateAlert[]>([])
  const [digests, setDigests] = useState<MorningDigest[]>([])
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [alertConfigState, setAlertConfigState] = useState<LoadState>('loading')
  const [digestConfigState, setDigestConfigState] = useState<LoadState>('loading')
  const [alertsState, setAlertsState] = useState<LoadState>('loading')
  const [digestsState, setDigestsState] = useState<LoadState>('loading')

  const busy = initializing || actionBusy

  const loadWorkspace = useCallback(async (signal?: AbortSignal): Promise<unknown[]> => {
    const [alertConfig, digestConfig, alertList, digestList] = await Promise.allSettled([
      getAlertConfig({ signal }),
      getDigestConfig({ signal }),
      listImmediateAlerts({ signal }),
      listMorningDigests({ signal }),
    ])
    if (signal?.aborted) {
      return []
    }
    if (alertConfig.status === 'fulfilled' && alertConfig.value.data) {
      setAlertThreshold(String(alertConfig.value.data.alert_threshold))
      setAlertConfigState('ready')
    } else {
      setAlertConfigState('failed')
    }
    if (digestConfig.status === 'fulfilled' && digestConfig.value.data) {
      const config = digestConfig.value.data
      setDigestThreshold(String(config.digest_threshold))
      setDigestWindow(String(config.digest_window_hours))
      setTopN(String(config.top_n))
      setDigestConfigState('ready')
    } else {
      setDigestConfigState('failed')
    }
    if (alertList.status === 'fulfilled') {
      setAlerts(alertList.value.data ?? [])
      setAlertsState('ready')
    } else {
      setAlertsState('failed')
    }
    if (digestList.status === 'fulfilled') {
      setDigests(digestList.value.data ?? [])
      setDigestsState('ready')
    } else {
      setDigestsState('failed')
    }
    return rejections([alertConfig, digestConfig, alertList, digestList])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void loadWorkspace(controller.signal)
      .then((failures) => {
        if (!controller.signal.aborted) {
          setError(combinedError(failures.filter((err) => !isAbortError(err))))
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted && !isAbortError(err)) {
          setError(errorMessage(err))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setInitializing(false)
        }
      })
    return () => controller.abort()
  }, [loadWorkspace])

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

  function onSaveAlert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!event.currentTarget.reportValidity()) {
      return
    }
    const threshold = optionalInt(alertThreshold)
    if (threshold === undefined) {
      setSummary(null)
      setError('Alert threshold must be an integer 0–100.')
      return
    }
    void runAction(async () => {
      const result = await saveAlertConfig(threshold, newCorrelationId())
      if (!result.data) {
        setError('The alert config may have been saved, but the API returned no record.')
        return
      }
      setAlertThreshold(String(result.data.alert_threshold))
      setAlertConfigState('ready')
      setSummary(`Alert threshold saved as ${result.data.alert_threshold}.`)
    })
  }

  function onSaveDigest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!event.currentTarget.reportValidity()) {
      return
    }
    const digest_threshold = optionalInt(digestThreshold)
    const digest_window_hours = optionalInt(digestWindow)
    const top_n = optionalInt(topN)
    if (
      digest_threshold === undefined ||
      digest_window_hours === undefined ||
      top_n === undefined
    ) {
      setSummary(null)
      setError('Digest fields must be integers in range (threshold 0–100, window 1–8760, top N 1–10).')
      return
    }
    void runAction(async () => {
      const result = await saveDigestConfig(
        { digest_threshold, digest_window_hours, top_n },
        newCorrelationId(),
      )
      if (!result.data) {
        setError('The digest config may have been saved, but the API returned no record.')
        return
      }
      setDigestThreshold(String(result.data.digest_threshold))
      setDigestWindow(String(result.data.digest_window_hours))
      setTopN(String(result.data.top_n))
      setDigestConfigState('ready')
      setSummary(
        `Digest saved: threshold ${result.data.digest_threshold}, window ${result.data.digest_window_hours}h, top ${result.data.top_n}.`,
      )
    })
  }

  function onRunAlerts() {
    void runAction(async () => {
      const result = await runImmediateAlerts(newCorrelationId())
      if (!result.data) {
        setError('The alert run may have completed, but the API returned no record.')
        return
      }
      const batch = result.data
      setSummary(
        `Alert run triggered=${batch.triggered_count} skipped_threshold=${batch.skipped_below_threshold_count} skipped_duplicate=${batch.skipped_duplicate_count} skipped_missing=${batch.skipped_missing_posting_count}. run_context ${batch.run_context}.`,
      )
      try {
        const listed = await listImmediateAlerts()
        setAlerts(listed.data ?? [])
        setAlertsState('ready')
      } catch (err) {
        setAlertsState('failed')
        setError(`The run completed, but the alert list did not reload. ${errorMessage(err)}`)
      }
    })
  }

  function onRunDigest() {
    void runAction(async () => {
      const result = await runMorningDigest(newCorrelationId())
      if (!result.data) {
        setError('The digest run may have completed, but the API returned no record.')
        return
      }
      const digest = result.data
      setSummary(
        digest.is_noop
          ? `No-op digest for ${digest.digest_date} (run_context ${digest.run_context}). Nothing met the window and threshold.`
          : `Digest ${digest.digest_date}: new=${digest.new_items.length} updated=${digest.updated_items.length} expired=${digest.expired_items.length} top=${digest.top_recommendations.length}. run_context ${digest.run_context}.`,
      )
      try {
        const listed = await listMorningDigests()
        setDigests(listed.data ?? [])
        setDigestsState('ready')
      } catch (err) {
        setDigestsState('failed')
        setError(`The run completed, but the digest list did not reload. ${errorMessage(err)}`)
      }
    })
  }

  return (
    <section className="page sources-page alerts-page" aria-busy={busy}>
      <h1>Alerts / Digest</h1>
      <p>
        Configure thresholds, trigger runs, and read the results. Copy a <code>run_context</code>{' '}
        from a run summary into Notifications to deliver it.
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

      <form className="source-form" onSubmit={onSaveAlert}>
        <h2>Immediate alerts</h2>
        {alertConfigState === 'loading' ? <p>Loading…</p> : null}
        {alertConfigState === 'failed' ? (
          <p>Could not load alert config — see the error above.</p>
        ) : null}
        {alertConfigState === 'ready' ? (
          <>
            <label>
              Alert threshold
              <input
                name="alert_threshold"
                type="number"
                min="0"
                max="100"
                step="1"
                required
                value={alertThreshold}
                onChange={(event) => setAlertThreshold(event.target.value)}
              />
            </label>
            <p className="hint">Integer 0–100. Only match scores at or above this value alert.</p>
          </>
        ) : null}
        {alertConfigState !== 'loading' ? (
          <div className="form-actions">
            {alertConfigState === 'ready' ? (
              <button type="submit" disabled={busy}>
                Save alert config
              </button>
            ) : null}
            <button type="button" disabled={busy} onClick={onRunAlerts}>
              Run immediate alerts
            </button>
          </div>
        ) : null}
      </form>

      <h2>Triggered alerts{alertsState === 'ready' ? ` (${alerts.length})` : ''}</h2>
      {alertsState === 'loading' ? <p>Loading…</p> : null}
      {alertsState === 'failed' ? <p>Could not load alerts — see the error above.</p> : null}
      {alertsState === 'ready' && alerts.length === 0 ? (
        <p>No immediate alerts yet. Run scoring, then run alerts.</p>
      ) : null}
      {alertsState === 'ready' && alerts.length > 0 ? (
        <ul className="posting-list">
          {alerts.map((item) => (
            <li key={item.id}>
              {item.role_summary} · score {item.match_score} · {formatTimestamp(item.created_at)} ·
              context <code>{item.run_context}</code>
            </li>
          ))}
        </ul>
      ) : null}

      <form className="source-form" onSubmit={onSaveDigest}>
        <h2>Morning digest</h2>
        {digestConfigState === 'loading' ? <p>Loading…</p> : null}
        {digestConfigState === 'failed' ? (
          <p>Could not load digest config — see the error above.</p>
        ) : null}
        {digestConfigState === 'ready' ? (
          <>
            <label>
              Digest threshold
              <input
                name="digest_threshold"
                type="number"
                min="0"
                max="100"
                step="1"
                required
                value={digestThreshold}
                onChange={(event) => setDigestThreshold(event.target.value)}
              />
            </label>
            <label>
              Window hours
              <input
                name="digest_window_hours"
                type="number"
                min="1"
                max="8760"
                step="1"
                required
                value={digestWindow}
                onChange={(event) => setDigestWindow(event.target.value)}
              />
            </label>
            <label>
              Top N
              <input
                name="top_n"
                type="number"
                min="1"
                max="10"
                step="1"
                required
                value={topN}
                onChange={(event) => setTopN(event.target.value)}
              />
            </label>
          </>
        ) : null}
        {digestConfigState !== 'loading' ? (
          <div className="form-actions">
            {digestConfigState === 'ready' ? (
              <button type="submit" disabled={busy}>
                Save digest config
              </button>
            ) : null}
            <button type="button" disabled={busy} onClick={onRunDigest}>
              Run morning digest
            </button>
          </div>
        ) : null}
      </form>

      <h2>Digests{digestsState === 'ready' ? ` (${digests.length})` : ''}</h2>
      {digestsState === 'loading' ? <p>Loading…</p> : null}
      {digestsState === 'failed' ? <p>Could not load digests — see the error above.</p> : null}
      {digestsState === 'ready' && digests.length === 0 ? (
        <p>No digests yet. Run a morning digest after postings exist in the window.</p>
      ) : null}
      {digestsState === 'ready' && digests.length > 0 ? (
        <ul className="posting-list">
          {digests.map((digest) => (
            <li key={digest.id} className="digest-row">
              <strong>{digest.digest_date}</strong> · context <code>{digest.run_context}</code> ·{' '}
              {formatTimestamp(digest.created_at)}
              {digest.is_noop ? (
                <p>No-op digest — nothing met the window and threshold.</p>
              ) : (
                <>
                  {renderItems('New', digest.new_items)}
                  {renderItems('Updated', digest.updated_items)}
                  {renderItems('Expired', digest.expired_items)}
                  {renderItems('Top recommendations', digest.top_recommendations)}
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
