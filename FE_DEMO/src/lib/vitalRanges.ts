// 방문 간호 입력값의 즉시 판정 (화면 안내용, 진단 아님)
// 기준: 2022 고혈압 진료지침 (당뇨 동반 시 130/80 mmHg 미만),
//       2025 당뇨병 진료지침 (공복혈당 80–130 mg/dL)

export type VitalLevel = 'ok' | 'warn' | 'high' | 'danger';

export type VitalJudgement = { level: VitalLevel; text: string };

export const BP_TARGET_TEXT = '목표 130/80 미만';
export const SUGAR_TARGET_TEXT = '목표 80–130';

export function judgeBp(sys: number | '', dia: number | ''): VitalJudgement | null {
  if (sys === '' || dia === '') return null;
  if (sys >= 180 || dia >= 110) return { level: 'danger', text: '매우 높음 · 의사에게 바로 알리세요' };
  if (sys < 90) return { level: 'danger', text: '낮음 · 어지럼증 여부 확인' };
  if (sys >= 140 || dia >= 90) return { level: 'high', text: '높음 · 고혈압 범위' };
  if (sys >= 130 || dia >= 80) return { level: 'warn', text: '목표 초과' };
  return { level: 'ok', text: '목표 범위' };
}

export function judgeSugar(sugar: number | ''): VitalJudgement | null {
  if (sugar === '') return null;
  if (sugar < 70) return { level: 'danger', text: '저혈당 · 즉시 조치 필요' };
  if (sugar >= 250) return { level: 'danger', text: '매우 높음 · 의사에게 바로 알리세요' };
  if (sugar >= 180) return { level: 'high', text: '높음' };
  if (sugar > 130) return { level: 'warn', text: '목표 초과' };
  if (sugar < 80) return { level: 'warn', text: '목표보다 낮음' };
  return { level: 'ok', text: '목표 범위' };
}

export const LEVEL_STYLE: Record<VitalLevel, { box: string; text: string }> = {
  ok:     { box: 'bg-teal-50 border-teal-200',     text: 'text-teal-800' },
  warn:   { box: 'bg-amber-50 border-amber-200',   text: 'text-amber-800' },
  high:   { box: 'bg-orange-50 border-orange-200', text: 'text-orange-800' },
  danger: { box: 'bg-red-50 border-red-200',       text: 'text-red-800' },
};
