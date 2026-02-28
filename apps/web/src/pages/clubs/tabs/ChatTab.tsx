import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, ClubMember } from "@cardpilot/shared-types";
import type { ChatActions, ChatState } from "../hooks/useChat";
import type { ClubPermissions } from "../hooks/useClubPermissions";
import { EmptyState } from "../shared";

interface ChatTabProps {
  chatActions: ChatActions;
  chatState: ChatState;
  permissions: ClubPermissions;
  members: ClubMember[];
  currentUserId: string;
  currentDisplayName: string;
}

export const ChatTab = memo(function ChatTab({
  chatActions,
  chatState,
  permissions,
  members,
  currentUserId,
  currentDisplayName,
}: ChatTabProps) {
  const [input, setInput] = useState("");
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [selectedMentions, setSelectedMentions] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load initial history
  useEffect(() => {
    chatActions.loadHistory();
  }, [chatActions]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatState.messages.length]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    chatActions.sendMessage(trimmed, selectedMentions.length > 0 ? selectedMentions : undefined);
    setInput("");
    setSelectedMentions([]);
    setMentionQuery(null);
  }, [input, selectedMentions, chatActions]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setInput(value);

      // Detect @mention
      const atIndex = value.lastIndexOf("@");
      if (atIndex >= 0 && atIndex === value.length - 1) {
        setMentionQuery("");
      } else if (atIndex >= 0) {
        const query = value.slice(atIndex + 1);
        if (!query.includes(" ")) {
          setMentionQuery(query);
        } else {
          setMentionQuery(null);
        }
      } else {
        setMentionQuery(null);
      }
    },
    [],
  );

  const handleMentionSelect = useCallback(
    (member: ClubMember) => {
      const name = member.displayName ?? member.userId.slice(0, 8);
      const atIndex = input.lastIndexOf("@");
      const before = input.slice(0, atIndex);
      setInput(`${before}@${name} `);
      setSelectedMentions((prev) => [...prev, member.userId]);
      setMentionQuery(null);
      inputRef.current?.focus();
    },
    [input],
  );

  const handleLoadMore = useCallback(() => {
    const oldest = chatState.messages[chatState.messages.length - 1];
    if (oldest) {
      chatActions.loadHistory(undefined, oldest.id);
    }
  }, [chatActions, chatState.messages]);

  // Filtered members for mention autocomplete
  const mentionCandidates =
    mentionQuery !== null
      ? members
          .filter((m) => m.userId !== currentUserId && m.status === "active")
          .filter((m) => {
            const name = (m.displayName ?? "").toLowerCase();
            return name.includes((mentionQuery ?? "").toLowerCase());
          })
          .slice(0, 5)
      : [];

  const isMuted = chatState.myMute !== null;

  return (
    <div className="flex flex-col h-[500px]">
      {/* Messages area */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto space-y-1 px-2 py-2"
      >
        {/* Load more */}
        {chatState.hasMore && (
          <div className="text-center py-2">
            <button
              onClick={handleLoadMore}
              disabled={chatState.loading}
              className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors disabled:opacity-50"
            >
              {chatState.loading ? "Loading..." : "Load older messages"}
            </button>
          </div>
        )}

        {chatState.messages.length === 0 && !chatState.loading && (
          <EmptyState
            icon="💬"
            title="No messages yet"
            description="Start the conversation!"
          />
        )}

        {/* Messages (reversed since newest first from server) */}
        {[...chatState.messages].reverse().map((msg) => (
          <ChatBubble
            key={msg.id}
            message={msg}
            isOwn={msg.senderUserId === currentUserId}
            canDelete={permissions.isAdmin}
            onDelete={() => chatActions.deleteMessage(msg.id)}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Mention autocomplete dropdown */}
      {mentionCandidates.length > 0 && (
        <div className="mx-2 mb-1 rounded-lg border border-slate-700 bg-slate-800 shadow-lg">
          {mentionCandidates.map((m) => (
            <button
              key={m.userId}
              onClick={() => handleMentionSelect(m)}
              className="w-full px-3 py-1.5 text-left text-xs text-slate-300 hover:bg-slate-700 transition-colors first:rounded-t-lg last:rounded-b-lg"
            >
              @{m.displayName ?? m.userId.slice(0, 8)}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-slate-700 px-2 py-2">
        {isMuted ? (
          <div className="rounded-lg bg-red-900/20 border border-red-800/40 px-3 py-2 text-xs text-red-400 text-center">
            You are muted in this club
            {chatState.myMute?.expiresAt && (
              <span className="block text-[10px] text-red-500 mt-0.5">
                Expires: {new Date(chatState.myMute.expiresAt).toLocaleString()}
              </span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type a message... (@ to mention)"
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500 placeholder:text-slate-600"
              maxLength={2000}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

// ── Chat Bubble ──

const ChatBubble = memo(function ChatBubble({
  message,
  isOwn,
  canDelete,
  onDelete,
}: {
  message: ChatMessage;
  isOwn: boolean;
  canDelete: boolean;
  onDelete: () => void;
}) {
  if (message.messageType === "system") {
    return (
      <div className="text-center py-1">
        <span className="text-[10px] text-slate-500 italic">{message.content}</span>
      </div>
    );
  }

  return (
    <div className={`flex ${isOwn ? "justify-end" : "justify-start"} group`}>
      <div
        className={`max-w-[75%] rounded-xl px-3 py-1.5 ${
          isOwn
            ? "bg-cyan-600/30 border border-cyan-500/20"
            : "bg-slate-800 border border-slate-700"
        }`}
      >
        {!isOwn && (
          <div className="text-[10px] font-medium text-cyan-400 mb-0.5">
            {message.senderDisplayName}
          </div>
        )}
        <div className="text-xs text-slate-200 break-words">{message.content}</div>
        <div className="flex items-center justify-between gap-2 mt-0.5">
          <span className="text-[9px] text-slate-500">
            {new Date(message.createdAt).toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {canDelete && (
            <button
              onClick={onDelete}
              className="text-[9px] text-red-400 opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-300"
            >
              Delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

export default ChatTab;
