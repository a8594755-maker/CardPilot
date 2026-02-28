// ===== Notification Domain Types =====

export type NotificationType =
  | 'table_opened'
  | 'table_started'
  | 'join_request_received'
  | 'join_request_approved'
  | 'join_request_rejected'
  | 'role_changed'
  | 'kicked'
  | 'banned'
  | 'credit_granted'
  | 'credit_deducted'
  | 'chat_mention';

export interface Notification {
  id: string;
  userId: string;
  type: NotificationType;
  clubId: string | null;
  refId: string | null;
  title: string;
  body: string;
  metadata: Record<string, unknown>;
  isRead: boolean;
  readAt: string | null;
  createdAt: string;
}

export interface NotificationPreferences {
  userId: string;
  preferences: Partial<Record<NotificationType, boolean>>;
  updatedAt: string;
}
