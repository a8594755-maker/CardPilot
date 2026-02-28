// ===== Chat Domain Types =====

export type ChatMessageType = 'text' | 'system';

export interface ChatMessage {
  id: string;
  clubId: string;
  tableId: string | null;
  senderUserId: string;
  senderDisplayName: string;
  messageType: ChatMessageType;
  content: string;
  mentions: string[];         // userId array
  deletedAt: string | null;
  deletedBy: string | null;
  createdAt: string;
}

export interface ChatMute {
  id: string;
  clubId: string;
  userId: string;
  mutedBy: string;
  reason: string;
  expiresAt: string | null;
  createdAt: string;
}

export interface ChatReadCursor {
  clubId: string;
  userId: string;
  scopeKey: string;           // 'club' or 'table:{tableId}'
  lastReadMessageId: string | null;
  lastReadAt: string;
}

export interface ChatUnreadCount {
  clubId: string;
  scopeKey: string;
  count: number;
}
