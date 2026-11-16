import React from 'react';
import { Plus, Minus } from 'lucide-react';

type Props = {
  label: string;
  value: number | '';
  onChange: (value: number | '') => void;
  step?: number;
  unit?: string;
  /** 화면에는 숨기고 스크린리더용 이름으로만 사용 */
  hideLabel?: boolean;
  /** 빈칸일 때 +/− 를 누르면 이 값부터 시작 (예: 지난 측정값) */
  base?: number;
};

export default function NumberSpinner({ label, value, onChange, step = 1, unit, hideLabel, base }: Props) {
  const adjust = (delta: number) => {
    if (value === '' && base !== undefined) { onChange(base); return; }
    const current = value === '' ? 0 : value;
    onChange(Math.max(0, current + delta));
  };

  return (
    <div className="flex-1 bg-sky-50/50 rounded-3xl p-4 border border-sky-100 flex items-center justify-between">
      <button
        type="button"
        aria-label={`${label} ${step} 내리기`}
        onClick={() => adjust(-step)}
        className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"
      >
        <Minus className="w-6 h-6" strokeWidth={2.5} />
      </button>
      <div className="flex flex-col items-center">
        <input
          type="number"
          inputMode="numeric"
          placeholder="—"
          aria-label={label}
          value={value}
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          className="w-24 text-center text-4xl font-extrabold text-slate-900 placeholder:text-slate-300 bg-transparent outline-none focus:ring-0 p-0"
        />
        {label && !hideLabel && <span className="text-sky-700 font-bold text-sm">{label}</span>}
        {unit && <span className="text-slate-400 text-xs mt-0.5">{unit}</span>}
      </div>
      <button
        type="button"
        aria-label={`${label} ${step} 올리기`}
        onClick={() => adjust(step)}
        className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"
      >
        <Plus className="w-6 h-6" strokeWidth={2.5} />
      </button>
    </div>
  );
}
