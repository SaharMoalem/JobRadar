import { ApiClientError, apiRequest } from './client.ts'
import { listJobPostings } from './sources.ts'
import type { ApiRequestOptions } from './types.ts'

export const FILTER_SESSION_ID = 'web-opportunities'

export const WORK_MODELS = ['hybrid', 'on_site', 'remote'] as const
export const LIFECYCLE_STATES = ['new', 'updated', 'active', 'expired', 'archived'] as const

export type SearchForm = {
  role_family: string
  location: string
  work_model: string
  min_score: string
  max_score: string
  freshness_days: string
  lifecycle_states: string[]
}

export type OpportunitySearchRequest = {
  role_family?: string
  location?: string
  work_model?: string
  min_score?: number
  max_score?: number
  freshness_days?: number
  lifecycle_states?: string[]
  session_id: string
}

export type OpportunityItem = {
  job_posting_id: string
  title: string
  company: string
  location: string
  url: string
  posted_at: string | null
  lifecycle_state: string
  role_family: string
  work_model: string
  match_score: number | null
}

export type OpportunitySearchResult = {
  items: OpportunityItem[]
  total_count: number
  empty: boolean
}

export type OpportunityFilterState = {
  session_id: string
  criteria: Record<string, unknown>
  updated_at: string
}

export type GateTraceEntry = {
  gate: string
  passed: boolean
  message: string
}

export type GatedRecommendation = {
  job_posting_id: string
  match_score: number
  actionable: boolean
  gate_trace: GateTraceEntry[]
}

export type TopRecommendation = {
  job_posting_id: string
  match_score: number
  rank: number | null
  suppressed: boolean
}

export type ExplainabilityNote = {
  match_rationale: string
  missing_skills: string[]
  interview_probability_pct: number
  effort_estimate: string
}

export type ExplainableRecommendation = {
  job_posting_id: string
  match_score: number
  promoted: boolean
  note: ExplainabilityNote | null
}

export type UserProfile = {
  skills: string[]
  preferred_locations: string[]
  preferred_languages: string[]
  target_seniority: string
}

export type ScoringRun = {
  scored_count: number
  skipped_count: number
}

export type GatingRun = {
  actionable_count: number
  non_actionable_count: number
  skipped_count: number
}

export type PrecisionRun = {
  top_count: number
  suppressed_low_confidence_count: number
  suppressed_capacity_count: number
}

export type ExplainabilityRun = {
  promoted_count: number
  failed_count: number
}

export function emptySearchForm(): SearchForm {
  return {
    role_family: '',
    location: '',
    work_model: '',
    min_score: '',
    max_score: '',
    freshness_days: '',
    lifecycle_states: [],
  }
}

export function formFromCriteria(criteria: Record<string, unknown> | null | undefined): SearchForm {
  const form = emptySearchForm()
  if (!criteria) {
    return form
  }
  if (typeof criteria.role_family === 'string') {
    form.role_family = criteria.role_family
  }
  if (typeof criteria.location === 'string') {
    form.location = criteria.location
  }
  if (typeof criteria.work_model === 'string') {
    form.work_model = criteria.work_model
  }
  if (typeof criteria.min_score === 'number') {
    form.min_score = String(criteria.min_score)
  }
  if (typeof criteria.max_score === 'number') {
    form.max_score = String(criteria.max_score)
  }
  if (typeof criteria.freshness_days === 'number') {
    form.freshness_days = String(criteria.freshness_days)
  }
  if (Array.isArray(criteria.lifecycle_states)) {
    form.lifecycle_states = criteria.lifecycle_states.filter(
      (value): value is string => typeof value === 'string',
    )
  }
  return form
}

function optionalNumber(raw: string): number | undefined {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return undefined
  }
  const parsed = Number(trimmed)
  // JSON.stringify turns NaN and Infinity into null, which the API reads as
  // "filter not supplied" — omit them instead of dropping the filter silently.
  return Number.isFinite(parsed) ? parsed : undefined
}

export function searchPayload(form: SearchForm): OpportunitySearchRequest {
  const body: OpportunitySearchRequest = { session_id: FILTER_SESSION_ID }
  const roleFamily = form.role_family.trim()
  const location = form.location.trim()
  const workModel = form.work_model.trim()
  if (roleFamily) {
    body.role_family = roleFamily
  }
  if (location) {
    body.location = location
  }
  if (workModel) {
    body.work_model = workModel
  }
  const minScore = optionalNumber(form.min_score)
  if (minScore !== undefined) {
    body.min_score = minScore
  }
  const maxScore = optionalNumber(form.max_score)
  if (maxScore !== undefined) {
    body.max_score = maxScore
  }
  const freshness = optionalNumber(form.freshness_days)
  if (freshness !== undefined) {
    body.freshness_days = freshness
  }
  if (form.lifecycle_states.length > 0) {
    body.lifecycle_states = [...form.lifecycle_states]
  }
  return body
}

export function getFilterState(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<OpportunityFilterState | null>(
    `/opportunity-filter-state?session_id=${encodeURIComponent(FILTER_SESSION_ID)}`,
    options,
  )
}

export function saveFilterState(form: SearchForm) {
  return apiRequest<OpportunityFilterState>('/opportunity-filter-state', {
    method: 'PUT',
    body: searchPayload(form),
  })
}

export function searchOpportunities(
  form: SearchForm,
  options?: Pick<ApiRequestOptions, 'signal'>,
) {
  return apiRequest<OpportunitySearchResult>('/opportunities/search', {
    method: 'POST',
    body: searchPayload(form),
    signal: options?.signal,
  })
}

/**
 * Titles for every known posting. The recommendation endpoints are global, so a
 * filtered search result is not enough to label them.
 */
export async function listJobTitles(
  options?: Pick<ApiRequestOptions, 'signal'>,
): Promise<Record<string, string>> {
  const result = await listJobPostings(options)
  const titles: Record<string, string> = {}
  for (const posting of result.data ?? []) {
    titles[posting.id] = posting.title
  }
  return titles
}

export function listActionable(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<GatedRecommendation[]>('/recommendations/actionable', options)
}

export function listTop(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<TopRecommendation[]>('/recommendations/top', options)
}

export function listExplainable(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<ExplainableRecommendation[]>('/recommendations/explainable', options)
}

export async function getUserProfile(options?: Pick<ApiRequestOptions, 'signal'>) {
  try {
    return await apiRequest<UserProfile>('/user-profile', options)
  } catch (err) {
    if (err instanceof ApiClientError && err.code === 'PROFILE_NOT_CONFIGURED') {
      return { data: null, meta: {} }
    }
    throw err
  }
}

export function saveUserProfile(profile: UserProfile) {
  return apiRequest<UserProfile>('/user-profile', { method: 'PUT', body: profile })
}

export function runScoring(correlationId: string) {
  return apiRequest<ScoringRun>('/match-scores/run', { method: 'POST', correlationId })
}

export function runGating(correlationId: string) {
  return apiRequest<GatingRun>('/recommendations/gating/run', { method: 'POST', correlationId })
}

export function runPrecision(correlationId: string) {
  return apiRequest<PrecisionRun>('/recommendations/precision/run', { method: 'POST', correlationId })
}

export function runExplainability(correlationId: string) {
  return apiRequest<ExplainabilityRun>('/recommendations/explainability/run', {
    method: 'POST',
    correlationId,
  })
}
