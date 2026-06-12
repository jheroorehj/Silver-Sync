const API_BASE = 'https://ky1y2zdh68.execute-api.ap-northeast-2.amazonaws.com/dev';
const CACHE_KEY = 'silversync_s3_keys';
const NURSE_QUEUE_KEY = 'silversync_nurse_queue';
const TODAY_SCHEDULE_KEY = 'silversync_today_schedule';

// ── Schedule bridge (Nurse → Doctor via localStorage) ────────────────────

export type ScheduleEntry = {
  lambdaPatientId: string;
  time: string;
};

export function saveSchedule(entries: ScheduleEntry[]) {
  localStorage.setItem(TODAY_SCHEDULE_KEY, JSON.stringify(entries));
}

export function getSchedule(): ScheduleEntry[] {
  try { return JSON.parse(localStorage.getItem(TODAY_SCHEDULE_KEY) ?? '[]'); } catch { return []; }
}

// ── Verdict type (extended with parsed S3 fields) ────────────────────────

export type LambdaVerdict = {
  consultationType: '대면' | '비대면';
  verdictLevel: 'red' | 'yellow' | 'green';
  riskScore: number;
  confidence: number;
  // Parsed from full S3 result
  patientName?: string;
  age?: number;
  gender?: string;
  conditions?: string[];
  bpCurrent?: string;
  bpTrendUp?: boolean;
  bpData?: number[];
  sugarCurrent?: string;
  sugarTrendUp?: boolean;
  sugarData?: number[];
  adherenceRate?: number;
  adherenceData?: number[];
  soapNote?: {
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
    anomalies: string[];
  };
  recommendation?: {
    title: string;
    highlight: string;
    reasons: { type: string; text: string }[];
    details: string;
    stats: { label: string; value: string }[];
  };
  footerAction?: string;
  guidelineEvidence?: { source: string; content: string }[];
};

export type LambdaStatus =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'done'; verdict: LambdaVerdict }
  | { type: 'error'; message?: string };

// ── S3 Full Parser ───────────────────────────────────────────────────────

type R = Record<string, unknown>;

function r(v: unknown): R { return (v as R | undefined) ?? {}; }
function arr<T>(v: unknown): T[] { return (v as T[] | undefined) ?? []; }
function str(v: unknown, fallback = ''): string { return v != null ? String(v) : fallback; }
function num(v: unknown, fallback = 0): number { return v != null ? Number(v) : fallback; }

