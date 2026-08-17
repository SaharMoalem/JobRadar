import { apiRequest } from './client.ts'
import type { ApiRequestOptions } from './types.ts'

export const TRACKER_STATES = [
  'new',
  'review',
  'apply',
  'submitted',
  'rejected',
  'closed',
] as const

export type TrackerState = (typeof TRACKER_STATES)[number]

export type TrackedOpportunity = {
  job_posting_id: string
  tracker_state: TrackerState
  bookmarked: boolean
  bookmarked_at: string | null
  updated_at: string
}

export type TrackerTransition = {
  job_posting_id: string
  from_state: TrackerState | null
  to_state: TrackerState
  reason: string
  correlation_id: string
  transitioned_at: string
}

export function listTracked(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<TrackedOpportunity[]>('/tracker', options)
}

export function bookmarkOpportunity(jobPostingId: string, correlationId: string) {
  return apiRequest<TrackedOpportunity>('/tracker/bookmarks', {
    method: 'POST',
    body: { job_posting_id: jobPostingId },
    correlationId,
  })
}

export function unbookmarkOpportunity(jobPostingId: string, correlationId: string) {
  return apiRequest<TrackedOpportunity>(
    `/tracker/bookmarks/${encodeURIComponent(jobPostingId)}`,
    { method: 'DELETE', correlationId },
  )
}

export function transitionTracked(
  jobPostingId: string,
  toState: TrackerState,
  reason: string,
  correlationId: string,
) {
  return apiRequest<TrackedOpportunity>(
    `/tracker/${encodeURIComponent(jobPostingId)}/transitions`,
    { method: 'POST', body: { to_state: toState, reason }, correlationId },
  )
}

export function listTransitions(
  jobPostingId: string,
  options?: Pick<ApiRequestOptions, 'signal'>,
) {
  return apiRequest<TrackerTransition[]>(
    `/tracker/${encodeURIComponent(jobPostingId)}/transitions`,
    options,
  )
}
