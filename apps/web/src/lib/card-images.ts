// 扑克牌图片映射
// 将牌面代码映射到 PNG 图片路径

export const CARD_IMAGE_BASE = '/cards/PNG-cards-1.3';
const CARD_FALLBACK_IMAGE = `${CARD_IMAGE_BASE}/red_joker.png`;

// 牌面代码映射: A=ace, 2=2, ..., T=10, J=jack, Q=queen, K=king
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

// 花色映射: s=spades, h=hearts, d=diamonds, c=clubs
const SUIT_MAP: Record<string, string> = {
  's': 'spades',
  'h': 'hearts',
  'd': 'diamonds',
  'c': 'clubs',
};

/**
 * 获取扑克牌图片路径
 * @param card 牌面代码, e.g., "Ah", "Ks", "Td", "2c"
 * @returns 图片路径
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
 * 获取牌背图片路径
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
 * 预加载牌面图片
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