export function parseS3Full(data: R): LambdaVerdict {
  const meta = r(data._meta);
  // judge 먼저 파싱 — S3 포맷에 따라 verdict 필드가 judge 안에만 있을 수 있음
  const judge = r(data.judge);

  const verdictLevel = (
    str(data.verdict_level) || str(meta.verdict_level) || str(judge.verdict_level) || 'green'
  ) as 'red' | 'yellow' | 'green';

  const rawConsultationType =
    str(data.consultation_type) || str(meta.consultation_type) || str(judge.consultation_type);
  // consultation_type 없으면 verdictLevel로 추론
  const consultationType = (rawConsultationType || (verdictLevel === 'red' ? '대면' : '비대면')) as '대면' | '비대면';

  const riskScore = num(data.risk_score ?? meta.risk_score ?? judge.risk_score);
  const confidence = num(data.confidence ?? meta.confidence ?? judge.confidence);

  const curatedCase = r(data.curated_case);
  const patient = r(curatedCase.patient);
  const raw = r(patient.raw);
  const conditions = arr<string>(patient.conditions);
  const signals = r(curatedCase.signals);

  // visit_records: { vital_signs: { blood_pressure, blood_sugar } } 형식 — 현재 방문 측정값 포함
  // patient.records: { blood_pressure, blood_sugar } 형식 — DynamoDB 과거 기록 (히스토리 차트용)
  const visitRecords = arr<R>(raw.visit_records);
  const patientRecords = arr<R>(patient.records);

  // 두 가지 포맷 모두 지원하는 추출 헬퍼
  function extractBpSystolic(record: R): number {
    const vs = r(record.vital_signs);
    const bp = str(vs.blood_pressure) || str(record.blood_pressure) || '120/80';
    return num(bp.split('/')[0], 120);
  }
  function extractSugar(record: R): number {
    const vs = r(record.vital_signs);
    return num(vs.blood_sugar ?? vs.fasting_glucose ?? record.blood_sugar, 100);
  }

  // 히스토리 차트: patient.records 우선 (DynamoDB 전체 기록), 없으면 visit_records
  const historySource = patientRecords.length > 0 ? patientRecords : visitRecords;
  // 현재값: visit_records 우선 (실제 측정 포함), 없으면 patient.records
  const currentSource = visitRecords.length > 0 ? visitRecords : patientRecords;

  const sortedHistory = [...historySource]
    .sort((a, b) => str(a.visit_date).localeCompare(str(b.visit_date)))
    .slice(-5);

  const latestCurrentEntry = [...currentSource]
    .sort((a, b) => str(a.visit_date).localeCompare(str(b.visit_date)))
    .at(-1) ?? {};
  const latestVitals = r((latestCurrentEntry as R).vital_signs);

  // 최신 방문 SOAP S 데이터용 (증상/노트)
  const latestVisit = latestCurrentEntry;

  const bpData = sortedHistory.map(extractBpSystolic);
  const sugarData = sortedHistory.map(extractSugar);

  // 현재값: visit_records 최신 측정값 우선
  const bpCurrent = str(latestVitals.blood_pressure)
    || str((latestCurrentEntry as R).blood_pressure)
    || '120/80';
  const sugarCurrent = String(
    num(latestVitals.blood_sugar ?? latestVitals.fasting_glucose, 0)
    || num((latestCurrentEntry as R).blood_sugar, 100)
  );
  const bpTrendUp = num(signals.systolic_delta) > 0;
  const sugarTrendUp = num(signals.blood_sugar_delta) > 0;

  const medicationAdherenceDays = num(raw.medication_adherence_days, 25);
  const adherenceRate = Math.min(100, Math.round((medicationAdherenceDays / 30) * 100));
  const adherenceData = Array(Math.max(1, sortedHistory.length)).fill(adherenceRate);

  // SOAP
  const symptoms = arr<string>(latestVisit.symptoms).join(', ');
  const chiefComplaint = str(latestVisit.chief_complaint);
  const notes = str(latestVisit.notes);
  const subjective = [chiefComplaint, symptoms, notes].filter(Boolean).join('. ');

  // HbA1c: 전체 히스토리에서 가장 최근 HbA1c 값 검색
  const latestHba1cRecord = [...sortedHistory].reverse().find(v => {
    const vs = r(v.vital_signs);
    return vs.hba1c != null || (v as R).hba1c != null;
  });
  const hba1cValue = latestHba1cRecord
    ? (num(r(latestHba1cRecord.vital_signs).hba1c) || num((latestHba1cRecord as R).hba1c))
    : num(signals.latest_hba1c);

  const objective = [
    `혈압 ${bpCurrent} mmHg`,
    `공복혈당 ${sugarCurrent} mg/dL`,
    hba1cValue ? `HbA1c ${hba1cValue}%` : null,
    `복약 순응도 ${adherenceRate}%`,
  ].filter(Boolean).join('. ');

  const actionPlan = r(data.action_plan);
  const doctorActions = arr<string>(actionPlan.doctor_actions);
  const plan = doctorActions.map((a, i) => `${i + 1}. ${a}`).join(' ');

  const systolic = num(bpCurrent.split('/')[0]);
  const anomalies: string[] = [];
  if (systolic >= 140) anomalies.push('bp');
  if (num(sugarCurrent) >= 126) anomalies.push('sugar');

  // AI Recommendation
  const isInPerson = consultationType === '대면';
  const inPersonArg = r(data.in_person_argument);
  const remoteArg = r(data.remote_argument);
  const reasoning = r(data.reasoning);

  // RAG 근거 지침
  const guidelineEvidence = arr<R>(reasoning.guideline_evidence).map(e => ({
    source: str(e.source),
    content: str(e.content),
  })).filter(e => e.content.length > 0);

  // Assessment: 여러 경로에서 순서대로 시도, 모두 없으면 위험도 기반으로 구성
  const rationaleBase =
    str(judge.rationale) ||
    str(reasoning.summary) ||
    arr<R>(judge.issue_judgments).map(j => str(j.rationale)).filter(Boolean).join(' ') ||
    (verdictLevel === 'red'
      ? `위험도 ${riskScore}점 — 주요 이상 소견이 확인되어 즉각적인 대면 진료가 필요합니다.`
      : verdictLevel === 'yellow'
      ? `위험도 ${riskScore}점 — 주의 관찰이 필요한 상태입니다.`
      : `위험도 ${riskScore}점 — 현재 상태는 비교적 안정적입니다.`);
  const evidenceRef = guidelineEvidence.length > 0
    ? ` [참조 진료지침 ${guidelineEvidence.length}건 적용]`
    : '';
  const assessment = rationaleBase + evidenceRef;

  const argList = isInPerson
    ? arr<string>(inPersonArg.arguments)
    : arr<string>(remoteArg.arguments);

  const reasons = argList.slice(0, 4).map(text => ({
    type: isInPerson
      ? (/증가|초과|악화|높|위험/.test(text) ? 'up' : 'alert')
      : 'check',
    text,
  }));

  const stats: { label: string; value: string }[] = [
    { label: '혈압', value: `${bpCurrent} mmHg` },
    { label: '공복혈당', value: `${sugarCurrent} mg/dL` },
  ];
  if (hba1cValue) stats.push({ label: 'HbA1c', value: `${hba1cValue}%` });
  stats.push({ label: '복약 순응도', value: `${adherenceRate}%` });

  return {
    consultationType,
    verdictLevel,
    riskScore,
    confidence,
    patientName: str(patient.name),
    age: num(patient.age),
    gender: str(patient.gender, 'M'),
    conditions,
    bpCurrent,
    bpTrendUp,
    bpData,
    sugarCurrent,
    sugarTrendUp,
    sugarData,
    adherenceRate,
    adherenceData,
    guidelineEvidence,
    soapNote: { subjective, objective, assessment, plan, anomalies },
    recommendation: {
      title: str(reasoning.summary),
      highlight: isInPerson ? '대면 진료가 권고' : '비대면 진료가 가능',
      reasons,
      details: assessment,
      stats,
    },
    footerAction: isInPerson ? '대면 진료 예약하기' : '비대면 상담 예약하기',
  };
}

