import { apiRequest } from './client.ts'
import type { ApiRequestOptions } from './types.ts'

export type ImmediateAlertConfig = {
  config_version: string
  alert_threshold: number
}

export type ImmediateAlert = {
  id: string
  job_posting_id: string
  role_summary: string
  match_score: number
  deep_link: string
  run_context: string
  correlation_id: string
  created_at: string
}

export type ImmediateAlertBatch = {
  triggered_count: number
  skipped_below_threshold_count: number
  skipped_duplicate_count: number
  skipped_missing_posting_count: number
  run_context: string
  alerts: ImmediateAlert[]
}

export function getAlertConfig(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<ImmediateAlertConfig>('/immediate-alert-config', options)
}

export function saveAlertConfig(alertThreshold: number, correlationId: string) {
  return apiRequest<ImmediateAlertConfig>('/immediate-alert-config', {
    method: 'PUT',
    body: { alert_threshold: alertThreshold, config_version: 'v1' },
    correlationId,
  })
}

export function runImmediateAlerts(correlationId: string, runContext?: string) {
  return apiRequest<ImmediateAlertBatch>('/alerts/immediate/run', {
    method: 'POST',
    body: runContext?.trim() ? { run_context: runContext.trim() } : {},
    correlationId,
  })
}

export function listImmediateAlerts(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<ImmediateAlert[]>('/alerts/immediate', options)
}
