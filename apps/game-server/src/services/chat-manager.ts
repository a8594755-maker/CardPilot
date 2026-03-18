/**
 * Chat Manager — Business logic layer for the club chat system.
 *
 * Provides:
 * - Rate limiting (in-memory, per user per club)
 * - Content validation and profanity filtering
 * - send / history / delete / mute / unmute / markRead / getUnreads
 *
 * All persistence is delegated to the injected ChatRepo instance.
 */

import type { ChatRepo } from './chat-repo';
import type { ChatMessage, ChatMute, ChatUnreadCount } from '@cardpilot/shared-types';
import { logInfo, logWarn } from '../logger';

// ── Rate-limit window config ────────────────────────────────────────

const RATE_LIMIT_WINDOW_MS = 10_000; // 10 seconds
const RATE_LIMIT_MAX_MESSAGES = 10;

// ── Profanity word list (placeholder) ───────────────────────────────

const PROFANITY_LIST: string[] = ['fuck', 'shit', 'ass', 'damn', 'bitch'];

// ── Types ───────────────────────────────────────────────────────────

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

export interface SendMessageOpts {
  clubId: string;
  tableId?: string;
  senderUserId: string;
  senderDisplayName: string;
  content: string;
  mentions?: string[];
  chatEnabled?: boolean;
  profanityFilterEnabled?: boolean;
}

export type SendMessageResult = { message: ChatMessage } | { error: string };

// ── ChatManager ─────────────────────────────────────────────────────

export class ChatManager {
  private readonly repo: ChatRepo;
  private readonly rateLimits: Map<string, RateLimitEntry> = new Map();

  constructor(repo: ChatRepo) {
    this.repo = repo;
  }

  // ═══════════════ RATE LIMITING ═══════════════

  /**
   * Returns true if the user is within the rate limit for this club.
   * Sliding-window counter: max RATE_LIMIT_MAX_MESSAGES messages per
   * RATE_LIMIT_WINDOW_MS window.
   */
  private checkRateLimit(clubId: string, userId: string): boolean {
    const key = `${clubId}:${userId}`;
    const now = Date.now();
    const entry = this.rateLimits.get(key);

    if (!entry || now - entry.windowStart >= RATE_LIMIT_WINDOW_MS) {
      // Start a fresh window
      this.rateLimits.set(key, { count: 1, windowStart: now });
      return true;
    }

    if (entry.count >= RATE_LIMIT_MAX_MESSAGES) {
      return false;
    }

    entry.count += 1;
    return true;
  }

  // ═══════════════ CONTENT VALIDATION ═══════════════

  private validateContent(content: string): { valid: boolean; reason?: string } {
    const trimmed = content.trim();

    if (trimmed.length === 0) {
      return { valid: false, reason: 'Message content must not be empty' };
    }

    if (trimmed.length > 2000) {
      return { valid: false, reason: 'Message content must not exceed 2000 characters' };
    }

    return { valid: true };
  }

  // ═══════════════ PROFANITY FILTER ═══════════════

  private filterProfanity(content: string, enabled: boolean): string {
    if (!enabled) return content;

    let filtered = content;
    for (const word of PROFANITY_LIST) {
      const regex = new RegExp(word, 'gi');
      filtered = filtered.replace(regex, '***');
    }
    return filtered;
  }

  // ═══════════════ PUBLIC METHODS ═══════════════

  async sendMessage(opts: SendMessageOpts): Promise<SendMessageResult> {
    const {
      clubId,
      tableId,
      senderUserId,
      senderDisplayName,
      content,
      mentions,
      chatEnabled = true,
      profanityFilterEnabled = false,
    } = opts;

    // 1. Check if chat is enabled
    if (!chatEnabled) {
      return { error: 'Chat is currently disabled' };
    }

    // 2. Validate content
    const validation = this.validateContent(content);
    if (!validation.valid) {
      return { error: validation.reason! };
    }

    // 3. Check rate limit
    if (!this.checkRateLimit(clubId, senderUserId)) {
      logWarn({
        event: 'chat.rate_limit',
        message: `User ${senderUserId} exceeded rate limit in club ${clubId}`,
        userId: senderUserId,
      });
      return { error: 'You are sending messages too quickly. Please wait a moment.' };
    }

    // 4. Check if user is muted
    const muted = await this.repo.isMuted(clubId, senderUserId);
    if (muted) {
      return { error: 'You are muted in this club' };
    }

    // 5. Apply profanity filter
    const filteredContent = this.filterProfanity(content.trim(), profanityFilterEnabled);

    // 6. Persist message via repo
    const message = await this.repo.sendMessage({
      clubId,
      tableId: tableId ?? null,
      senderUserId,
      senderDisplayName,
      messageType: 'text',
      content: filteredContent,
      mentions: mentions ?? [],
    });

    if (!message) {
      return { error: 'Failed to persist message (offline mode)' };
    }

    logInfo({
      event: 'chat.message_sent',
      message: `Message sent by ${senderUserId} in club ${clubId}`,
      userId: senderUserId,
    });

    return { message };
  }

  async getHistory(
    clubId: string,
    tableId?: string,
    before?: string,
    limit?: number,
  ): Promise<{ messages: ChatMessage[]; hasMore: boolean }> {
    return this.repo.getHistory(clubId, tableId, before, limit);
  }

  async deleteMessage(messageId: string, deletedBy: string): Promise<void> {
    return this.repo.deleteMessage(messageId, deletedBy);
  }

  async muteUser(
    clubId: string,
    userId: string,
    mutedBy: string,
    reason?: string,
    durationMinutes?: number,
  ): Promise<ChatMute | null> {
    return this.repo.muteUser(clubId, userId, mutedBy, reason, durationMinutes);
  }

  async unmuteUser(clubId: string, userId: string): Promise<void> {
    return this.repo.unmuteUser(clubId, userId);
  }

  async isMuted(clubId: string, userId: string): Promise<ChatMute | null> {
    return this.repo.isMuted(clubId, userId);
  }

  async markRead(
    clubId: string,
    userId: string,
    tableId: string | undefined,
    lastReadMessageId: string,
  ): Promise<void> {
    const scopeKey = tableId ? `table:${tableId}` : 'club';
    return this.repo.markRead(clubId, userId, scopeKey, lastReadMessageId);
  }

  async getUnreads(clubId: string, userId: string): Promise<ChatUnreadCount[]> {
    return this.repo.getUnreads(clubId, userId);
  }
}
