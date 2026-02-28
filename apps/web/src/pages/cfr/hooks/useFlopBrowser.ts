// Flop browser hook — search and filter logic for the sidebar.

import { useState, useMemo } from 'react';
import type { FlopEntry } from '../lib/cfr-api';
import { cardLabel } from '../lib/cfr-constants';

export type TextureFilter = 'all' | 'rainbow' | 'two-tone' | 'monotone';
export type PairingFilter = 'all' | 'unpaired' | 'paired';
export type HighCardFilter = 'all' | 'A' | 'K' | 'Q' | 'J' | 'T-';

export interface FlopBrowserState {
  searchQuery: string;
  textureFilter: TextureFilter;
  pairingFilter: PairingFilter;
  highCardFilter: HighCardFilter;
  filteredFlops: FlopEntry[];
}

export interface FlopBrowserActions {
  setSearchQuery: (q: string) => void;
  setTextureFilter: (f: TextureFilter) => void;
  setPairingFilter: (f: PairingFilter) => void;
  setHighCardFilter: (f: HighCardFilter) => void;
}

export function useFlopBrowser(flops: FlopEntry[]): [FlopBrowserState, FlopBrowserActions] {
  const [searchQuery, setSearchQuery] = useState('');
  const [textureFilter, setTextureFilter] = useState<TextureFilter>('all');
  const [pairingFilter, setPairingFilter] = useState<PairingFilter>('all');
  const [highCardFilter, setHighCardFilter] = useState<HighCardFilter>('all');

  const filteredFlops = useMemo(() => {
    return flops.filter(f => {
      // Text search
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const cards = f.flopCards.map(c => cardLabel(c)).join(' ').toLowerCase();
        const meta = `${f.texture || ''} ${f.pairing || ''} ${f.connectivity || ''} ${f.highCard || ''}`.toLowerCase();
        if (!(cards + ' ' + meta).includes(q)) return false;
      }
      // Texture
      if (textureFilter !== 'all' && f.texture !== textureFilter) return false;
      // Pairing
      if (pairingFilter !== 'all' && f.pairing !== pairingFilter) return false;
      // High card
      if (highCardFilter !== 'all') {
        if (highCardFilter === 'T-') {
          if ('AKQJ'.includes(f.highCard)) return false;
        } else if (f.highCard !== highCardFilter) {
          return false;
        }
      }
      return true;
    });
  }, [flops, searchQuery, textureFilter, pairingFilter, highCardFilter]);

  return [
    { searchQuery, textureFilter, pairingFilter, highCardFilter, filteredFlops },
    { setSearchQuery, setTextureFilter, setPairingFilter, setHighCardFilter },
  ];
}
