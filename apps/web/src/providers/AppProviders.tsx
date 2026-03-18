import { ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { ToastProvider } from '../contexts/ToastContext';
import { AuthProvider } from '../contexts/AuthContext';
import { SocketProvider } from '../contexts/SocketContext';
import { RoomProvider } from '../contexts/RoomContext';
import { GameProvider } from '../contexts/GameContext';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <SocketProvider>
            <RoomProvider>
              <GameProvider>{children}</GameProvider>
            </RoomProvider>
          </SocketProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
