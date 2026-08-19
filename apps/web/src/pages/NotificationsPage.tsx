import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { isAbortError, newCorrelationId } from '../api/client.ts'
import {
  NOTIFICATION_CHANNELS,
  NOTIFICATION_KINDS,
  deliverNotifications,
  listInAppNotifications,
  listNotificationDeliveries,
  type NotificationChannelId,
  type NotificationDelivery,
  type NotificationKind,
} from '../api/notifications.ts'
import {
  type LoadState,
  combinedError,
  errorMessage,
  formatTimestamp,
  rejections,
} from '../lib/ui.ts'

export function NotificationsPage() {
  const [kind, setKind] = useState<NotificationKind>('immediate_alert')
  const [runContext, setRunContext] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [channels, setChannels] = useState<NotificationChannelId[]>([...NOTIFICATION_CHANNELS])
  const [inbox, setInbox] = useState<NotificationDelivery[]>([])
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([])
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [inboxState, setInboxState] = useState<LoadState>('loading')
  const [deliveriesState, setDeliveriesState] = useState<LoadState>('loading')

  const busy = initializing || actionBusy

  const loadWorkspace = useCallback(async (signal?: AbortSignal): Promise<unknown[]> => {
    const [inboxResult, deliveryResult] = await Promise.allSettled([
      listInAppNotifications({ signal }),
      listNotificationDeliveries({ signal }),
    ])
    if (signal?.aborted) {
      return []
    }
    if (inboxResult.status === 'fulfilled') {
      setInbox(inboxResult.value.data ?? [])
      setInboxState('ready')
    } else {
      setInboxState('failed')
    }
    if (deliveryResult.status === 'fulfilled') {
      setDeliveries(deliveryResult.value.data ?? [])
      setDeliveriesState('ready')
    } else {
      setDeliveriesState('failed')
    }
    return rejections([inboxResult, deliveryResult])
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

  function toggleChannel(channel: NotificationChannelId) {
    setChannels((current) =>
      current.includes(channel)
        ? current.filter((item) => item !== channel)
        : [...current, channel],
    )
  }

  function onDeliver(event: FormEvent) {
    event.preventDefault()
    if (channels.length === 0) {
      setSummary(null)
      setError('Select at least one channel. Clearing both does not deliver to every channel.')
      return
    }
    void runAction(async () => {
      const result = await deliverNotifications(
        {
          kind,
          run_context: runContext.trim() || undefined,
          source_id: sourceId.trim() || undefined,
          channels,
        },
        newCorrelationId(),
      )
      if (!result.data) {
        setError('Delivery may have run, but the API returned no record.')
        return
      }
      const batch = result.data
      setSummary(
        `Delivered ${batch.delivered_count}, failed ${batch.failed_count}, skipped missing source ${batch.skipped_missing_source_count}. run_context ${batch.run_context}. Email is recorded locally — nothing is sent externally.`,
      )
      try {
        const [inboxResult, deliveryResult] = await Promise.allSettled([
          listInAppNotifications(),
          listNotificationDeliveries(),
        ])
        if (inboxResult.status === 'fulfilled') {
          setInbox(inboxResult.value.data ?? [])
          setInboxState('ready')
        } else {
          setInboxState('failed')
        }
        if (deliveryResult.status === 'fulfilled') {
          setDeliveries(deliveryResult.value.data ?? [])
          setDeliveriesState('ready')
        } else {
          setDeliveriesState('failed')
        }
        const refreshFailures = rejections([inboxResult, deliveryResult])
        if (refreshFailures.length > 0) {
          setError(
            `Delivery finished, but the lists did not fully reload. ${combinedError(refreshFailures)}`,
          )
        }
      } catch (err) {
        setError(`Delivery finished, but the lists did not reload. ${errorMessage(err)}`)
      }
    })
  }

  return (
    <section className="page sources-page notifications-page" aria-busy={busy}>
      <h1>Notifications</h1>
      <p>
        Fan out a completed alert or digest run to the in-app inbox and the recording email
        adapter. Delivery is local — the email channel stores a record, it does not send mail.
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

      <form className="source-form" onSubmit={onDeliver}>
        <h2>Deliver</h2>
        <label>
          Kind
          <select
            name="kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as NotificationKind)}
          >
            {NOTIFICATION_KINDS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          Run context
          <input
            name="run_context"
            value={runContext}
            onChange={(event) => setRunContext(event.target.value)}
            placeholder="From the last alert or digest run"
          />
        </label>
        <label>
          Source id (optional)
          <input
            name="source_id"
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
          />
        </label>
        <fieldset className="lifecycle-set">
          <legend>Channels</legend>
          {NOTIFICATION_CHANNELS.map((channel) => (
            <label key={channel} className="checkbox-label">
              <input
                type="checkbox"
                name={`channel_${channel}`}
                checked={channels.includes(channel)}
                onChange={() => toggleChannel(channel)}
              />
              {channel}
            </label>
          ))}
          <p className="hint">
            Tick the channels to fan out to. Unchecking both disables Deliver — it does not omit the
            field and use every registered channel. There is no channel-list API — these two ids are
            wired in the server.
          </p>
        </fieldset>
        <div className="form-actions">
          <button type="submit" disabled={busy || channels.length === 0}>
            Deliver
          </button>
        </div>
      </form>

      <h2>In-app inbox{inboxState === 'ready' ? ` (${inbox.length})` : ''}</h2>
      {inboxState === 'loading' ? <p>Loading…</p> : null}
      {inboxState === 'failed' ? <p>Could not load the inbox — see the error above.</p> : null}
      {inboxState === 'ready' && inbox.length === 0 ? <p>Inbox is empty.</p> : null}
      {inboxState === 'ready' && inbox.length > 0 ? (
        <ul className="posting-list">
          {inbox.map((item) => (
            <li key={item.id}>
              {item.detail} · {formatTimestamp(item.created_at)}
            </li>
          ))}
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
          {deliveries.map((item) => (
            <li key={item.id}>
              {item.channel_id} · {item.status} · {item.kind} · {item.detail} ·{' '}
              {formatTimestamp(item.created_at)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
