/** A single dense layer: weights[outputDim][inputDim], biases[outputDim] */
export interface LayerWeights {
  weights: number[][];
  biases: number[];
}

/** Dense layer with LayerNorm: weights + biases + LN scale/bias */
export interface LayerWithNorm {
  weights: number[][];
  biases: number[];
  lnScale: number[];
  lnBias: number[];
}

/** V3 multi-layer head: hidden + output layers */
export interface HeadWeights {
  layers: LayerWeights[];
}

/** V3 architecture config stored in model JSON */
export interface V3Architecture {
  cardEmbedDim: number;
  handCategories: number;
  numCards: number;
  contextDim: number;
  encoderDim: number;
  trunkSizes: number[];
  headHidden: number;
  useLayerNorm: boolean;
  dropout?: number;
}

/** Full model: ordered list of layers (input→hidden→…→output) */
export interface ModelWeights {
  layers: LayerWeights[];
  /** V2 multi-head: action output layer (backbone→3) */
  actionHead?: LayerWeights;
  /** V2 multi-head: sizing output layer (backbone→5) */
  sizingHead?: LayerWeights;
  /** Feature vector length the model expects */
  inputSize: number;
  /** Model version */
  version?: 'v1' | 'v2' | 'v3';
  /** ISO timestamp of when the model was trained */
  trainedAt: string;
  /** Number of training samples used */
  trainingSamples: number;
  /** Final validation loss */
  valLoss: number;
  /** Architecture metadata for reproducibility */
  architecture?: {
    hiddenSizes?: number[];
  } & Partial<V3Architecture>;

  // ── V3 embedding model fields ──
  /** V3: hand category embedding table [169][embedDim] */
  handEmbedding?: number[][];
  /** V3: card embedding table [53][embedDim] */
  cardEmbedding?: number[][];
  /** V3: hole card encoder (embedDim+5 → encoderDim) */
  holeEncoder?: LayerWeights;
  /** V3: board card encoder (embedDim → encoderDim) */
  boardEncoder?: LayerWeights;
  /** V3: context float encoder (24 → encoderDim) */
  contextEncoder?: LayerWeights;
  /** V3: trunk layers with LayerNorm */
  trunk?: LayerWithNorm[];
  /** V3: action head (multi-layer) */
  actionHeadV3?: HeadWeights;
  /** V3: sizing head (multi-layer) */
  sizingHeadV3?: HeadWeights;

  /** Data manifest: what CFR data was used for training */
  dataManifest?: {
    configName: string;
    flopCount: number;
    totalSamples: number;
    streets: string[];
  };
  /** Incremental training history */
  trainingHistory?: Array<{
    timestamp: string;
    flopCount: number;
    valLoss: number;
    samples: number;
  }>;
}

/** Strategy mix output matching the bot's existing Mix type */
export interface StrategyMix {
  raise: number;
  call: number;
  fold: number;
}

/** V2 sizing bucket distribution (probabilities over 5 raise size candidates) */
export interface SizingMix {
  third: number; // 33% pot
  half: number; // 50% pot
  twoThirds: number; // 66% pot
  pot: number; // 100% pot
  allIn: number; // all-in
}

/** Combined prediction result (V2 multi-head) */
export interface PredictResult {
  action: StrategyMix;
  sizing?: SizingMix;
}

/** A single training sample (compact keys for JSONL storage) */
export interface TrainingSample {
  /** Feature vector */
  f: number[];
  /** Label: [raise, call, fold] probabilities from teacher */
  l: [number, number, number];
  /** V2: sizing label [33%, 50%, 66%, 100%, allIn] probabilities */
  sz?: [number, number, number, number, number];
  /** Hand ID (for debugging/dedup) */
  h: string;
  /** Street */
  s: string;
}
