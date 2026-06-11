const API_BASE = 'https://ky1y2zdh68.execute-api.ap-northeast-2.amazonaws.com/dev';
const CACHE_KEY = 'silversync_s3_keys';
const NURSE_QUEUE_KEY = 'silversync_nurse_queue';

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

function loadCache(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) ?? '{}'); } catch { return {}; }
}

function saveToCache(patientId: string, s3Key: string) {
  const cache = loadCache();
  cache[patientId] = s3Key;
  localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
}

// 간호사 측정값 없이 단순 트리거 (캐시 우선)
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

// 간호사 측정값과 함께 트리거 — 항상 새로운 s3_key 발급
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

async function fetchResult(s3Key: string): Promise<Record<string, unknown>> {
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
    if (data.status === 'done' && data.consultation_type && data.verdict_level) {
      onDone({
        consultationType: data.consultation_type as '대면' | '비대면',
        verdictLevel: data.verdict_level as 'red' | 'yellow' | 'green',
        riskScore: Number(data.risk_score ?? 0),
        confidence: Number(data.confidence ?? 0),
      });
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

// ── Nurse queue (localStorage bridge between Nurse and Doctor views) ───────

export type NurseVitalsSnapshot = {
  bp: string;       // "148/94" 형식, 없으면 ''
  sugar: string;    // "162" 형식, 없으면 ''
};

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

// 간호사 측정값 포함 제출 — 항상 새 파이프라인 실행
export async function submitAnalysis(patientId: string, vitals: VisitVitals): Promise<string> {
  const s3Key = await triggerPipelineWithVitals(patientId, vitals);
  const snapshot: NurseVitalsSnapshot = {
    bp: (vitals.systolic && vitals.diastolic) ? `${vitals.systolic}/${vitals.diastolic}` : '',
    sugar: vitals.blood_sugar ? String(vitals.blood_sugar) : '',
  };
  addToQueue({ patientId, s3Key, submittedAt: new Date().toISOString(), vitals: snapshot });
  return s3Key;
}
