import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import type { LobbyRoomSummary } from '@cardpilot/shared-types';
import { useSocket } from './SocketContext';

interface RoomContextType {
  lobbyRooms: LobbyRoomSummary[];
  tableId: string | null;
  setTableId: (id: string | null) => void;
  currentRoomCode: string;
  currentRoomName: string;
}

const RoomContext = createContext<RoomContextType | null>(null);

export function useRoom() {
  const context = useContext(RoomContext);
  if (!context) {
    throw new Error('useRoom must be used within a RoomProvider');
  }
  return context;
}

export function RoomProvider({ children }: { children: ReactNode }) {
  const { socket } = useSocket();
  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoomSummary[]>([]);
  const [tableId, setTableId] = useState<string | null>(null);
  const [currentRoomCode, setCurrentRoomCode] = useState('');
  const [currentRoomName, setCurrentRoomName] = useState('');

  useEffect(() => {
    if (!socket) return;

    const onLobbySnapshot = (d: { rooms: LobbyRoomSummary[] }) => {
      setLobbyRooms(d.rooms ?? []);
    };

    const onRoomJoined = (d: { tableId: string; roomCode: string; roomName: string }) => {
      if (d.tableId?.startsWith('fb_')) return; // Ignore fast battle
      setTableId(d.tableId);
      setCurrentRoomCode(d.roomCode);
      setCurrentRoomName(d.roomName);
    };

    const onRoomCreated = (d: { tableId: string; roomCode: string; roomName: string }) => {
      setTableId(d.tableId);
      setCurrentRoomCode(d.roomCode);
      setCurrentRoomName(d.roomName);
    };

    const onLeftTable = (d: { tableId: string }) => {
      if (tableId && d.tableId === tableId) {
        setTableId(null);
        setCurrentRoomCode('');
        setCurrentRoomName('');
      }
    };

    socket.on('lobby_snapshot', onLobbySnapshot);
    socket.on('room_joined', onRoomJoined);
    socket.on('room_created', onRoomCreated);
    socket.on('left_table', onLeftTable);

    // Initial request
    socket.emit('request_lobby');

    return () => {
      socket.off('lobby_snapshot', onLobbySnapshot);
      socket.off('room_joined', onRoomJoined);
      socket.off('room_created', onRoomCreated);
      socket.off('left_table', onLeftTable);
    };
  }, [socket, tableId]);

  return (
    <RoomContext.Provider
      value={{
        lobbyRooms,
        tableId,
        setTableId,
        currentRoomCode,
        currentRoomName,
      }}
    >
      {children}
    </RoomContext.Provider>
  );
}
