import { io, Socket } from 'socket.io-client';

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io('/gto', { transports: ['websocket', 'polling'] });
  }
  return socket;
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}

export interface SolveProgress {
  jobId: string;
  completedFlops: number;
  totalFlops: number;
  currentIteration: number;
  totalIterations: number;
  infoSets: number;
  memoryMB: number;
  elapsed: number;
  exploitability: number;
  speed: number; // iterations per second
  eta: number; // estimated remaining seconds
}

export interface SolveComplete {
  jobId: string;
  totalFlops: number;
  totalInfoSets: number;
  elapsed: number;
}

export interface SolveError {
  jobId: string;
  error: string;
}
