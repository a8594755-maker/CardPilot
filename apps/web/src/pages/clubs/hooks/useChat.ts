import { useState, useEffect, useCallback, useRef } from "react";
import type { Socket } from "socket.io-client";
import type {
  ChatMessage,
  ChatUnreadCount,
  ChatMute,
  ChatHistoryResponsePayload,
  ChatMessagePayload,
  ChatMessageDeletedPayload,
  ChatMuteUpdatePayload,
  ChatUnreadsPayload,
  ChatErrorPayload,
} from "@cardpilot/shared-types";

export interface ChatActions {
  sendMessage: (content: string, mentions?: string[], tableId?: string) => void;
  loadHistory: (tableId?: string, before?: string) => void;
  deleteMessage: (messageId: string) => void;
  muteUser: (userId: string, reason?: string, durationMinutes?: number) => void;
  unmuteUser: (userId: string) => void;
  markRead: (lastReadMessageId: string, tableId?: string) => void;
  refreshUnreads: () => void;
}

export interface ChatState {
  messages: ChatMessage[];
  hasMore: boolean;
  unreads: ChatUnreadCount[];
  myMute: ChatMute | null;
  loading: boolean;
}

export function useChat(
  socket: Socket | null,
  clubId: string,
  userId: string,
): { actions: ChatActions; state: ChatState } {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [unreads, setUnreads] = useState<ChatUnreadCount[]>([]);
  const [myMute, setMyMute] = useState<ChatMute | null>(null);
  const [loading, setLoading] = useState(false);

  // Track current clubId to reset on change
  const clubIdRef = useRef(clubId);
  useEffect(() => {
    if (clubIdRef.current !== clubId) {
      clubIdRef.current = clubId;
      setMessages([]);
      setHasMore(false);
      setUnreads([]);
      setMyMute(null);
    }
  }, [clubId]);

  // Socket listeners
  useEffect(() => {
    if (!socket) return;

    const onMessage = (payload: ChatMessagePayload) => {
      if (payload.message.clubId !== clubId) return;
      setMessages((prev) => {
        // Deduplicate by id
        if (prev.some((m) => m.id === payload.message.id)) return prev;
        return [payload.message, ...prev];
      });
    };

    const onHistoryResponse = (payload: ChatHistoryResponsePayload) => {
      if (payload.clubId !== clubId) return;
      setLoading(false);
      setHasMore(payload.hasMore);
      setMessages((prev) => {
        const existingIds = new Set(prev.map((m) => m.id));
        const newMsgs = payload.messages.filter((m) => !existingIds.has(m.id));
        return [...prev, ...newMsgs];
      });
    };

    const onDeleted = (payload: ChatMessageDeletedPayload) => {
      if (payload.clubId !== clubId) return;
      setMessages((prev) => prev.filter((m) => m.id !== payload.messageId));
    };

    const onMuteUpdate = (payload: ChatMuteUpdatePayload) => {
      if (payload.clubId !== clubId) return;
      if (payload.userId === userId) {
        setMyMute(payload.mute);
      }
    };

    const onUnreads = (payload: ChatUnreadsPayload) => {
      setUnreads(payload.unreads);
    };

    const onError = (payload: ChatErrorPayload) => {
      setLoading(false);
      console.warn("[chat] error:", payload.code, payload.message);
    };

    socket.on("chat_message", onMessage);
    socket.on("chat_history_response", onHistoryResponse);
    socket.on("chat_message_deleted", onDeleted);
    socket.on("chat_mute_update", onMuteUpdate);
    socket.on("chat_unreads", onUnreads);
    socket.on("chat_error", onError);

    return () => {
      socket.off("chat_message", onMessage);
      socket.off("chat_history_response", onHistoryResponse);
      socket.off("chat_message_deleted", onDeleted);
      socket.off("chat_mute_update", onMuteUpdate);
      socket.off("chat_unreads", onUnreads);
      socket.off("chat_error", onError);
    };
  }, [socket, clubId, userId]);

  // Actions
  const sendMessage = useCallback(
    (content: string, mentions?: string[], tableId?: string) => {
      socket?.emit("chat_send", { clubId, content, mentions, tableId });
    },
    [socket, clubId],
  );

  const loadHistory = useCallback(
    (tableId?: string, before?: string) => {
      setLoading(true);
      socket?.emit("chat_history", { clubId, tableId, before, limit: 50 });
    },
    [socket, clubId],
  );

  const deleteMessage = useCallback(
    (messageId: string) => {
      socket?.emit("chat_delete", { clubId, messageId });
    },
    [socket, clubId],
  );

  const muteUser = useCallback(
    (targetUserId: string, reason?: string, durationMinutes?: number) => {
      socket?.emit("chat_mute", { clubId, userId: targetUserId, reason, durationMinutes });
    },
    [socket, clubId],
  );

  const unmuteUser = useCallback(
    (targetUserId: string) => {
      socket?.emit("chat_unmute", { clubId, userId: targetUserId });
    },
    [socket, clubId],
  );

  const markRead = useCallback(
    (lastReadMessageId: string, tableId?: string) => {
      socket?.emit("chat_mark_read", { clubId, lastReadMessageId, tableId });
    },
    [socket, clubId],
  );

  const refreshUnreads = useCallback(() => {
    socket?.emit("chat_get_unreads", { clubId });
  }, [socket, clubId]);

  return {
    actions: { sendMessage, loadHistory, deleteMessage, muteUser, unmuteUser, markRead, refreshUnreads },
    state: { messages, hasMore, unreads, myMute, loading },
  };
}