// ── Cache helpers ────────────────────────────────────────────────────────

function loadCache(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) ?? '{}'); } catch { return {}; }
}

function saveToCache(patientId: string, s3Key: string) {
  const cache = loadCache();
  cache[patientId] = s3Key;
  localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

async function triggerPipeline(patientId: string): Promise<string> {
  const cache = loadCache();
  if (cache[patientId]) return cache[patientId];
  const res = await fetch(`${API_BASE}/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_id: patientId }),
  });
  if (!res.ok) throw new Error(`Pipeline trigger failed: ${res.status}`);
  const data = await res.json();
  if (!data.s3_key) throw new Error('s3_key not returned');
  saveToCache(patientId, data.s3_key);
  return data.s3_key;
}

async function triggerPipelineWithVitals(patientId: string, vitals: VisitVitals): Promise<string> {
  const res = await fetch(`${API_BASE}/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_id: patientId, visit_vitals: vitals }),
  });
  if (!res.ok) throw new Error(`Pipeline trigger failed: ${res.status}`);
  const data = await res.json();
  if (!data.s3_key) throw new Error('s3_key not returned');
  saveToCache(patientId, data.s3_key);
  return data.s3_key;
}

async function fetchResult(s3Key: string): Promise<R> {
  const res = await fetch(`${API_BASE}/result?s3_key=${encodeURIComponent(s3Key)}`);
  return res.json();
}

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

