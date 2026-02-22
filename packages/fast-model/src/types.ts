/** A single dense layer: weights[outputDim][inputDim], biases[outputDim] */
export interface LayerWeights {
  weights: number[][];
  biases: number[];
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
  /** Model version: 'v1' (single-head 48 features) or 'v2' (multi-head 54 features) */
  version?: 'v1' | 'v2';
  /** ISO timestamp of when the model was trained */
  trainedAt: string;
  /** Number of training samples used */
  trainingSamples: number;
  /** Final validation loss */
  valLoss: number;
}

/** Strategy mix output matching the bot's existing Mix type */
export interface StrategyMix {
  raise: number;
  call: number;
  fold: number;
}

/** V2 sizing bucket distribution (probabilities over 5 raise size candidates) */
export interface SizingMix {
  third: number;      // 33% pot
  half: number;       // 50% pot
  twoThirds: number;  // 66% pot
  pot: number;        // 100% pot
  allIn: number;      // all-in
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
