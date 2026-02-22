/** A single dense layer: weights[outputDim][inputDim], biases[outputDim] */
export interface LayerWeights {
  weights: number[][];
  biases: number[];
}

/** Full model: ordered list of layers (input→hidden→…→output) */
export interface ModelWeights {
  layers: LayerWeights[];
  /** Feature vector length the model expects */
  inputSize: number;
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

/** A single training sample (compact keys for JSONL storage) */
export interface TrainingSample {
  /** Feature vector */
  f: number[];
  /** Label: [raise, call, fold] probabilities from teacher */
  l: [number, number, number];
  /** Hand ID (for debugging/dedup) */
  h: string;
  /** Street */
  s: string;
}
