import { type FormEvent, useCallback, useEffect, useState } from 'react'

import { ApiClientError, isAbortError } from '../api/client.ts'
import {
  approveCompliance,
  createSource,
  disableSource,
  enableSource,
  executeSource,
  listJobPostings,
  listSources,
  rejectCompliance,
  runDiscovery,
  updateSource,
  type CareerSource,
  type CrawlOutcome,
  type CrawlRun,
  type JobPosting,
  type SourceWritePayload,
} from '../api/sources.ts'

function errorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    return `${err.code}: ${err.message}`
  }
  return 'Request failed'
}

function defaultForm(source?: CareerSource): SourceWritePayload {
  return {
    name: source?.name ?? '',
    base_url: source?.base_url ?? '',
    plugin_id: source?.plugin_id ?? 'generic',
  }
}

export function SourcesPage() {
  const [sources, setSources] = useState<CareerSource[]>([])
  const [postings, setPostings] = useState<JobPosting[]>([])
  const [form, setForm] = useState<SourceWritePayload>(defaultForm())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runSummary, setRunSummary] = useState<string | null>(null)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [sourceResult, postingResult] = await Promise.allSettled([
      listSources({ signal }),
      listJobPostings({ signal }),
    ])
    if (signal?.aborted) {
      return
    }
    if (sourceResult.status === 'fulfilled') {
      setSources(sourceResult.value.data ?? [])
    }
    if (postingResult.status === 'fulfilled') {
      setPostings(postingResult.value.data ?? [])
    }
    const firstReject = [sourceResult, postingResult].find((item) => item.status === 'rejected')
    if (firstReject && firstReject.status === 'rejected') {
      throw firstReject.reason
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal).catch((err: unknown) => {
      if (controller.signal.aborted || isAbortError(err)) {
        return
      }
      setError(errorMessage(err))
    })
    return () => controller.abort()
  }, [refresh])

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    setRunSummary(null)
    try {
      await action()
      await refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const payload = {
      name: form.name.trim(),
      base_url: form.base_url.trim(),
      plugin_id: form.plugin_id.trim() || 'generic',
    }
    void runAction(async () => {
      if (editingId) {
        await updateSource(editingId, payload)
        setEditingId(null)
      } else {
        await createSource(payload)
      }
      setForm(defaultForm())
    })
  }

  function formatOutcome(outcome: CrawlOutcome, correlationId: string) {
    const extra = outcome.error_code
      ? ` ${outcome.error_code}: ${outcome.error_message ?? ''}`
      : ''
    return `Source ${outcome.source_id} ${outcome.status} (${outcome.duration_ms}ms). Correlation ${correlationId}.${extra}`
  }

  function formatRun(run: CrawlRun, metaCorrelation?: unknown) {
    const correlation =
      run.correlation_id || (typeof metaCorrelation === 'string' ? metaCorrelation : '')
    const failed = run.outcomes
      .filter((item) => item.error_code)
      .map((item) => `${item.source_id}: ${item.error_code}`)
      .join('; ')
    const extra = failed ? ` Failures: ${failed}.` : ''
    return `Discovery succeeded=${run.succeeded_count} failed=${run.failed_count}. Correlation ${correlation}.${extra}`
  }

  return (
    <section className="page sources-page">
      <h1>Sources</h1>
      <p>Register career pages, approve compliance, then run discovery.</p>

      {error ? (
        <p className="banner-error" role="alert">
          {error}
        </p>
      ) : null}
                    {runSummary ? <p className="banner-ok">{runSummary}</p> : null}

      <form className="source-form" onSubmit={onSubmit}>
        <h2>{editingId ? 'Edit source' : 'Add source'}</h2>
        <label>
          Name
          <input
            name="name"
            required
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </label>
        <label>
          Base URL
          <input
            name="base_url"
            type="url"
            required
            value={form.base_url}
            onChange={(event) => setForm({ ...form, base_url: event.target.value })}
          />
        </label>
        <label>
          Plugin
          <input
            name="plugin_id"
            value={form.plugin_id}
            onChange={(event) => setForm({ ...form, plugin_id: event.target.value })}
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={busy}>
            {editingId ? 'Save source' : 'Create source'}
          </button>
          {editingId ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setEditingId(null)
                setForm(defaultForm())
              }}
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>

      <div className="section-heading">
        <h2>Registered sources</h2>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void runAction(async () => {
              const result = await runDiscovery(crypto.randomUUID())
              setRunSummary(formatRun(result.data, result.meta.correlation_id))
            })
          }
        >
          Run discovery
        </button>
      </div>

      {sources.length === 0 ? (
        <p>No career sources yet.</p>
      ) : (
        <ul className="source-list">
          {sources.map((source) => {
            const canApprove = source.compliance_status !== 'approved'
            const canEnable =
              source.status === 'disabled' && source.compliance_status === 'approved'
            const canDisable = source.status === 'enabled'
            const canExecute =
              source.status === 'enabled' && source.compliance_status === 'approved'
            return (
              <li key={source.id} className="source-row">
                <div>
                  <strong>{source.name}</strong>
                  <p>
                    {source.base_url} · plugin {source.plugin_id}
                  </p>
                  <p>
                    {source.status} · compliance {source.compliance_status}
                    {source.compliance_reason ? ` (${source.compliance_reason})` : ''}
                  </p>
                </div>
                <div className="row-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setEditingId(source.id)
                      setForm(defaultForm(source))
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={busy || !canApprove}
                    onClick={() => void runAction(() => approveCompliance(source.id))}
                  >
                    Approve
                  </button>
                  <label>
                    Reject reason
                    <input
                      value={rejectReasons[source.id] ?? ''}
                      onChange={(event) =>
                        setRejectReasons({ ...rejectReasons, [source.id]: event.target.value })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void runAction(() =>
                        rejectCompliance(
                          source.id,
                          rejectReasons[source.id]?.trim() || 'manual_rejection',
                        ),
                      )
                    }
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    disabled={busy || !canEnable}
                    onClick={() => void runAction(() => enableSource(source.id))}
                  >
                    Enable
                  </button>
                  <button
                    type="button"
                    disabled={busy || !canDisable}
                    onClick={() => void runAction(() => disableSource(source.id))}
                  >
                    Disable
                  </button>
                  <button
                    type="button"
                    disabled={busy || !canExecute}
                    onClick={() =>
                      void runAction(async () => {
                        const correlationId = crypto.randomUUID()
                        const result = await executeSource(source.id, correlationId)
                        const reported =
                          typeof result.meta.correlation_id === 'string' &&
                          result.meta.correlation_id.trim()
                            ? result.meta.correlation_id
                            : correlationId
                        setRunSummary(formatOutcome(result.data, reported))
                        if (result.error?.code) {
                          setError(`${result.error.code}: ${result.error.message}`)
                        }
                      })
                    }
                  >
                    Execute
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <h2>Job postings</h2>
      {postings.length === 0 ? (
        <p>No job postings yet. Run discovery after enabling an approved source.</p>
      ) : (
        <ul className="posting-list">
          {postings.map((posting) => (
            <li key={posting.id}>
              <strong>{posting.title}</strong> · {posting.company} · {posting.location} ·{' '}
              {posting.lifecycle_state}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
