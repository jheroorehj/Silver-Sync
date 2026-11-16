// 데모 모드 분석: 간호사 입력값으로 재진 방식을 판정한다.
// 백엔드 multi_agent_rag/clinical_safety.py (CDS 규칙)와
// neuro_symbolic/triage.py (응급 → 긴급 대면 → 일반 대면 → 그 외, 불확실하면 대면)를
// 화면 시연용으로 단순화해 옮긴 것. 실제 진단 도구가 아님.

import type { DocPatient, SoapNote } from '../types';

export type AnalysisInput = {
  systolic: number | null;
  diastolic: number | null;
  sugar: number | null;
  medication: 'well' | 'missed' | '';
  observations: string[];
  notes: string;
  diseases: string[];
};

type Severity = 'emergency' | 'urgent' | 'routine' | 'caution';
type RefKey = 'retina-refer' | 'retina-control' | 'bp-target';

type Alert = { severity: Severity; label: string; reason: string; ref?: RefKey[] };

export type DemoAnalysis = {
  verdict: {
    consultationType: '대면' | '비대면';
    verdictLevel: 'red' | 'yellow' | 'green';
    riskScore: number;
    confidence: number;
  };
  recommendation: DocPatient['aiRecommendation'];
  soap: SoapNote;
  agentTrace: string[];
};

// 저장소의 진료지침 PDF 원문과 대조해 확인한 문장만 사용
const REFERENCES: Record<RefKey, { source: string; excerpt: string }> = {
  'retina-refer': {
    source: '대한당뇨병학회 2025 당뇨병 진료지침 요약문, 8-3. 당뇨병망막병증 (권고 6)',
    excerpt: '증식당뇨병망막병증으로 진행하였을 경우에는 범망막광응고의 시행을 위해 안과전문의에게 환자를 의뢰한다.',
  },
  'retina-control': {
    source: '대한당뇨병학회 2025 당뇨병 진료지침 요약문, 8-3. 당뇨병망막병증 (권고 1)',
    excerpt: '당뇨병망막병증의 발생 위험을 낮추거나 진행을 억제하기 위해 최적의 혈당, 혈압 및 지질조절을 권고한다.',
  },
  'bp-target': {
    source: '대한고혈압학회 2022 고혈압 진료지침, 8.3.2. 당뇨병을 동반한 고혈압',
    excerpt: '무증상장기손상이 동반된 당뇨병의 경우 혈압은 130/80 mmHg 미만으로 조절할 것을 고려한다.',
  },
};

// 백엔드 _EMERGENCY_SYMPTOMS / _MODERATE_SYMPTOMS 축약
const EMERGENCY_WORDS: [string, string][] = [
  ['흉통', '흉통'], ['호흡곤란', '호흡곤란'], ['의식 변화', '의식 변화'], ['의식변화', '의식 변화'],
  ['기절', '실신'], ['쓰러', '실신'],
];
const RETINA_WORDS: [string, string][] = [
  ['시야가 흐', '시야 흐림'], ['시야', '시야 이상'], ['시력 저하', '시력 저하'], ['날파리', '비문증(날파리증)'], ['비문', '비문증'],
];
const MODERATE_WORDS: [string, string][] = [
  ['가슴 답답', '흉부 답답함'], ['가슴이 답답', '흉부 답답함'], ['숨이 차', '숨이 참'],
  ['어지러', '어지러움'], ['부종', '부종'], ['붓', '부종'], ['저리', '저림'], ['저림', '저림'],
  ['발 상처', '족부 상처'], ['감각', '감각 저하'], ['체중이 늘', '체중 증가'], ['체중 증가', '체중 증가'],
];
// 관찰 소견 칩 → 증상 (백엔드 moderate 키워드에 해당하는 것만 대면 트리거)
const CHIP_MODERATE: Record<string, string> = { '부종 관찰': '부종', '어지러움 호소': '어지러움', '호흡 가쁨': '숨이 참' };
const CHIP_CAUTION = ['인지 저하 의심', '거동 불편', '식욕 부진', '수면 장애', '피부 건조'];

const b = (s: string | number) => `<span class="font-bold text-slate-900">${s}</span>`;

function findWords(text: string, words: [string, string][]) {
  const found = new Set<string>();
  words.forEach(([kw, label]) => { if (text.includes(kw)) found.add(label); });
  return [...found];
}

