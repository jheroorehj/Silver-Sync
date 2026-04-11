import React from 'react';
import { CheckCircle2, User } from 'lucide-react';
import type { DocPatientStatus, NursePatientStatus } from '../../types';

// ── Doctor view badge (orange / amber / teal) ─────────────────────────────
const DOC_BADGE_CONFIG: Record<DocPatientStatus, { container: string; dot: string; label: string }> = {
  orange: { container: 'bg-orange-50 border-orange-200 text-orange-600', dot: 'bg-orange-500', label: '대면권고' },
  amber:  { container: 'bg-amber-50  border-amber-200  text-amber-600',  dot: 'bg-amber-500',  label: '주의'    },
  teal:   { container: 'bg-teal-50   border-teal-200   text-teal-600',   dot: 'bg-teal-500',   label: '비대면'  },
};

export function DocStatusBadge({ status }: { status: DocPatientStatus }) {
  const cfg = DOC_BADGE_CONFIG[status];
  return (
    <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${cfg.container}`}>
      <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      <span className="text-[10px] font-bold whitespace-nowrap">{cfg.label}</span>
    </div>
  );
}

// ── Nurse view avatar icon (pending / completed) ───────────────────────────
export function NurseStatusAvatar({ status }: { status: NursePatientStatus }) {
  return (
    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
      status === 'completed' ? 'bg-teal-100 text-teal-600' : 'bg-sky-100 text-sky-600'
    }`}>
      {status === 'completed'
        ? <CheckCircle2 className="w-7 h-7" strokeWidth={2.5} />
        : <User className="w-7 h-7" strokeWidth={2.5} />
      }
    </div>
  );
}
