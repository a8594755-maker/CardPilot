import { useRangeEditor } from '../../stores/range-editor';

export function WeightSlider() {
  const { weight, setWeight } = useRangeEditor();

  return (
    <input
      type="range"
      min={0}
      max={100}
      value={weight}
      onChange={(e) => setWeight(Number(e.target.value))}
      className="w-32 h-1.5 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
    />
  );
}
