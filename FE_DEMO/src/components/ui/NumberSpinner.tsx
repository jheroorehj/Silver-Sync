import React from 'react';
import { Plus, Minus } from 'lucide-react';

type Props = {
  label: string;
  value: number | '';
  onChange: (value: number | '') => void;
  step?: number;
  unit?: string;
};

export default function NumberSpinner({ label, value, onChange, step = 1, unit }: Props) {
  const adjust = (delta: number) => {
    const current = value === '' ? 0 : value;
    onChange(Math.max(0, current + delta));
  };

  return (
    <div className="flex-1 bg-sky-50/50 rounded-3xl p-4 border border-sky-100 flex items-center justify-between">
      <button
        onClick={() => adjust(-step)}
        className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"
      >
        <Minus className="w-6 h-6" strokeWidth={2.5} />
      </button>
      <div className="flex flex-col items-center">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
          className="w-24 text-center text-4xl font-extrabold text-slate-900 bg-transparent outline-none focus:ring-0 p-0"
        />
        {label && <span className="text-sky-600 font-bold text-sm">{label}</span>}
        {unit && <span className="text-slate-400 text-xs mt-0.5">{unit}</span>}
      </div>
      <button
        onClick={() => adjust(step)}
        className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"
      >
        <Plus className="w-6 h-6" strokeWidth={2.5} />
      </button>
    </div>
  );
}
