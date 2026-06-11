const API_BASE = 'https://ky1y2zdh68.execute-api.ap-northeast-2.amazonaws.com/dev';
const NURSE_QUEUE_KEY = 'silversync_nurse_queue';

// ── 데모 모드 ─────────────────────────────────────────────────────────────
// true: API 호출 없이 하드코딩된 판정을 5초 뒤 반환
const DEMO_MODE = true;

const DEMO_VERDICTS: Record<string, LambdaVerdict> = {
  'EDGE-E3-0001': {
    consultationType: '대면',
    verdictLevel: 'red',
    riskScore: 72,
    confidence: 85,
  },
  'HARDNEG-HN4-0001': {
    consultationType: '비대면',
    verdictLevel: 'green',
    riskScore: 30,
    confidence: 80,
  },
  'CLEAR-C2-0001': {
    consultationType: '비대면',
    verdictLevel: 'green',
    riskScore: 30,
    confidence: 85,
  },
};

// ── Types ─────────────────────────────────────────────────────────────────

export type LambdaVerdict = {
  consultationType: '대면' | '비대면';
  verdictLevel: 'red' | 'yellow' | 'green';
  riskScore: number;
  confidence: number;
};

export type LambdaStatus =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'done'; verdict: LambdaVerdict }
  | { type: 'error'; message?: string };

export type VisitVitals = {
  systolic: number | null;
  diastolic: number | null;
  blood_sugar: number | null;
  medication_status: 'well' | 'missed' | '';
  observations: string[];
  notes: string;
};

export type NurseVitalsSnapshot = {
  bp: string;
  sugar: string;
};

// ── Nurse queue ───────────────────────────────────────────────────────────

type QueueEntry = {
  patientId: string;
  s3Key: string;
  submittedAt: string;
  vitals?: NurseVitalsSnapshot;
};

export function getNurseQueue(): QueueEntry[] {
  try { return JSON.parse(localStorage.getItem(NURSE_QUEUE_KEY) ?? '[]'); } catch { return []; }
}

export function getNurseVitals(patientId: string): NurseVitalsSnapshot | null {
  const entry = getNurseQueue().find(e => e.patientId === patientId);
  return entry?.vitals ?? null;
}

function addToQueue(entry: QueueEntry) {
  const queue = getNurseQueue();
  const idx = queue.findIndex(e => e.patientId === entry.patientId);
  if (idx >= 0) queue[idx] = entry; else queue.push(entry);
  localStorage.setItem(NURSE_QUEUE_KEY, JSON.stringify(queue));
}

export async function submitAnalysis(patientId: string, vitals: VisitVitals): Promise<string> {
  const snapshot: NurseVitalsSnapshot = {
    bp: (vitals.systolic && vitals.diastolic) ? `${vitals.systolic}/${vitals.diastolic}` : '',
    sugar: vitals.blood_sugar ? String(vitals.blood_sugar) : '',
  };

  if (DEMO_MODE) {
    // 데모: API 호출 없이 즉시 큐에 추가
    addToQueue({ patientId, s3Key: `demo/${patientId}`, submittedAt: new Date().toISOString(), vitals: snapshot });
    return `demo/${patientId}`;
  }

  const res = await fetch(`${API_BASE}/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_id: patientId, visit_vitals: vitals }),
  });
  if (!res.ok) throw new Error(`Pipeline trigger failed: ${res.status}`);
  const data = await res.json();
  if (!data.s3_key) throw new Error('s3_key not returned');
  addToQueue({ patientId, s3Key: data.s3_key, submittedAt: new Date().toISOString(), vitals: snapshot });
  return data.s3_key;
}

// ── Poll ──────────────────────────────────────────────────────────────────

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

export async function runAndPoll(
  patientId: string,
  onDone: (verdict: LambdaVerdict) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (DEMO_MODE) {
    // 데모: 5초 뒤 하드코딩된 판정 반환
    await sleep(5000);
    if (signal?.aborted) return;
    const verdict = DEMO_VERDICTS[patientId];
    if (verdict) onDone(verdict);
    return;
  }

  // 실제 모드: S3 폴링
  const cache = loadCache();
  const s3Key = cache[patientId];
  if (!s3Key) throw new Error('No s3Key in cache');

  for (let i = 0; i < 60; i++) {
    if (signal?.aborted) return;
    const res = await fetch(`${API_BASE}/result?s3_key=${encodeURIComponent(s3Key)}`);
    const data = await res.json();
    if (data.status === 'done' && data.consultation_type && data.verdict_level) {
      onDone({
        consultationType: data.consultation_type as '대면' | '비대면',
        verdictLevel: data.verdict_level as 'red' | 'yellow' | 'green',
        riskScore: Number(data.risk_score ?? 0),
        confidence: Number(data.confidence ?? 0),
      });
      return;
    }
    await sleep(5000);
  }
  throw new Error('Polling timeout');
}

function loadCache(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem('silversync_s3_keys') ?? '{}'); } catch { return {}; }
}

// ── Patient info ──────────────────────────────────────────────────────────

export type PatientInfo = {
  patient_id: string;
  name: string;
  age: number;
  gender: 'M' | 'F' | string;
  conditions: string[];
  medications: string[];
};

const DEMO_PATIENTS: Record<string, PatientInfo> = {
  'EDGE-E3-0001': { patient_id: 'EDGE-E3-0001', name: '홍영희', age: 66, gender: 'F', conditions: ['당뇨', '고혈압'], medications: [] },
  'HARDNEG-HN4-0001': { patient_id: 'HARDNEG-HN4-0001', name: '홍길동', age: 75, gender: 'M', conditions: ['당뇨', '고혈압', '만성콩팥병'], medications: [] },
  'CLEAR-C2-0001': { patient_id: 'CLEAR-C2-0001', name: '박대호', age: 74, gender: 'M', conditions: ['당뇨', '고혈압'], medications: [] },
};

export async function fetchPatient(patientId: string): Promise<PatientInfo> {
  if (DEMO_MODE) {
    const patient = DEMO_PATIENTS[patientId];
    if (patient) return patient;
    throw new Error(`Demo patient not found: ${patientId}`);
  }
  const res = await fetch(`${API_BASE}/patient?patient_id=${encodeURIComponent(patientId)}`);
  if (!res.ok) throw new Error(`Patient not found: ${patientId}`);
  return res.json();
}

// ── Nurse completion persistence ──────────────────────────────────────────

const NURSE_COMPLETED_KEY = 'silversync_nurse_completed';

export function getCompletedPatients(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(NURSE_COMPLETED_KEY) ?? '[]')); } catch { return new Set(); }
}

export function markPatientCompleted(patientId: string) {
  const set = getCompletedPatients();
  set.add(patientId);
  localStorage.setItem(NURSE_COMPLETED_KEY, JSON.stringify([...set]));
}

export function clearCache() {
  localStorage.removeItem('silversync_s3_keys');
  localStorage.removeItem(NURSE_QUEUE_KEY);
  localStorage.removeItem(NURSE_COMPLETED_KEY);
}
