import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { HandState } from './hand-state.js';
import type { Card } from '@cardpilot/poker-evaluator';
import type { PlayerActionType } from '@cardpilot/shared-types';

@Injectable()
export class HandService {
  private readonly logger = new Logger(HandService.name);
  private activeHands: Map<string, HandState> = new Map();

  constructor(private prisma: PrismaService) {}

  createHand(params: {
    roomId: string;
    handNumber: number;
    smallBlind: number;
    bigBlind: number;
    maxSeats: number;
    buttonSeat: number;
    players: Array<{
      seatIndex: number;
      userId: string;
      nickname: string;
      stack: number;
    }>;
  }): HandState {
    const hand = new HandState({
      roomId: params.roomId,
      handNumber: params.handNumber,
      smallBlind: params.smallBlind,
      bigBlind: params.bigBlind,
      maxSeats: params.maxSeats,
    });

    // Add players
    for (const player of params.players) {
      hand.addPlayer(
        player.seatIndex,
        player.userId,
        player.nickname,
        player.stack
      );
    }

    // Start the hand
    hand.startHand(params.buttonSeat);

    // Store in active hands
    this.activeHands.set(hand.getId(), hand);

    return hand;
  }

  getHand(handId: string): HandState | undefined {
    return this.activeHands.get(handId);
  }

  applyAction(
    handId: string,
    seatIndex: number,
    action: PlayerActionType,
    amount?: number
  ): ReturnType<HandState['applyAction']> & { handId: string } {
    const hand = this.activeHands.get(handId);
    if (!hand) {
      return { 
        success: false, 
        error: 'Hand not found', 
        handId 
      };
    }

    const result = hand.applyAction(seatIndex, action, amount);
    
    // If hand ended, persist results and remove from active
    if (result.handEnded) {
      this.persistHandResult(hand);
      this.activeHands.delete(handId);
    }

    return { ...result, handId };
  }

  private async persistHandResult(hand: HandState): Promise<void> {
    try {
      // Persist hand results to database
      // This would save the hand history, results, etc.
      this.logger.log(`Hand ${hand.getId()} ended, pot: ${hand.getPot()}`);
    } catch (error) {
      this.logger.error('Failed to persist hand result:', error);
    }
  }

  getHandForSeat(handId: string, seatIndex: number): {
    handId: string;
    holeCards: [Card, Card] | null;
    position: string;
    canAct: boolean;
  } | null {
    const hand = this.activeHands.get(handId);
    if (!hand) return null;

    return {
      handId: hand.getId(),
      holeCards: hand.getHoleCards(seatIndex),
      position: hand.getPosition(seatIndex),
      canAct: hand.getActorSeat() === seatIndex,
    };
  }

  getSpotInfo(handId: string, seatIndex: number): ReturnType<HandState['getSpotInfo']> | null {
    const hand = this.activeHands.get(handId);
    if (!hand) return null;
    return hand.getSpotInfo(seatIndex);
  }

  cleanup(): void {
    // Clean up old hands
    const now = Date.now();
    // In a real implementation, track hand start times and remove old ones
  }
}