export async function runAndPoll(
  patientId: string,
  onDone: (verdict: LambdaVerdict) => void,
  signal?: AbortSignal,
): Promise<void> {
  const s3Key = await triggerPipeline(patientId);
  for (let i = 0; i < 40; i++) {
    if (signal?.aborted) return;
    const data = await fetchResult(s3Key);
    const meta = data._meta as R | undefined;
    const judgeData = data.judge as R | undefined;
    const status = str(data.status || meta?.status);
    // verdict_level은 top-level, _meta, 또는 judge 안에 있을 수 있음
    const verdictLevel =
      data.verdict_level || meta?.verdict_level || judgeData?.verdict_level;
    if (status === 'done' && verdictLevel) {
      onDone(parseS3Full(data));
      return;
    }
    await sleep(3000);
  }
  throw new Error('Polling timeout');
}

export function clearCache() {
  localStorage.removeItem(CACHE_KEY);
}

// ── Patient info ──────────────────────────────────────────────────────────

export type VisitVitals = {
  systolic: number | null;
  diastolic: number | null;
  blood_sugar: number | null;
  medication_status: 'well' | 'missed' | '';
  observations: string[];
  notes: string;
};

export type PatientInfo = {
  patient_id: string;
  name: string;
  age: number;
  gender: 'M' | 'F' | string;
  conditions: string[];
  medications: string[];
};

export async function fetchPatient(patientId: string): Promise<PatientInfo> {
  const res = await fetch(`${API_BASE}/patient?patient_id=${encodeURIComponent(patientId)}`);
  if (!res.ok) throw new Error(`Patient not found: ${patientId}`);
  return res.json();
}

// ── Nurse queue ───────────────────────────────────────────────────────────

export type NurseVitalsSnapshot = {
  bp: string;
  sugar: string;
};

type QueueEntry = {
  patientId: string;
  s3Key: string;
  submittedAt: string;
  vitals?: NurseVitalsSnapshot;
  fullVitals?: VisitVitals;
};

export function getNurseQueue(): QueueEntry[] {
  try { return JSON.parse(localStorage.getItem(NURSE_QUEUE_KEY) ?? '[]'); } catch { return []; }
}

export function getNurseVitals(patientId: string): NurseVitalsSnapshot | null {
  const entry = getNurseQueue().find(e => e.patientId === patientId);
  return entry?.vitals ?? null;
}

export function getNurseFullVitals(patientId: string): VisitVitals | null {
  const entry = getNurseQueue().find(e => e.patientId === patientId);
  return entry?.fullVitals ?? null;
}

function addToQueue(entry: QueueEntry) {
  const queue = getNurseQueue();
  const idx = queue.findIndex(e => e.patientId === entry.patientId);
  if (idx >= 0) queue[idx] = entry; else queue.push(entry);
  localStorage.setItem(NURSE_QUEUE_KEY, JSON.stringify(queue));
}

export async function submitAnalysis(patientId: string, vitals: VisitVitals): Promise<string> {
  const s3Key = await triggerPipelineWithVitals(patientId, vitals);
  const snapshot: NurseVitalsSnapshot = {
    bp: (vitals.systolic && vitals.diastolic) ? `${vitals.systolic}/${vitals.diastolic}` : '',
    sugar: vitals.blood_sugar ? String(vitals.blood_sugar) : '',
  };
  addToQueue({ patientId, s3Key, submittedAt: new Date().toISOString(), vitals: snapshot, fullVitals: vitals });
  return s3Key;
}
