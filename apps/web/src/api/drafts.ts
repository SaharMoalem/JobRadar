import { apiRequest } from './client.ts'
import type { TrackerState } from './tracker.ts'
import type { ApiRequestOptions } from './types.ts'

export const DRAFT_KINDS = ['recruiter_message', 'cv_improvement', 'interview_prep'] as const

export type DraftKind = (typeof DRAFT_KINDS)[number]

/** Tracker states the API accepts for draft generation (`draft_artifact_policy.py`). */
export const DRAFTABLE_TRACKER_STATES: readonly TrackerState[] = ['review', 'apply'] as const

export type DraftArtifact = {
  id: string
  job_posting_id: string
  kind: DraftKind
  content: string
  source_reference: string
  /** `DraftArtifactStatus` has exactly one member today; the API never returns anything else. */
  status: 'draft'
  is_latest: boolean
  correlation_id: string
  created_at: string
}

export type OutboundApproval = {
  id: string
  artifact_id: string
  correlation_id: string
  approved_at: string
}

export type OutboundDelivery = {
  id: string
  artifact_id: string
  approval_id: string
  channel: string
  correlation_id: string
  content_snapshot: string
  delivered_at: string
}

export function listDrafts(jobPostingId: string, options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<DraftArtifact[]>(
    `/draft-artifacts?job_posting_id=${encodeURIComponent(jobPostingId)}`,
    options,
  )
}

export function generateDraft(jobPostingId: string, kind: DraftKind, correlationId: string) {
  return apiRequest<DraftArtifact>('/draft-artifacts/generate', {
    method: 'POST',
    body: { job_posting_id: jobPostingId, kind },
    correlationId,
  })
}

export function approveOutbound(artifactId: string, correlationId: string) {
  return apiRequest<OutboundApproval>(
    `/draft-artifacts/${encodeURIComponent(artifactId)}/approve-outbound`,
    { method: 'POST', correlationId },
  )
}

export function deliverOutbound(
  artifactId: string,
  channel: string,
  correlationId: string,
) {
  return apiRequest<OutboundDelivery>('/outbound/deliver', {
    method: 'POST',
    body: { artifact_id: artifactId, channel },
    correlationId,
  })
}

export function listDeliveries(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<OutboundDelivery[]>('/outbound/deliveries', options)
}
