import { apiRequest } from './client.ts'
import type { ApiRequestOptions } from './types.ts'

export type CareerSourceStatus = 'enabled' | 'disabled'
export type ComplianceStatus = 'pending' | 'approved' | 'rejected'

export type CareerSource = {
  id: string
  name: string
  base_url: string
  plugin_id: string
  status: CareerSourceStatus
  compliance_status: ComplianceStatus
  compliance_reason: string | null
  robots_check_passed: boolean | null
}

export type SourceWritePayload = {
  name: string
  base_url: string
  plugin_id: string
}

export type JobPosting = {
  id: string
  title: string
  company: string
  location: string
  url: string
  career_source_id: string
  lifecycle_state: string
}

export type CrawlOutcome = {
  source_id: string
  plugin_id: string
  status: string
  error_code: string | null
  error_message: string | null
  duration_ms: number
  job_postings?: JobPosting[]
}

export type CrawlRun = {
  correlation_id: string
  outcomes: CrawlOutcome[]
  succeeded_count: number
  failed_count: number
}

export function listSources(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<CareerSource[]>('/career-sources', options)
}

export function createSource(payload: SourceWritePayload) {
  return apiRequest<CareerSource>('/career-sources', { method: 'POST', body: payload })
}

export function updateSource(sourceId: string, payload: SourceWritePayload) {
  return apiRequest<CareerSource>(`/career-sources/${sourceId}`, {
    method: 'PATCH',
    body: payload,
  })
}

export function enableSource(sourceId: string) {
  return apiRequest<CareerSource>(`/career-sources/${sourceId}/enable`, { method: 'POST' })
}

export function disableSource(sourceId: string) {
  return apiRequest<CareerSource>(`/career-sources/${sourceId}/disable`, { method: 'POST' })
}

export function approveCompliance(sourceId: string) {
  return apiRequest<CareerSource>(`/career-sources/${sourceId}/compliance/approve`, {
    method: 'POST',
  })
}

export function rejectCompliance(sourceId: string, reason: string) {
  return apiRequest<CareerSource>(`/career-sources/${sourceId}/compliance/reject`, {
    method: 'POST',
    body: { reason },
  })
}

export function executeSource(sourceId: string, correlationId: string) {
  return apiRequest<CrawlOutcome>(`/career-sources/${sourceId}/execute`, {
    method: 'POST',
    correlationId,
  })
}

export function runDiscovery(correlationId: string) {
  return apiRequest<CrawlRun>('/discovery/runs', { method: 'POST', correlationId })
}

export function listJobPostings(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<JobPosting[]>('/job-postings', options)
}
