import { apiRequest } from './client.ts'
import type { ApiRequestOptions } from './types.ts'

export type MorningDigestConfig = {
  config_version: string
  digest_threshold: number
  digest_window_hours: number
  top_n: number
}

export type DigestJobItem = {
  job_posting_id: string
  role_summary: string
  match_score: number
  deep_link: string
  lifecycle_state: string
  transitioned_at: string | null
  rank: number | null
}

export type MorningDigest = {
  id: string
  run_context: string
  correlation_id: string
  digest_date: string
  is_noop: boolean
  skipped_below_threshold_count: number
  skipped_missing_score_count: number
  skipped_missing_posting_count: number
  new_items: DigestJobItem[]
  updated_items: DigestJobItem[]
  expired_items: DigestJobItem[]
  top_recommendations: DigestJobItem[]
  created_at: string
}

export function getDigestConfig(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<MorningDigestConfig>('/morning-digest-config', options)
}

export function saveDigestConfig(
  config: { digest_threshold: number; digest_window_hours: number; top_n: number },
  correlationId: string,
) {
  return apiRequest<MorningDigestConfig>('/morning-digest-config', {
    method: 'PUT',
    body: { ...config, config_version: 'v1' },
    correlationId,
  })
}

export function runMorningDigest(correlationId: string, runContext?: string) {
  return apiRequest<MorningDigest>('/digests/morning/run', {
    method: 'POST',
    body: runContext?.trim() ? { run_context: runContext.trim() } : {},
    correlationId,
  })
}

export function listMorningDigests(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<MorningDigest[]>('/digests/morning', options)
}
