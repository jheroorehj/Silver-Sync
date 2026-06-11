import type { DocPatient } from '../types';

export const demoPatients: DocPatient[] = [
  // ── D-1: 홍길동001 (HARDNEG-HN4) — 비대면, 안정 CKD ─────────────────────
  {
    id: 2,
    lambdaPatientId: 'HARDNEG-HN4-0001',
    daysUntilDeadline: 1,
    name: '홍길동',
    age: 75,
    gender: '남',
    time: '09:30',
    status: 'teal',
    disease: '당뇨, 고혈압, 만성콩팥병',
    aiRecommendation: {
      title: '만성콩팥병 동반에도 모든 지표 안정적으로',
      highlight: '비대면 진료가 가능',
      reasons: [
        { type: 'check', text: '혈압 <span class="font-bold text-slate-900">126/75 mmHg</span>로 목표치 이내 유지' },
        { type: 'check', text: 'eGFR <span class="font-bold text-slate-900">45 mL/min</span> — CKD 3기 안정 추적 중' },
        { type: 'check', text: '공복혈당 101 mg/dL, HbA1c 7.1% (목표 범위 내)' },
      ],
      details: '만성콩팥병(CKD 3기, eGFR 45)을 동반하고 있으나 지난 3회 외래에서 eGFR이 안정적으로 유지되고 있습니다. 혈압·혈당 모두 목표 범위이며 새로운 증상 없이 복약 순응도도 양호합니다. 신장내과 의뢰 필요 기준(eGFR < 30)에 해당하지 않아 비대면 정기 추적이 적합합니다.',
      stats: [
        { label: 'eGFR', value: '45 mL/min (안정)' },
        { label: '복약 순응도', value: '27/30일 (90%)' },
      ],
    },
    vitals: {
      bp:        { current: '126/75', trend: '안정적 유지 중', trendUp: false, data: [130, 127, 124, 128, 126] },
      sugar:     { current: '101',    status: '목표 범위 유지',  trendUp: false, data: [112, 106, 108, 104, 101] },
      adherence: { current: '90',     data: [100, 100, 90, 80, 100] },
    },
    footerAction: '비대면 상담 예약하기',
    soapNote: {
      subjective: '정기 재진. 특별한 불편 증상 없음. 약 복용 중 하루 누락 2회 있었음.',
      objective:  '혈압 126/75 mmHg. 공복혈당 101 mg/dL, 식후혈당 145 mg/dL. HbA1c 7.1%. eGFR 45 mL/min (안정). 복약 순응도 90%.',
      assessment: 'CKD 3기 안정 추적. 혈압·혈당·신기능 모두 현재 처방으로 적절히 조절되고 있음. 신장내과 의뢰 기준 미해당.',
      plan:       '1. 현재 처방 유지. 2. 비대면 정기 추적 월 1회. 3. eGFR 변화 추이 3개월마다 재확인.',
      anomalies:  [],
    },
  },

  // ── D-2: 홍영희 (EDGE-E3) — 대면, 당뇨망막병증 악화 ─────────────────────
  {
    id: 3,
    lambdaPatientId: 'EDGE-E3-0001',
    daysUntilDeadline: 2,
    name: '홍영희',
    age: 66,
    gender: '여',
    time: '10:00',
    status: 'orange',
    disease: '당뇨, 고혈압',
    aiRecommendation: {
      title: '당뇨망막병증 악화 의심 증상으로',
      highlight: '대면 진료가 권고',
      reasons: [
        { type: 'alert', text: '최근 문진에서 <span class="font-bold text-slate-900">시야 흐림·비문증</span> 호소 — 망막병증 진행 의심' },
        { type: 'up',    text: '공복혈당 <span class="font-bold text-slate-900">138 mg/dL</span>로 목표치 초과 지속' },
        { type: 'check', text: '복약 순응도 양호하나 안과 협진 여부 재검토 필요' },
      ],
      details: '당뇨 유병 기간이 길고 최근 혈당 조절이 불안정한 상태에서 시야 흐림·비문증이 새롭게 보고되었습니다. 비증식성 당뇨망막병증에서 증식성으로 진행될 가능성을 배제하기 위해 안과 협진을 포함한 대면 평가가 필요합니다.',
      stats: [
        { label: '시야 이상 호소', value: '비문증·흐림 신규 보고' },
        { label: '공복혈당', value: '138 mg/dL (↑)' },
      ],
    },
    vitals: {
      bp:        { current: '138/88', trend: '소폭 상승',        trendUp: true,  data: [132, 134, 136, 140, 138] },
      sugar:     { current: '138',    status: '목표치 초과 (↑)', trendUp: true,  data: [122, 128, 135, 142, 138] },
      adherence: { current: '92',     data: [100, 90, 90, 90, 100] },
    },
    footerAction: '대면 진료 예약하기',
    soapNote: {
      subjective: '정기 재진. 최근 2주간 시야가 흐리고 눈앞에 실 같은 것이 보인다고 호소(비문증). 복약 유지 중.',
      objective:  '혈압 138/88 mmHg. 공복혈당 138 mg/dL. HbA1c 7.8%. 복약 순응도 92%.',
      assessment: '당뇨망막병증 진행 의심. 신규 시각 증상 발생으로 안과 협진 필요. 혈당 조절도 목표치 초과 지속.',
      plan:       '1. 즉시 안과 협진 의뢰. 2. 대면 진료 통해 혈당 조절 약제 재검토. 3. 혈압 조절 강화.',
      anomalies:  ['sugar'],
    },
  },

  // ── D-5: 박대호 (CLEAR-C2) — 비대면, 전 수치 안정 ───────────────────────
  {
    id: 5,
    lambdaPatientId: 'CLEAR-C2-0001',
    daysUntilDeadline: 5,
    name: '박대호',
    age: 74,
    gender: '남',
    time: '11:00',
    status: 'teal',
    disease: '당뇨, 고혈압',
    aiRecommendation: {
      title: '모든 지표가 안정적으로 유지되어',
      highlight: '비대면 진료가 가능',
      reasons: [
        { type: 'check', text: '혈압 <span class="font-bold text-slate-900">124/80 mmHg</span>으로 목표치 이내 안정' },
        { type: 'check', text: '공복혈당 <span class="font-bold text-slate-900">105 mg/dL</span>, HbA1c 6.8% (목표 범위)' },
        { type: 'check', text: '자각 증상 없음, 복약 순응도 100%' },
      ],
      details: '최근 3개월간 혈압·혈당 모두 목표 범위 내에서 안정적으로 유지되고 있으며, 활동량과 수면 패턴도 규칙적입니다. 자각 증상이 없고 생활 습관 관리도 우수하여 현재 처방을 유지하며 비대면 정기 상담으로 충분합니다.',
      stats: [
        { label: 'HbA1c', value: '6.8% (목표 범위)' },
        { label: '복약 순응도', value: '100% (30/30일)' },
      ],
    },
    vitals: {
      bp:        { current: '124/80', trend: '안정적 유지 중', trendUp: false, data: [126, 122, 125, 124, 124] },
      sugar:     { current: '105',    status: '목표 범위 유지', trendUp: false, data: [108, 104, 107, 103, 105] },
      adherence: { current: '100',    data: [100, 100, 100, 100, 100] },
    },
    footerAction: '비대면 상담 예약하기',
    soapNote: {
      subjective: '정기 재진. 특별한 불편 사항 없음. 매일 30분 산책, 저염식 유지 중.',
      objective:  '혈압 124/80 mmHg. 공복혈당 105 mg/dL. HbA1c 6.8%. 복약 순응도 100%.',
      assessment: '당뇨·고혈압 모두 안정적 조절 중. 현재 처방 및 생활 습관 유지로 충분.',
      plan:       '1. 현재 처방 유지. 2. 월 1회 비대면 정기 상담. 3. 현재 운동·식단 습관 격려.',
      anomalies:  [],
    },
  },
];
