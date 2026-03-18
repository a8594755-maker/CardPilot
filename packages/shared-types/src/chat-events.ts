// ===== Chat Socket Events =====

import type { ChatMessage, ChatMute, ChatUnreadCount } from './chat-types.js';

// ── Client → Server Payloads ──

export interface ChatSendPayload {
  clubId: string;
  tableId?: string; // omit for club-level chat
  content: string;
  mentions?: string[]; // userId array
}

export interface ChatHistoryPayload {
  clubId: string;
  tableId?: string;
  before?: string; // cursor: message id
  limit?: number; // default 50
}

export interface ChatDeletePayload {
  clubId: string;
  messageId: string;
}

export interface ChatMutePayload {
  clubId: string;
  userId: string;
  reason?: string;
  durationMinutes?: number; // omit for permanent
}

export interface ChatUnmutePayload {
  clubId: string;
  userId: string;
}

export interface ChatMarkReadPayload {
  clubId: string;
  tableId?: string;
  lastReadMessageId: string;
}

export interface ChatGetUnreadsPayload {
  clubId: string;
}

// ── Server → Client Payloads ──

export interface ChatMessagePayload {
  message: ChatMessage;
}

export interface ChatHistoryResponsePayload {
  clubId: string;
  tableId: string | null;
  messages: ChatMessage[];
  hasMore: boolean;
}

export interface ChatMessageDeletedPayload {
  clubId: string;
  messageId: string;
  deletedBy: string;
}

export interface ChatMuteUpdatePayload {
  clubId: string;
  mute: ChatMute | null; // null = unmuted
  userId: string;
}

export interface ChatUnreadsPayload {
  unreads: ChatUnreadCount[];
}

export interface ChatErrorPayload {
  code: string;
  message: string;
}

// ── Event Maps ──

export interface ChatClientToServerEvents {
  chat_send: (payload: ChatSendPayload) => void;
  chat_history: (payload: ChatHistoryPayload) => void;
  chat_delete: (payload: ChatDeletePayload) => void;
  chat_mute: (payload: ChatMutePayload) => void;
  chat_unmute: (payload: ChatUnmutePayload) => void;
  chat_mark_read: (payload: ChatMarkReadPayload) => void;
  chat_get_unreads: (payload: ChatGetUnreadsPayload) => void;
}

export interface ChatServerToClientEvents {
  chat_message: (payload: ChatMessagePayload) => void;
  chat_history_response: (payload: ChatHistoryResponsePayload) => void;
  chat_message_deleted: (payload: ChatMessageDeletedPayload) => void;
  chat_mute_update: (payload: ChatMuteUpdatePayload) => void;
  chat_unreads: (payload: ChatUnreadsPayload) => void;
  chat_error: (payload: ChatErrorPayload) => void;
}