export function analyzeVisit(input: AnalysisInput): DemoAnalysis {
  const { systolic: sys, diastolic: dia, sugar, medication, observations, notes } = input;
  const hasDm = input.diseases.some(d => d.includes('당뇨'));
  const alerts: Alert[] = [];
  const text = notes.trim();
  const missing = [sys == null || dia == null ? '혈압' : '', sugar == null ? '혈당' : ''].filter(Boolean);

  // 바이탈 (Rule 6: 응급, Rule 5: DM 동반 BP 목표)
  if (sys != null && dia != null) {
    if (sys >= 180 || dia >= 120) {
      alerts.push({ severity: 'emergency', label: '고혈압 위기', reason: `혈압 ${b(`${sys}/${dia} mmHg`)} — 고혈압 위기 범위` });
    } else if (sys >= 130 || dia >= 80) {
      alerts.push({ severity: 'routine', label: '혈압 목표 초과', reason: `혈압 ${b(`${sys}/${dia} mmHg`)}로 목표(130/80 미만) 초과`, ref: ['bp-target'] });
    }
  }
  if (sugar != null) {
    if (sugar >= 250) alerts.push({ severity: 'emergency', label: '고혈당', reason: `공복혈당 ${b(`${sugar} mg/dL`)} — 즉시 평가 필요` });
    else if (sugar <= 70) alerts.push({ severity: 'emergency', label: '저혈당', reason: `공복혈당 ${b(`${sugar} mg/dL`)} — 저혈당` });
    else if (sugar > 130) alerts.push({ severity: 'caution', label: '공복혈당 목표 초과', reason: `공복혈당 ${b(`${sugar} mg/dL`)}로 목표(80–130) 초과` });
  }

  // 증상 (Rule 7)
  findWords(text, EMERGENCY_WORDS).forEach(l =>
    alerts.push({ severity: 'emergency', label: l, reason: `특이사항에 ${b(l)} 호소 — 응급 의심 증상` }));
  const retina = findWords(text, RETINA_WORDS).filter((l, _, all) =>
    !(l === '시야 이상' && all.includes('시야 흐림')) && !(l === '비문증' && all.includes('비문증(날파리증)')));
  if (retina.length) {
    alerts.push({
      severity: hasDm ? 'urgent' : 'routine',
      label: hasDm ? '망막병증 진행 의심' : '시야 이상',
      reason: `${b(retina.join('·'))} 호소${hasDm ? ' — 당뇨망막병증 진행 의심' : ''}`,
      ref: hasDm ? ['retina-refer', 'retina-control'] : undefined,
    });
  }
  const moderate = new Set([...findWords(text, MODERATE_WORDS), ...observations.map(o => CHIP_MODERATE[o]).filter(Boolean)]);
  if (moderate.size) {
    alerts.push({ severity: 'routine', label: '합병증 의심 증상', reason: `${b([...moderate].join('·'))} — 합병증 평가 필요` });
  }
  const cautionChips = observations.filter(o => CHIP_CAUTION.includes(o));
  if (cautionChips.length) {
    alerts.push({ severity: 'caution', label: '관찰 소견', reason: `관찰 소견: ${b(cautionChips.join(', '))}` });
  }
  if (medication === 'missed') {
    alerts.push({ severity: 'caution', label: '복약 누락', reason: `복약을 ${b('거른 적 있음')} — 순응도 확인 필요` });
  }

  // 판정 사다리 (triage.py)
  const has = (s: Severity) => alerts.some(a => a.severity === s);
  const cautions = alerts.filter(a => a.severity === 'caution').length;
  let verdict: DemoAnalysis['verdict'];
  let highlight: string;
  if (has('emergency')) {
    verdict = { consultationType: '대면', verdictLevel: 'red', riskScore: 90, confidence: 95 };
    highlight = '즉시 대면 평가가 권고';
  } else if (has('urgent')) {
    verdict = { consultationType: '대면', verdictLevel: 'red', riskScore: Math.min(88, 75 + cautions * 3), confidence: 88 };
    highlight = '대면 진료가 권고';
  } else if (has('routine')) {
    verdict = { consultationType: '대면', verdictLevel: 'yellow', riskScore: Math.min(72, 60 + cautions * 3), confidence: 82 };
    highlight = '대면 진료가 권고';
  } else if (missing.length) {
    // 데이터 불충분 → 안전 비대칭: 대면
    verdict = { consultationType: '대면', verdictLevel: 'yellow', riskScore: 55, confidence: 60 };
    highlight = '대면 진료가 권고';
  } else {
    verdict = { consultationType: '비대면', verdictLevel: 'green', riskScore: Math.min(45, 25 + cautions * 5), confidence: 85 };
    highlight = '비대면 진료가 가능';
  }

  const gates = alerts.filter(a => a.severity !== 'caution');
  const order: Severity[] = ['emergency', 'urgent', 'routine', 'caution'];
  const sorted = [...alerts].sort((x, y) => order.indexOf(x.severity) - order.indexOf(y.severity));
  const top = sorted[0];

  const title = top && top.severity !== 'caution'
    ? `${top.label}${gates.length > 1 ? ` 외 ${gates.length - 1}건` : ''} 소견으로`
    : missing.length ? `${missing.join('·')} 측정값이 없어 안전을 위해` : '입력된 지표가 모두 안정적이어서';

  const reasons = sorted.slice(0, 3).map(a => ({
    type: a.severity === 'emergency' || a.severity === 'urgent' ? 'alert' : a.severity === 'routine' ? 'up' : 'up',
    text: a.reason,
  }));
  if (sys != null && dia != null && !alerts.some(a => a.label.startsWith('혈압') || a.label === '고혈압 위기') && reasons.length < 3)
    reasons.push({ type: 'check', text: `혈압 ${b(`${sys}/${dia} mmHg`)} — 목표 범위` });
  if (sugar != null && !alerts.some(a => a.label.includes('혈당')) && reasons.length < 3)
    reasons.push({ type: 'check', text: `공복혈당 ${b(`${sugar} mg/dL`)} — 목표 범위` });
  if (medication === 'well' && reasons.length < 3) reasons.push({ type: 'check', text: '복약 순응 양호' });

  const refs = [...new Set(alerts.flatMap(a => a.ref ?? []))].map(k => REFERENCES[k]);

  const details = gates.length
    ? `CDS 안전 규칙 ${gates.length}건이 발동했습니다 (${gates.map(a => a.label).join(', ')}). 규칙이 발동하면 AI 추론보다 안전 규칙을 우선하며, 판단이 불확실할 때는 대면을 권고하는 안전 비대칭 원칙을 따릅니다.`
    : missing.length
      ? `${missing.join('·')} 값이 입력되지 않았습니다. 판단 근거가 부족하면 안전을 위해 대면 평가를 권고합니다.`
      : `발동한 CDS 안전 규칙이 없고 입력된 지표가 목표 범위에 있어 비대면 추적이 적합합니다.${cautions ? ' 참고 소견은 다음 비대면 상담에서 확인하세요.' : ''}`;

  const bpText = sys != null && dia != null ? `${sys}/${dia} mmHg` : '미측정';
  const sugarText = sugar != null ? `${sugar} mg/dL` : '미측정';
  const medText = medication === 'well' ? '잘 복용 중' : medication === 'missed' ? '거른 적 있음' : '미확인';

  const plan = verdict.consultationType === '비대면'
    ? '1. 현재 처방 유지. 2. 비대면 정기 상담 유지. 3. 다음 방문 시 바이탈 재측정.'
    : [
        has('emergency') ? '1. 즉시 내원 또는 응급실 평가 안내.' : '1. 대면 진료 예약.',
        retina.length && hasDm ? '2. 안과 협진 의뢰.' : '2. 대면 진료에서 처방 재검토.',
        has('routine') && alerts.some(a => a.label === '혈압 목표 초과') ? '3. 혈압 조절 강화 검토.' : '3. 증상 경과 재확인.',
      ].join(' ');

  const cautionText = alerts.filter(a => a.severity === 'caution').map(a => a.reason.replace(/<[^>]+>/g, ''));
  const soap: SoapNote = {
    subjective: [
      text ? `특이사항: ${text}` : '특이 호소 없음.',
      observations.length ? `관찰 소견: ${observations.join(', ')}.` : '',
      `복약: ${medText}.`,
    ].filter(Boolean).join(' '),
    objective: `혈압 ${bpText}. 공복혈당 ${sugarText}. (방문 간호 측정)`,
    assessment: (gates.length
      ? `${sorted.filter(a => a.severity !== 'caution').map(a => a.reason.replace(/<[^>]+>/g, '')).join('. ')}. 판정: ${verdict.consultationType} (위험도 ${verdict.riskScore}).`
      : `${missing.length ? '측정값 일부 누락으로 판단 근거 부족.' : 'CDS 규칙 발동 없음. 혈압·혈당 목표 범위.'} 판정: ${verdict.consultationType} (위험도 ${verdict.riskScore}).`
      ) + (cautionText.length ? ` 참고: ${cautionText.join('. ')}.` : ''),
    plan,
    anomalies: [
      ...(sys != null && sys >= 140 ? ['bp'] : []),
      ...(sugar != null && sugar >= 126 ? ['sugar'] : []),
    ],
    references: refs.length ? refs : undefined,
  };

  const filled = 6 - missing.length - (medication ? 0 : 1);
  const agentTrace = [
    `데이터 정리 에이전트 · 입력 ${filled}개 항목 정리${missing.length ? ` (누락: ${missing.join(', ')})` : ', 누락 없음'}`,
    `CDS 안전 규칙 · ${gates.length ? `${gates.length}건 발동: ${gates.map(a => a.label).join(', ')}` : '발동 규칙 없음'}`,
    `임상 추론 에이전트 · ${refs.length ? `진료지침 근거 ${refs.length}건 연결` : '추가 진료지침 근거 불필요'}`,
    `최종 판정 · ${verdict.consultationType} ${verdict.consultationType === '대면' ? '권고' : '가능'} (위험도 ${verdict.riskScore})`,
  ];

  return {
    verdict,
    recommendation: {
      title,
      highlight,
      reasons,
      details,
      stats: [
        { label: '발동한 안전 규칙', value: `${gates.length}건` },
        { label: '방문 측정값', value: `${bpText} · ${sugarText}` },
      ],
    },
    soap,
    agentTrace,
  };
}
