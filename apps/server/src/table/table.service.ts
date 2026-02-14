import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service.js';
import type { 
  LobbyRoomSummary, 
  TableSnapshotPayload,
  SeatInfo,
  CurrentHandInfo
} from '@cardpilot/shared-types';
import type { HandState } from '../hand/hand-state.js';

@Injectable()
export class TableService {
  private readonly logger = new Logger(TableService.name);

  constructor(private prisma: PrismaService) {}

  async createRoom(params: {
    name: string;
    roomCode: string;
    maxSeats: number;
    smallBlind: number;
    bigBlind: number;
    isPublic: boolean;
    createdById?: string;
  }) {
    return this.prisma.room.create({
      data: {
        name: params.name,
        roomCode: params.roomCode,
        maxSeats: params.maxSeats,
        smallBlind: params.smallBlind,
        bigBlind: params.bigBlind,
        isPublic: params.isPublic,
        createdById: params.createdById,
        status: 'WAITING',
      },
    });
  }

  async getRoom(roomId: string) {
    return this.prisma.room.findUnique({
      where: { id: roomId },
      include: { seats: true },
    });
  }

  async getRoomByCode(roomCode: string) {
    return this.prisma.room.findUnique({
      where: { roomCode: roomCode.toUpperCase() },
      include: { seats: true },
    });
  }

  async getPublicRooms(limit: number = 50): Promise<LobbyRoomSummary[]> {
    const rooms = await this.prisma.room.findMany({
      where: { 
        isPublic: true,
        status: { in: ['WAITING', 'PLAYING'] }
      },
      include: { 
        seats: { where: { status: 'OCCUPIED' } }
      },
      orderBy: { updatedAt: 'desc' },
      take: limit,
    });

    return rooms.map(room => ({
      roomId: room.id,
      roomCode: room.roomCode,
      roomName: room.name,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind,
      maxSeats: room.maxSeats,
      playerCount: room.seats.length,
      status: room.status,
      updatedAt: room.updatedAt.toISOString(),
    }));
  }

  async sitDown(roomId: string, seatIndex: number, userId: string, stack: number) {
    return this.prisma.seat.create({
      data: {
        roomId,
        seatIndex,
        userId,
        stack,
        status: 'OCCUPIED',
      },
    });
  }

  async standUp(roomId: string, seatIndex: number) {
    return this.prisma.seat.deleteMany({
      where: { roomId, seatIndex },
    });
  }

  async updateRoomStatus(roomId: string, status: 'WAITING' | 'PLAYING' | 'PAUSED' | 'CLOSED') {
    return this.prisma.room.update({
      where: { id: roomId },
      data: { status },
    });
  }

  async incrementHandCount(roomId: string) {
    return this.prisma.room.update({
      where: { id: roomId },
      data: { handCount: { increment: 1 } },
    });
  }

  buildTableSnapshot(
    room: {
      id: string;
      roomCode: string;
      name: string;
      status: string;
      maxSeats: number;
      smallBlind: number;
      bigBlind: number;
      seats: Array<{
        seatIndex: number;
        userId: string | null;
        stack: number;
        status: string;
        isFolded: boolean;
        isAllIn: boolean;
        holeCards: string | null;
      }>;
    },
    hand?: HandState | null
  ): TableSnapshotPayload {
    const seats: SeatInfo[] = [];
    
    for (let i = 0; i < room.maxSeats; i++) {
      const seatData = room.seats.find(s => s.seatIndex === i);
      
      let status: 'empty' | 'active' | 'sitting_out' = 'empty';
      if (seatData) {
        status = seatData.status === 'OCCUPIED' 
          ? (seatData.isFolded ? 'sitting_out' : 'active')
          : 'empty';
      }

      // Determine positions
      const isButton = hand ? hand.getButtonSeat() === i : false;
      const isSmallBlind = hand ? this.getSeatRelativeToButton(hand.getButtonSeat(), 1, room.maxSeats) === i : false;
      const isBigBlind = hand ? this.getSeatRelativeToButton(hand.getButtonSeat(), 2, room.maxSeats) === i : false;

      seats.push({
        index: i,
        user: seatData?.userId ? {
          id: seatData.userId,
          nickname: 'Player', // Would fetch from user table
          avatar: undefined,
        } : null,
        stack: seatData?.stack ?? 0,
        status,
        isButton,
        isSmallBlind,
        isBigBlind,
      });
    }

    let currentHand: CurrentHandInfo | null = null;
    if (hand) {
      currentHand = {
        handId: hand.getId(),
        handNumber: hand.getHandNumber(),
        status: this.mapStreetToStatus(hand.getStatus()),
        communityCards: hand.getCommunityCards(),
        pot: hand.getPot(),
        currentBet: hand.getCurrentBet(),
        actorSeat: hand.getActorSeat(),
        timeRemaining: 30, // TODO: implement timer
      };
    }

    return {
      roomId: room.id,
      roomCode: room.roomCode,
      name: room.name,
      status: room.status.toLowerCase() as 'waiting' | 'playing',
      seats,
      currentHand,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind,
    };
  }

  private mapStreetToStatus(street: string): CurrentHandInfo['status'] {
    const mapping: Record<string, CurrentHandInfo['status']> = {
      'PREFLOP': 'preflop',
      'FLOP': 'flop',
      'TURN': 'turn',
      'RIVER': 'river',
      'SHOWDOWN': 'showdown',
    };
    return mapping[street] || 'preflop';
  }

  private getSeatRelativeToButton(buttonSeat: number, offset: number, maxSeats: number): number {
    // Simplified: assume seats are numbered 0 to maxSeats-1
    // In reality, you'd need active seats
    return (buttonSeat + offset) % maxSeats;
  }

  generateRoomCode(length: number = 6): string {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let code = '';
    for (let i = 0; i < length; i++) {
      code += chars[Math.floor(Math.random() * chars.length)];
    }
    return code;
  }
}
