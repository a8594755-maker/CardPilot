import { useEffect, useRef, useState, useCallback } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { 
  ClientToServerEvents, 
  ServerToClientEvents,
  TableState,
  AdvicePayload,
  LobbyRoomSummary
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
  tableSnapshot: TableState | null;
  advice: AdvicePayload | null;
  lobbyRooms: LobbyRoomSummary[];
  holeCards: [string, string] | null;
  currentRoom: { tableId: string; roomCode: string; roomName: string } | null;
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
  const [tableSnapshot, setTableSnapshot] = useState<TableState | null>(null);
  const [advice, setAdvice] = useState<AdvicePayload | null>(null);
  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [holeCards, setHoleCards] = useState<[string, string] | null>(null);
  const [currentRoom, setCurrentRoom] = useState<{ tableId: string; roomCode: string; roomName: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const socket: TypedSocket = io(serverUrl, {
      auth: { userId, displayName: nickname },
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      setIsConnected(true);
      setError(null);
    });

    socket.on('disconnect', () => {
      setIsConnected(false);
    });

    socket.on('connected', () => {});

    socket.on('table_snapshot', (snapshot) => {
      setTableSnapshot(snapshot);
    });

    socket.on('hole_cards', (data) => {
      if (Array.isArray(data.cards) && data.cards.length === 2) {
        setHoleCards([data.cards[0], data.cards[1]]);
      }
    });

    socket.on('advice_payload', (adviceData) => {
      setAdvice(adviceData);
    });

    socket.on('lobby_snapshot', (data) => {
      setLobbyRooms(data.rooms);
    });

    socket.on('room_joined', (room) => {
      setCurrentRoom(room);
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('left_table', () => {
      setCurrentRoom(null);
      setTableSnapshot(null);
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('room_closed', () => {
      setCurrentRoom(null);
      setTableSnapshot(null);
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('hand_ended', () => {
      setHoleCards(null);
      setAdvice(null);
    });

    socket.on('error_event', (err) => {
      setError(err.message);
    });

    return () => {
      socket.disconnect();
    };
  }, [serverUrl, userId, nickname]);

  const joinRoom = useCallback((roomCode: string) => {
    socketRef.current?.emit('join_room_code', { roomCode });
  }, []);

  const createRoom = useCallback((name: string) => {
    socketRef.current?.emit('create_room', { 
      roomName: name,
      maxPlayers: 6,
      smallBlind: 1,
      bigBlind: 2,
      isPublic: true,
    });
  }, []);

  const sitDown = useCallback((seatIndex: number, buyIn: number) => {
    if (!currentRoom) return;
    socketRef.current?.emit('sit_down', { tableId: currentRoom.tableId, seat: seatIndex, buyIn });
  }, [currentRoom]);

  const standUp = useCallback((seatIndex: number) => {
    if (!currentRoom) return;
    socketRef.current?.emit('stand_up', { tableId: currentRoom.tableId, seat: seatIndex });
  }, [currentRoom]);

  const startHand = useCallback(() => {
    if (!currentRoom) return;
    socketRef.current?.emit('start_hand', { tableId: currentRoom.tableId });
  }, [currentRoom]);

  const submitAction = useCallback((action: 'fold' | 'check' | 'call' | 'raise' | 'all_in', amount?: number) => {
    const handId = tableSnapshot?.handId;
    if (!handId || !currentRoom) return;

    socketRef.current?.emit('action_submit', {
      tableId: currentRoom.tableId,
      handId,
      action,
      amount,
    });
  }, [currentRoom, tableSnapshot]);

  const refreshLobby = useCallback(() => {
    socketRef.current?.emit('request_lobby');
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
