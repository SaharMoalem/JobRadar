import {
  type FormEvent,
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { isAbortError, newCorrelationId } from '../api/client.ts'
import {
  type LoadState,
  combinedError,
  errorMessage,
  formatDate,
  rejections,
  safeHref,
  splitCsv,
} from '../lib/ui.ts'
import {
  FILTER_SESSION_ID,
  LIFECYCLE_STATES,
  WORK_MODELS,
  emptySearchForm,
  formFromCriteria,
  getFilterState,
  getUserProfile,
  listActionable,
  listExplainable,
  listJobTitles,
  listTop,
  runExplainability,
  runGating,
  runPrecision,
  runScoring,
  saveFilterState,
  saveUserProfile,
  searchOpportunities,
  type ExplainableRecommendation,
  type GatedRecommendation,
  type OpportunityItem,
  type OpportunitySearchResult,
  type SearchForm,
  type TopRecommendation,
  type UserProfile,
} from '../api/opportunities.ts'
import { bookmarkOpportunity } from '../api/tracker.ts'

const PIPELINE_ORDER = ['scoring', 'gating', 'precision', 'explainability'] as const

type PipelineStage = (typeof PIPELINE_ORDER)[number]

function staleStagesNote(stage: PipelineStage): string {
  const downstream = PIPELINE_ORDER.slice(PIPELINE_ORDER.indexOf(stage) + 1)
  if (downstream.length === 0) {
    return ''
  }
  return ` Sections below still reflect the previous ${downstream.join(', ')} run — re-run those to keep them consistent.`
}

export function OpportunitiesPage() {
  const [form, setForm] = useState<SearchForm>(emptySearchForm())
  const [items, setItems] = useState<OpportunityItem[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [empty, setEmpty] = useState(false)
  const [titles, setTitles] = useState<Record<string, string>>({})
  const [actionable, setActionable] = useState<GatedRecommendation[]>([])
  const [top, setTop] = useState<TopRecommendation[]>([])
  const [explainable, setExplainable] = useState<ExplainableRecommendation[]>([])
  const [skills, setSkills] = useState('')
  const [locations, setLocations] = useState('')
  const [languages, setLanguages] = useState('')
  const [seniority, setSeniority] = useState('')
  // Confirmed bookmarks only, so the label never claims a write the API did not accept.
  const [bookmarked, setBookmarked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [runSummary, setRunSummary] = useState<string | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [resultsState, setResultsState] = useState<LoadState>('loading')
  const [actionableState, setActionableState] = useState<LoadState>('loading')
  const [topState, setTopState] = useState<LoadState>('loading')
  const [explainableState, setExplainableState] = useState<LoadState>('loading')

  const busy = initializing || actionBusy

  // Pipeline refreshes must reuse the criteria that produced the visible results,
  // not whatever the user has since typed into the form.
  const lastSearchRef = useRef<SearchForm>(emptySearchForm())

  const applySearchResult = useCallback((result: OpportunitySearchResult | null | undefined) => {
    setItems(result?.items ?? [])
    setTotalCount(result?.total_count ?? 0)
    setEmpty(Boolean(result?.empty))
    setResultsState('ready')
  }, [])

  const loadRecommendations = useCallback(async (signal?: AbortSignal): Promise<unknown[]> => {
    const [actionableResult, topResult, explainableResult] = await Promise.allSettled([
      listActionable({ signal }),
      listTop({ signal }),
      listExplainable({ signal }),
    ])
    if (signal?.aborted) {
      return []
    }
    if (actionableResult.status === 'fulfilled') {
      setActionable(actionableResult.value.data ?? [])
      setActionableState('ready')
    } else {
      setActionableState('failed')
    }
    if (topResult.status === 'fulfilled') {
      setTop(topResult.value.data ?? [])
      setTopState('ready')
    } else {
      setTopState('failed')
    }
    if (explainableResult.status === 'fulfilled') {
      setExplainable(explainableResult.value.data ?? [])
      setExplainableState('ready')
    } else {
      setExplainableState('failed')
    }
    return rejections([actionableResult, topResult, explainableResult])
  }, [])

  const loadWorkspace = useCallback(
    async (signal?: AbortSignal): Promise<unknown[]> => {
      const failures: unknown[] = []
      let nextForm = emptySearchForm()
      try {
        const state = await getFilterState({ signal })
        if (signal?.aborted) {
          return []
        }
        if (state.data?.criteria) {
          nextForm = formFromCriteria(state.data.criteria)
          setForm(nextForm)
        }
      } catch (err) {
        if (signal?.aborted || isAbortError(err)) {
          return []
        }
        failures.push(err)
      }
      lastSearchRef.current = nextForm

      const [searchResult, profileResult, titleResult] = await Promise.allSettled([
        searchOpportunities(nextForm, { signal }),
        getUserProfile({ signal }),
        listJobTitles({ signal }),
      ])
      if (signal?.aborted) {
        return []
      }
      if (searchResult.status === 'fulfilled') {
        applySearchResult(searchResult.value.data)
      } else {
        setResultsState('failed')
      }
      if (profileResult.status === 'fulfilled' && profileResult.value.data) {
        const profile = profileResult.value.data
        setSkills(profile.skills.join(', '))
        setLocations(profile.preferred_locations.join(', '))
        setLanguages(profile.preferred_languages.join(', '))
        setSeniority(profile.target_seniority)
      }
      if (titleResult.status === 'fulfilled') {
        setTitles(titleResult.value)
      }
      failures.push(...rejections([searchResult, profileResult, titleResult]))

      // Recommendation failures must not preempt the failures collected above.
      failures.push(...(await loadRecommendations(signal)))
      return signal?.aborted ? [] : failures
    },
    [applySearchResult, loadRecommendations],
  )

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

  async function runAction(action: () => Promise<unknown>) {
    setActionBusy(true)
    setError(null)
    setRunSummary(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
      setRunSummary(null)
    } finally {
      setActionBusy(false)
    }
  }

  function onSearch(event: FormEvent) {
    event.preventDefault()
    void runAction(async () => {
      const submitted = form
      const result = await searchOpportunities(submitted)
      lastSearchRef.current = submitted
      applySearchResult(result.data)
    })
  }

  function onSaveFilters(event: MouseEvent<HTMLButtonElement>) {
    // Save bypasses submit, so the numeric constraints need an explicit check.
    if (!event.currentTarget.form?.reportValidity()) {
      return
    }
    void runAction(async () => {
      await saveFilterState(form)
      setRunSummary(`Filters saved for session ${FILTER_SESSION_ID}.`)
    })
  }

  /** The tracker's entry point: a posting id is never shown, so it is bookmarked from here. */
  function onBookmark(jobPostingId: string, title: string) {
    void runAction(async () => {
      const result = await bookmarkOpportunity(jobPostingId, newCorrelationId())
      if (!result.data) {
        setError(`${title} may have been bookmarked, but the API returned no record.`)
        return
      }
      setBookmarked((current) =>
        current.includes(jobPostingId) ? current : [...current, jobPostingId],
      )
      setRunSummary(
        `Bookmarked ${title} in state ${result.data.tracker_state}. Move it on the Tracker page.`,
      )
    })
  }

  function profilePayload(): UserProfile {
    return {
      skills: splitCsv(skills),
      preferred_locations: splitCsv(locations),
      preferred_languages: splitCsv(languages),
      target_seniority: seniority.trim(),
    }
  }

  function onSaveProfile(event: FormEvent) {
    event.preventDefault()
    void runAction(async () => {
      const saved = await saveUserProfile(profilePayload())
      if (saved.data) {
        setSkills(saved.data.skills.join(', '))
        setLocations(saved.data.preferred_locations.join(', '))
        setLanguages(saved.data.preferred_languages.join(', '))
        setSeniority(saved.data.target_seniority)
      }
      setRunSummary('Profile saved. Re-run scoring to apply it to match scores.')
    })
  }

  async function refreshAfterPipeline() {
    const [searchResult, recFailures] = await Promise.allSettled([
      searchOpportunities(lastSearchRef.current),
      loadRecommendations(),
    ])
    if (searchResult.status === 'fulfilled') {
      applySearchResult(searchResult.value.data)
    } else {
      setResultsState('failed')
    }
    const failures = rejections([searchResult, recFailures])
    if (recFailures.status === 'fulfilled') {
      failures.push(...recFailures.value)
    }
    return failures
  }

  function runPipeline(stage: PipelineStage, run: () => Promise<string>) {
    void runAction(async () => {
      const summary = await run()
      const failures = await refreshAfterPipeline()
      setRunSummary(`${summary}${staleStagesNote(stage)}`)
      const refreshError = combinedError(failures)
      if (refreshError) {
        setError(`Run succeeded but refresh failed — ${refreshError}`)
      }
    })
  }

  function metaCorrelation(meta: Record<string, unknown>, fallback: string) {
    return typeof meta.correlation_id === 'string' && meta.correlation_id.trim()
      ? meta.correlation_id
      : fallback
  }

  function toggleLifecycle(state: string) {
    setForm((current) => {
      const selected = current.lifecycle_states.includes(state)
        ? current.lifecycle_states.filter((item) => item !== state)
        : [...current.lifecycle_states, state]
      return { ...current, lifecycle_states: selected }
    })
  }

  const titleLookup = useMemo(() => {
    const lookup: Record<string, string> = { ...titles }
    for (const item of items) {
      lookup[item.job_posting_id] = item.title
    }
    return lookup
  }, [titles, items])

  function titleFor(jobPostingId: string): string {
    return titleLookup[jobPostingId] ?? jobPostingId
  }

  function renderPlaceholder(state: LoadState, emptyCopy: string) {
    if (state === 'loading') {
      return <p>Loading…</p>
    }
    if (state === 'failed') {
      return <p>Could not load this list — see the error above.</p>
    }
    return <p>{emptyCopy}</p>
  }

  return (
    <section className="page sources-page opportunities-page">
      <h1>Opportunities</h1>
      <p>Search openings and inspect gated, top, and explainable recommendations.</p>

      {error ? (
        <p className="banner-error" role="alert">
          {error}
        </p>
      ) : null}
      {runSummary ? (
        <p className="banner-ok" role="status">
          {runSummary}
        </p>
      ) : null}

      <form className="source-form" onSubmit={onSearch}>
        <h2>Filters</h2>
        <label>
          Role family
          <input
            name="role_family"
            value={form.role_family}
            onChange={(event) => setForm({ ...form, role_family: event.target.value })}
          />
        </label>
        <label>
          Location
          <input
            name="location"
            value={form.location}
            onChange={(event) => setForm({ ...form, location: event.target.value })}
          />
        </label>
        <label>
          Work model
          <select
            name="work_model"
            value={form.work_model}
            onChange={(event) => setForm({ ...form, work_model: event.target.value })}
          >
            <option value="">Any</option>
            {WORK_MODELS.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
        <label>
          Min score
          <input
            name="min_score"
            type="number"
            min="0"
            max="100"
            step="1"
            value={form.min_score}
            onChange={(event) => setForm({ ...form, min_score: event.target.value })}
          />
        </label>
        <label>
          Max score
          <input
            name="max_score"
            type="number"
            min="0"
            max="100"
            step="1"
            value={form.max_score}
            onChange={(event) => setForm({ ...form, max_score: event.target.value })}
          />
        </label>
        <label>
          Freshness days
          <input
            name="freshness_days"
            type="number"
            min="1"
            step="1"
            value={form.freshness_days}
            onChange={(event) => setForm({ ...form, freshness_days: event.target.value })}
          />
        </label>
        <fieldset className="lifecycle-set">
          <legend>Lifecycle</legend>
          {LIFECYCLE_STATES.map((state) => (
            <label key={state} className="checkbox-label">
              <input
                type="checkbox"
                name={`lifecycle_${state}`}
                checked={form.lifecycle_states.includes(state)}
                onChange={() => toggleLifecycle(state)}
              />
              {state}
            </label>
          ))}
          <p className="hint">
            With none selected the API shows new, updated, and active only — tick expired or
            archived to include them.
          </p>
        </fieldset>
        <div className="form-actions">
          <button type="submit" disabled={busy}>
            Search
          </button>
          <button type="button" disabled={busy} onClick={onSaveFilters}>
            Save filters
          </button>
        </div>
      </form>

      <h2>Results ({totalCount})</h2>
      {resultsState !== 'ready' || empty || items.length === 0 ? (
        renderPlaceholder(resultsState, 'No opportunities match these filters.')
      ) : (
        <ul className="posting-list">
          {items.map((item) => {
            const href = safeHref(item.url)
            return (
              <li key={item.job_posting_id}>
                <strong>{item.title}</strong> · {item.company} · {item.location} · score{' '}
                {item.match_score ?? '—'} · {item.lifecycle_state}
                {item.posted_at ? ` · ${formatDate(item.posted_at)}` : ''}
                {href ? (
                  <>
                    {' '}
                    ·{' '}
                    <a href={href} target="_blank" rel="noreferrer">
                      Open
                    </a>
                  </>
                ) : null}
                <div className="row-actions">
                  <button
                    type="button"
                    disabled={busy || bookmarked.includes(item.job_posting_id)}
                    onClick={() => onBookmark(item.job_posting_id, item.title)}
                  >
                    {bookmarked.includes(item.job_posting_id) ? 'Bookmarked' : 'Bookmark'}
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      <form className="source-form" onSubmit={onSaveProfile}>
        <h2>User profile</h2>
        <label>
          Skills
          <input
            name="skills"
            value={skills}
            onChange={(event) => setSkills(event.target.value)}
          />
        </label>
        <label>
          Preferred locations
          <input
            name="preferred_locations"
            value={locations}
            onChange={(event) => setLocations(event.target.value)}
          />
        </label>
        <label>
          Preferred languages
          <input
            name="preferred_languages"
            value={languages}
            onChange={(event) => setLanguages(event.target.value)}
          />
        </label>
        <label>
          Target seniority
          <input
            name="target_seniority"
            value={seniority}
            onChange={(event) => setSeniority(event.target.value)}
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={busy}>
            Save profile
          </button>
        </div>
      </form>

      <div className="section-heading">
        <h2>Recommendation pipelines</h2>
        <p className="hint">
          Each stage feeds the next — run them in order: scoring → gating → precision →
          explainability.
        </p>
        <div className="form-actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              runPipeline('scoring', async () => {
                const correlationId = newCorrelationId()
                const result = await runScoring(correlationId)
                return `Scoring scored=${result.data.scored_count} skipped=${result.data.skipped_count}. Correlation ${metaCorrelation(result.meta, correlationId)}.`
              })
            }
          >
            Run scoring
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              runPipeline('gating', async () => {
                const correlationId = newCorrelationId()
                const result = await runGating(correlationId)
                return `Gating actionable=${result.data.actionable_count} non_actionable=${result.data.non_actionable_count} skipped=${result.data.skipped_count}. Correlation ${metaCorrelation(result.meta, correlationId)}.`
              })
            }
          >
            Run gating
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              runPipeline('precision', async () => {
                const correlationId = newCorrelationId()
                const result = await runPrecision(correlationId)
                return `Precision top=${result.data.top_count} suppressed_low_confidence=${result.data.suppressed_low_confidence_count} suppressed_capacity=${result.data.suppressed_capacity_count}. Correlation ${metaCorrelation(result.meta, correlationId)}.`
              })
            }
          >
            Run precision
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              runPipeline('explainability', async () => {
                const correlationId = newCorrelationId()
                const result = await runExplainability(correlationId)
                return `Explainability promoted=${result.data.promoted_count} failed=${result.data.failed_count}. Correlation ${metaCorrelation(result.meta, correlationId)}.`
              })
            }
          >
            Run explainability
          </button>
        </div>
      </div>

      <h2>Actionable</h2>
      {actionableState !== 'ready' || actionable.length === 0 ? (
        renderPlaceholder(
          actionableState,
          'No actionable recommendations. Gates may have filtered everything, or scoring/gating has not been run.',
        )
      ) : (
        <ul className="posting-list">
          {actionable.map((item) => (
            <li key={item.job_posting_id}>
              <strong>{titleFor(item.job_posting_id)}</strong> · score {item.match_score}
              {item.gate_trace.length > 0 ? (
                <ul className="gate-trace">
                  {item.gate_trace.map((gate) => (
                    <li key={gate.gate} className={gate.passed ? 'gate-pass' : 'gate-fail'}>
                      {gate.gate}: {gate.passed ? 'passed' : 'failed'} — {gate.message}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <h2>Top</h2>
      {topState !== 'ready' || top.length === 0 ? (
        renderPlaceholder(
          topState,
          'No top recommendations. Precision policy may have suppressed the list (confidence or capacity).',
        )
      ) : (
        <ul className="posting-list">
          {top.map((item) => (
            <li key={item.job_posting_id}>
              <strong>{titleFor(item.job_posting_id)}</strong> · rank {item.rank ?? '—'} · score{' '}
              {item.match_score}
            </li>
          ))}
        </ul>
      )}

      <h2>Explainable</h2>
      {explainableState !== 'ready' || explainable.length === 0 ? (
        renderPlaceholder(
          explainableState,
          'No explainability notes. Run explainability after top recommendations exist.',
        )
      ) : (
        <ul className="posting-list">
          {explainable.map((item) => (
            <li key={item.job_posting_id}>
              <strong>{titleFor(item.job_posting_id)}</strong>
              {item.note ? (
                <p>
                  {item.note.match_rationale} Missing: {item.note.missing_skills.join(', ') || 'none'}.
                  Interview {item.note.interview_probability_pct}%. Effort {item.note.effort_estimate}.
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
