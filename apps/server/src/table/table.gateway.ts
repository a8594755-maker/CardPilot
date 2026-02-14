import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  MessageBody,
  ConnectedSocket,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger, UseGuards } from '@nestjs/common';
import { TableService } from './table.service.js';
import { HandService } from '../hand/hand.service.js';
import { AdviceService } from '../advice/advice.service.js';
import { PrismaService } from '../prisma/prisma.service.js';
import type {
  ClientToServerEvents,
  ServerToClientEvents,
  CreateRoomPayload,
  JoinRoomCodePayload,
  JoinTablePayload,
  SitDownPayload,
  PlayerActionPayload,
  RoomCreatedPayload,
  RoomJoinedPayload,
  TableSnapshotPayload,
  AdvicePayload,
} from '@cardpilot/shared-types';

// Socket with typed events
interface TypedSocket extends Socket {
  data: {
    userId: string;
    nickname: string;
    currentRoomId?: string;
    currentSeatIndex?: number;
  };
}

@WebSocketGateway({
  namespace: '/poker',
  cors: { origin: '*' },
})
export class TableGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server: Server<ClientToServerEvents, ServerToClientEvents>;

  private readonly logger = new Logger(TableGateway.name);
  private roomHands: Map<string, string> = new Map(); // roomId -> handId

  constructor(
    private tableService: TableService,
    private handService: HandService,
    private adviceService: AdviceService,
    private prisma: PrismaService,
  ) {}

  async handleConnection(client: TypedSocket) {
    // In production, validate JWT token here
    const userId = client.handshake.auth.userId || `guest_${Date.now()}`;
    const nickname = client.handshake.auth.nickname || 'Guest';
    
    client.data.userId = userId;
    client.data.nickname = nickname;

    this.logger.log(`Client connected: ${client.id}, user: ${userId}`);

    client.emit('connection:established', {
      socketId: client.id,
      userId,
      nickname,
    });

    // Send lobby snapshot
    const rooms = await this.tableService.getPublicRooms();
    client.emit('lobby:snapshot', { rooms });
  }

  handleDisconnect(client: TypedSocket) {
    this.logger.log(`Client disconnected: ${client.id}`);
    
    // Clean up if player was seated
    if (client.data.currentRoomId && client.data.currentSeatIndex !== undefined) {
      this.handleStandUp(client, {
        seatIndex: client.data.currentSeatIndex,
      });
    }
  }

  @SubscribeMessage('room:create')
  async handleCreateRoom(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: CreateRoomPayload,
  ): Promise<RoomCreatedPayload> {
    const roomCode = this.tableService.generateRoomCode();
    const name = payload.roomName?.trim() || `Room ${roomCode}`;

    const room = await this.tableService.createRoom({
      name,
      roomCode,
      maxSeats: payload.maxSeats || 6,
      smallBlind: payload.smallBlind || 1,
      bigBlind: payload.bigBlind || 2,
      isPublic: payload.isPublic ?? true,
      createdById: client.data.userId,
    });

    client.join(room.id);
    client.data.currentRoomId = room.id;

    const result: RoomCreatedPayload = {
      roomId: room.id,
      roomCode: room.roomCode,
      roomName: room.name,
    };

    client.emit('room:created', result);
    
    // Broadcast lobby update
    this.broadcastLobbyUpdate();

    return result;
  }

  @SubscribeMessage('room:join_code')
  async handleJoinRoomCode(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: JoinRoomCodePayload,
  ): Promise<RoomJoinedPayload | { error: string }> {
    const room = await this.tableService.getRoomByCode(payload.roomCode);
    
    if (!room) {
      return { error: 'Room not found' };
    }

    if (room.status === 'CLOSED') {
      return { error: 'Room is closed' };
    }

    client.join(room.id);
    client.data.currentRoomId = room.id;

    const result: RoomJoinedPayload = {
      roomId: room.id,
      roomCode: room.roomCode,
      roomName: room.name,
    };

    client.emit('room:joined', result);
    
    // Send table snapshot
    const handId = this.roomHands.get(room.id);
    const hand = handId ? this.handService.getHand(handId) : null;
    const snapshot = this.tableService.buildTableSnapshot(room, hand);
    client.emit('table:snapshot', snapshot);

    return result;
  }

  @SubscribeMessage('table:join')
  async handleJoinTable(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: JoinTablePayload,
  ) {
    const room = await this.tableService.getRoom(payload.roomId);
    
    if (!room) {
      client.emit('error', { code: 'ROOM_NOT_FOUND', message: 'Room not found' });
      return;
    }

    client.join(room.id);
    client.data.currentRoomId = room.id;

    const result: RoomJoinedPayload = {
      roomId: room.id,
      roomCode: room.roomCode,
      roomName: room.name,
    };

    client.emit('room:joined', result);

    // Send table snapshot
    const handId = this.roomHands.get(room.id);
    const hand = handId ? this.handService.getHand(handId) : null;
    const snapshot = this.tableService.buildTableSnapshot(room, hand);
    client.emit('table:snapshot', snapshot);
  }

  @SubscribeMessage('seat:sit')
  async handleSitDown(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: SitDownPayload,
  ) {
    const roomId = client.data.currentRoomId;
    if (!roomId) {
      client.emit('error', { code: 'NOT_IN_ROOM', message: 'Not in a room' });
      return;
    }

    try {
      await this.tableService.sitDown(
        roomId,
        payload.seatIndex,
        client.data.userId,
        payload.buyIn,
      );

      client.data.currentSeatIndex = payload.seatIndex;

      // Notify room
      this.server.to(roomId).emit('player:joined', {
        seatIndex: payload.seatIndex,
        nickname: client.data.nickname,
      });

      // Update snapshot
      await this.broadcastSnapshot(roomId);

    } catch (error) {
      client.emit('error', { 
        code: 'SIT_DOWN_FAILED', 
        message: (error as Error).message 
      });
    }
  }

  @SubscribeMessage('seat:stand')
  async handleStandUp(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: { seatIndex: number },
  ) {
    const roomId = client.data.currentRoomId;
    if (!roomId) return;

    await this.tableService.standUp(roomId, payload.seatIndex);

    if (client.data.currentSeatIndex === payload.seatIndex) {
      client.data.currentSeatIndex = undefined;
    }

    this.server.to(roomId).emit('player:left', {
      seatIndex: payload.seatIndex,
    });

    await this.broadcastSnapshot(roomId);
  }

  @SubscribeMessage('hand:start')
  async handleStartHand(
    @ConnectedSocket() client: TypedSocket,
  ) {
    const roomId = client.data.currentRoomId;
    if (!roomId) {
      client.emit('error', { code: 'NOT_IN_ROOM', message: 'Not in a room' });
      return;
    }

    const room = await this.tableService.getRoom(roomId);
    if (!room) return;

    // Get seated players
    const activeSeats = room.seats.filter(s => s.status === 'OCCUPIED');
    if (activeSeats.length < 2) {
      client.emit('error', { 
        code: 'NOT_ENOUGH_PLAYERS', 
        message: 'Need at least 2 players to start' 
      });
      return;
    }

    // Increment hand count
    await this.tableService.incrementHandCount(roomId);
    const handNumber = room.handCount + 1;

    // Create hand
    const hand = this.handService.createHand({
      roomId,
      handNumber,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind,
      maxSeats: room.maxSeats,
      buttonSeat: 0, // Would rotate based on previous hand
      players: activeSeats.map(s => ({
        seatIndex: s.seatIndex,
        userId: s.userId!,
        nickname: 'Player', // Would fetch from user
        stack: s.stack,
      })),
    });

    this.roomHands.set(roomId, hand.getId());

    // Update room status
    await this.tableService.updateRoomStatus(roomId, 'PLAYING');

    // Deal cards to each player
    for (const seat of activeSeats) {
      const handInfo = this.handService.getHandForSeat(hand.getId(), seat.seatIndex);
      if (handInfo?.holeCards) {
        // Send private hole cards
        this.server.to(roomId).emit('hand:deal', {
          handId: hand.getId(),
          holeCards: handInfo.holeCards,
          position: handInfo.position as any,
        });
      }
    }

    // Broadcast snapshot
    await this.broadcastSnapshot(roomId);

    // Push advice to first actor
    this.pushAdviceToActor(roomId, hand);
  }

  @SubscribeMessage('hand:action')
  async handlePlayerAction(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: PlayerActionPayload,
  ) {
    const roomId = client.data.currentRoomId;
    if (!roomId) {
      client.emit('error', { code: 'NOT_IN_ROOM', message: 'Not in a room' });
      return;
    }

    const seatIndex = client.data.currentSeatIndex;
    if (seatIndex === undefined) {
      client.emit('error', { code: 'NOT_SEATED', message: 'Not seated at table' });
      return;
    }

    const handId = this.roomHands.get(roomId);
    if (!handId) {
      client.emit('error', { code: 'NO_ACTIVE_HAND', message: 'No active hand' });
      return;
    }

    const result = this.handService.applyAction(
      handId,
      seatIndex,
      payload.action,
      payload.amount,
    );

    if (!result.success) {
      client.emit('error', { 
        code: 'ACTION_FAILED', 
        message: result.error || 'Action failed' 
      });
      return;
    }

    // Broadcast action
    const hand = this.handService.getHand(handId);
    this.server.to(roomId).emit('hand:action_applied', {
      handId,
      seatIndex,
      action: payload.action,
      amount: payload.amount,
      potAfter: hand?.getPot() || 0,
      nextActor: hand?.getActorSeat() || undefined,
      streetEnds: result.streetAdvanced,
    });

    // Handle street advancement
    if (result.streetAdvanced && hand) {
      this.server.to(roomId).emit('hand:street_advanced', {
        handId,
        newStreet: this.mapStreet(hand.getStatus()),
        communityCards: hand.getCommunityCards(),
        pot: hand.getPot(),
        nextActor: hand.getActorSeat()!,
      });
    }

    // Handle hand end
    if (result.handEnded && hand) {
      this.server.to(roomId).emit('hand:ended', {
        handId,
        winners: [], // Would calculate winners
        showdown: hand.getStatus() === 'SHOWDOWN',
        communityCards: hand.getCommunityCards(),
        pot: hand.getPot(),
      });

      this.roomHands.delete(roomId);
      await this.tableService.updateRoomStatus(roomId, 'WAITING');
    }

    // Update snapshot and push advice to next actor
    await this.broadcastSnapshot(roomId);
    
    if (hand && !result.handEnded) {
      this.pushAdviceToActor(roomId, hand);
    }
  }

  @SubscribeMessage('advice:request')
  async handleAdviceRequest(
    @ConnectedSocket() client: TypedSocket,
    @MessageBody() payload: { handId: string },
  ) {
    const roomId = client.data.currentRoomId;
    const seatIndex = client.data.currentSeatIndex;
    
    if (!roomId || seatIndex === undefined) return;

    const hand = this.handService.getHand(payload.handId);
    if (!hand) return;

    const spotInfo = this.handService.getSpotInfo(payload.handId, seatIndex);
    if (!spotInfo) return;

    const holeCards = hand.getHoleCards(seatIndex);
    if (!holeCards) return;

    const advice = this.adviceService.getAdvice({
      handId: payload.handId,
      heroHand: holeCards,
      heroPosition: spotInfo.position,
      vsPosition: spotInfo.vsPosition,
      effectiveStack: spotInfo.effectiveStack,
      potSize: spotInfo.potSize,
      toCall: spotInfo.toCall,
      actionHistory: spotInfo.actionHistory,
      isUnopened: spotInfo.isUnopened,
    });

    client.emit('advice:recommendation', advice);
  }

  @SubscribeMessage('lobby:refresh')
  async handleLobbyRefresh(
    @ConnectedSocket() client: TypedSocket,
  ) {
    const rooms = await this.tableService.getPublicRooms();
    client.emit('lobby:snapshot', { rooms });
  }

  private async broadcastSnapshot(roomId: string) {
    const room = await this.tableService.getRoom(roomId);
    if (!room) return;

    const handId = this.roomHands.get(roomId);
    const hand = handId ? this.handService.getHand(handId) : null;
    const snapshot = this.tableService.buildTableSnapshot(room, hand);

    this.server.to(roomId).emit('table:snapshot', snapshot);
  }

  private async broadcastLobbyUpdate() {
    const rooms = await this.tableService.getPublicRooms();
    this.server.emit('lobby:snapshot', { rooms });
  }

  private pushAdviceToActor(roomId: string, hand: any) {
    const actorSeat = hand.getActorSeat();
    if (actorSeat === null) return;

    const spotInfo = hand.getSpotInfo(actorSeat);
    const holeCards = hand.getHoleCards(actorSeat);
    
    if (!spotInfo || !holeCards) return;

    const advice = this.adviceService.getAdvice({
      handId: hand.getId(),
      heroHand: holeCards,
      heroPosition: spotInfo.position,
      vsPosition: spotInfo.vsPosition,
      effectiveStack: spotInfo.effectiveStack,
      potSize: spotInfo.potSize,
      toCall: spotInfo.toCall,
      actionHistory: spotInfo.actionHistory,
      isUnopened: spotInfo.isUnopened,
    });

    // Find socket for this seat and send advice
    // In a real implementation, track socket -> seat mapping
    this.server.to(roomId).emit('advice:recommendation', advice);
  }

  private mapStreet(street: string): 'flop' | 'turn' | 'river' | 'showdown' {
    const mapping: Record<string, 'flop' | 'turn' | 'river' | 'showdown'> = {
      'FLOP': 'flop',
      'TURN': 'turn',
      'RIVER': 'river',
      'SHOWDOWN': 'showdown',
    };
    return mapping[street] || 'flop';
  }
}
