// 扑克牌图片映射
// 将牌面代码映射到 PNG 图片路径

export const CARD_IMAGE_BASE = '/cards/2x';

// 牌面代码映射: A=1, 2=2, ..., T=10, J=11, Q=12, K=13
const RANK_MAP: Record<string, string> = {
  'A': '1',
  '2': '2',
  '3': '3',
  '4': '4',
  '5': '5',
  '6': '6',
  '7': '7',
  '8': '8',
  '9': '9',
  'T': '10',
  'J': '11',
  'Q': '12',
  'K': '13',
};

// 花色映射: s=spade, h=heart, d=diamond, c=club
const SUIT_MAP: Record<string, string> = {
  's': 'spade',
  'h': 'heart',
  'd': 'diamond',
  'c': 'club',
};

/**
 * 获取扑克牌图片路径
 * @param card 牌面代码, e.g., "Ah", "Ks", "Td", "2c"
 * @returns 图片路径
 */
export function getCardImagePath(card: string): string {
  if (!card || card.length < 2) {
    return `${CARD_IMAGE_BASE}/back.png`;
  }

  const rank = card[0];
  const suit = card[1];

  const rankNum = RANK_MAP[rank];
  const suitName = SUIT_MAP[suit];

  if (!rankNum || !suitName) {
    return `${CARD_IMAGE_BASE}/back.png`;
  }

  return `${CARD_IMAGE_BASE}/${suitName}_${rankNum}.png`;
}

/**
 * 获取牌背图片路径
 */
export function getCardBackPath(color: string = 'blue'): string {
  const colorMap: Record<string, string> = {
    'blue': 'back-blue.png',
    'red': 'back-red.png',
    'black': 'back-black.png',
    'green': 'back-green.png',
  };
  
  return `${CARD_IMAGE_BASE}/${colorMap[color] || 'back.png'}`;
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
