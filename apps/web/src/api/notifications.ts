import { apiRequest } from './client.ts'
import type { ApiRequestOptions } from './types.ts'

export const NOTIFICATION_KINDS = ['immediate_alert', 'morning_digest'] as const
export const NOTIFICATION_CHANNELS = ['in_app', 'email'] as const

export type NotificationKind = (typeof NOTIFICATION_KINDS)[number]
export type NotificationChannelId = (typeof NOTIFICATION_CHANNELS)[number]

export type NotificationDelivery = {
  id: string
  channel_id: string
  kind: string
  source_id: string
  correlation_id: string
  run_context: string
  status: string
  detail: string
  created_at: string
}

export type NotificationDeliveryBatch = {
  delivered_count: number
  failed_count: number
  skipped_missing_source_count: number
  run_context: string
  kind: string
  deliveries: NotificationDelivery[]
}

export function deliverNotifications(
  payload: {
    kind: NotificationKind
    run_context?: string
    source_id?: string
    channels?: NotificationChannelId[]
  },
  correlationId: string,
) {
  const body: Record<string, unknown> = { kind: payload.kind }
  if (payload.run_context?.trim()) {
    body.run_context = payload.run_context.trim()
  }
  if (payload.source_id?.trim()) {
    body.source_id = payload.source_id.trim()
  }
  if (payload.channels && payload.channels.length > 0) {
    body.channels = payload.channels
  }
  return apiRequest<NotificationDeliveryBatch>('/notifications/deliver', {
    method: 'POST',
    body,
    correlationId,
  })
}

export function listNotificationDeliveries(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<NotificationDelivery[]>('/notifications/deliveries', options)
}

export function listInAppNotifications(options?: Pick<ApiRequestOptions, 'signal'>) {
  return apiRequest<NotificationDelivery[]>('/notifications/in-app', options)
}
