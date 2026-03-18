import { useState, useEffect, type InputHTMLAttributes } from 'react';

type NumericInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'type'
> & {
  value: number;
  onChange: (value: number) => void;
};

/**
 * Controlled numeric input that keeps local string state to avoid
 * the leading-zero bug with <input type="number"> + React.
 * Normalizes the displayed value on blur.
 */
export function NumericInput({ value, onChange, onBlur, ...props }: NumericInputProps) {
  const [local, setLocal] = useState(String(value));

  useEffect(() => {
    setLocal(String(value));
  }, [value]);

  return (
    <input
      type="number"
      value={local}
      onChange={(e) => {
        setLocal(e.target.value);
        const num = parseFloat(e.target.value);
        if (!isNaN(num)) onChange(num);
      }}
      onBlur={(e) => {
        const num = parseFloat(local);
        const normalized = isNaN(num) ? 0 : num;
        setLocal(String(normalized));
        onChange(normalized);
        onBlur?.(e);
      }}
      {...props}
    />
  );
}
