// Poker card image mapping
// Map card codes to PNG image paths

export const CARD_IMAGE_BASE = '/cards/PNG-cards-1.3';
const CARD_FALLBACK_IMAGE = `${CARD_IMAGE_BASE}/red_joker.png`;

// Rank mapping: A=ace, 2=2, ..., T=10, J=jack, Q=queen, K=king
const RANK_MAP: Record<string, string> = {
  'A': 'ace',
  '2': '2',
  '3': '3',
  '4': '4',
  '5': '5',
  '6': '6',
  '7': '7',
  '8': '8',
  '9': '9',
  'T': '10',
  'J': 'jack',
  'Q': 'queen',
  'K': 'king',
};

// Suit mapping: s=spades, h=hearts, d=diamonds, c=clubs
const SUIT_MAP: Record<string, string> = {
  's': 'spades',
  'h': 'hearts',
  'd': 'diamonds',
  'c': 'clubs',
};

/**
 * Get poker card image path
 * @param card Card code, e.g., "Ah", "Ks", "Td", "2c"
 * @returns Image path
 */
export function getCardImagePath(card: string): string {
  if (!card || card.length < 2) {
    return CARD_FALLBACK_IMAGE;
  }

  const rank = card[0];
  const suit = card[1];

  const rankNum = RANK_MAP[rank];
  const suitName = SUIT_MAP[suit];

  if (!rankNum || !suitName) {
    return CARD_FALLBACK_IMAGE;
  }

  return `${CARD_IMAGE_BASE}/${rankNum}_of_${suitName}.png`;
}

/**
 * Get card back image path
 */
export function getCardBackPath(color: string = 'blue'): string {
  const colorMap: Record<string, string> = {
    'blue': 'black_joker.png',
    'red': 'red_joker.png',
    'black': 'black_joker.png',
    'green': 'black_joker.png',
  };
  
  return `${CARD_IMAGE_BASE}/${colorMap[color] || 'black_joker.png'}`;
}

/**
 * Preload card face images
 */
export function preloadCardImages(): void {
  const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K'];
  const suits = ['s', 'h', 'd', 'c'];

  for (const rank of ranks) {
    for (const suit of suits) {
      const img = new Image();
      img.src = getCardImagePath(`${rank}${suit}`);
    }
  }
}

export default {
  getCardImagePath,
  getCardBackPath,
  preloadCardImages,
};
