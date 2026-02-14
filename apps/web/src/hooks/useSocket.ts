import { useEffect, useRef, useState, useCallback } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { 
  ClientToServerEvents, 
  ServerToClientEvents,
  TableSnapshotPayload,
  AdvicePayload,
  LobbyRoomSummary,
  RoomJoinedPayload
} from '@cardpilot/shared-types';

type TypedSocket = Socket<ServerToClientEvents, ClientToServerEvents>;

interface UseSocketOptions {
  serverUrl: string;
  userId: string;
  nickname: string;
}

interface UseSocketReturn {
  socket: TypedSocket | null;
  isConnected: boolean;
  tableSnapshot: TableSnapshotPayload | null;
  advice: AdvicePayload | null;
  lobbyRooms: LobbyRoomSummary[];
  holeCards: [string, string] | null;
  currentRoom: RoomJoinedPayload | null;
  error: string | null;
  
  // Actions
  joinRoom: (roomCode: string) => void;
  createRoom: (name: string) => void;
  sitDown: (seatIndex: number, buyIn: number) => void;
  standUp: (seatIndex: number) => void;
  startHand: () => void;
  submitAction: (action: 'fold' | 'check' | 'call' | 'raise' | 'all_in', amount?: number) => void;
  refreshLobby: () => void;
}

export function useSocket({ serverUrl, userId, nickname }: UseSocketOptions): UseSocketReturn {
  const socketRef = useRef<TypedSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [tableSnapshot, setTableSnapshot] = useState<TableSnapshotPayload | null>(null);
  const [advice, setAdvice] = useState<AdvicePayload | null>(null);
  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [holeCards, setHoleCards] = useState<[string, string] | null>(null);
  const [currentRoom, setCurrentRoom] = useState<RoomJoinedPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const socket: TypedSocket = io(`${serverUrl}/poker`, {
      auth: { userId, nickname },
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setIsConnected(true);
      setError(null);
    });

    socket.on('disconnect', () => {
      setIsConnected(false);
    });

    socket.on('connection:established', () => {
      // Connection established
    });

    socket.on('table:snapshot', (snapshot) => {
      setTableSnapshot(snapshot);
    });

    socket.on('hand:deal', (data) => {
      setHoleCards(data.holeCards);
    });

    socket.on('advice:recommendation', (adviceData) => {
      setAdvice(adviceData);
    });

    socket.on('lobby:snapshot', (data) => {
      setLobbyRooms(data.rooms);
    });

    socket.on('room:joined', (room) => {
      setCurrentRoom(room);
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('room:left', () => {
      setCurrentRoom(null);
      setTableSnapshot(null);
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('hand:ended', () => {
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('error', (err) => {
      setError(err.message);
    });

    return () => {
      socket.disconnect();
    };
  }, [serverUrl, userId, nickname]);

  const joinRoom = useCallback((roomCode: string) => {
    socketRef.current?.emit('room:join_code', { roomCode });
  }, []);

  const createRoom = useCallback((name: string) => {
    socketRef.current?.emit('room:create', { 
      roomName: name,
      maxSeats: 6,
      smallBlind: 1,
      bigBlind: 2,
      isPublic: true,
    });
  }, []);

  const sitDown = useCallback((seatIndex: number, buyIn: number) => {
    socketRef.current?.emit('seat:sit', { seatIndex, buyIn });
  }, []);

  const standUp = useCallback((seatIndex: number) => {
    socketRef.current?.emit('seat:stand', { seatIndex });
  }, []);

  const startHand = useCallback(() => {
    socketRef.current?.emit('hand:start');
  }, []);

  const submitAction = useCallback((action: 'fold' | 'check' | 'call' | 'raise' | 'all_in', amount?: number) => {
    const handId = tableSnapshot?.currentHand?.handId;
    if (!handId) return;

    socketRef.current?.emit('hand:action', {
      handId,
      action,
      amount,
    });
  }, [tableSnapshot]);

  const refreshLobby = useCallback(() => {
    socketRef.current?.emit('lobby:refresh');
  }, []);

  return {
    socket: socketRef.current,
    isConnected,
    tableSnapshot,
    advice,
    lobbyRooms,
    holeCards,
    currentRoom,
    error,
    joinRoom,
    createRoom,
    sitDown,
    standUp,
    startHand,
    submitAction,
    refreshLobby,
  };
}

export default useSocket;
