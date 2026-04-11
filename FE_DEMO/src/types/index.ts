// ── Status ──────────────────────────────────────────────────────────────
export type DocPatientStatus = 'orange' | 'amber' | 'teal';
export type NursePatientStatus = 'pending' | 'completed';

// ── Theme ────────────────────────────────────────────────────────────────
export type StatusTheme = {
  gradient: string;
  border: string;
  iconColor: string;
  labelColor: string;
  highlightColor: string;
  detailsButtonColor: string;
  detailBorder: string;
  detailBg: string;
  detailStatColor: string;
  footerBtn1: string;
  footerBtn2: string;
};

// ── Vitals ───────────────────────────────────────────────────────────────
export type VitalSeries = {
  current: string;
  trend?: string;
  trendUp?: boolean;
  status?: string;
  data: number[];
};

// ── Conversation & SOAP (Phase 2) ─────────────────────────────────────────
export type ConversationSummary = {
  summary: string; // may contain <strong> HTML
  transcript: { speaker: '간호사' | '환자'; text: string }[];
};

export type SoapNote = {
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  anomalies: string[];
};

// ── Doctor Patient ────────────────────────────────────────────────────────
export type DocPatient = {
  id: number;
  name: string;
  age: number;
  gender: string;
  time: string;
  status: DocPatientStatus;
  disease: string;
  aiRecommendation: {
    title: string;
    highlight: string;
    reasons: { type: string; text: string }[];
    details: string;
    stats: { label: string; value: string }[];
  };
  vitals: {
    bp: VitalSeries;
    sugar: VitalSeries;
    adherence: VitalSeries;
  };
  footerAction: string;
  conversationSummary?: ConversationSummary;
  soapNote?: SoapNote;
};

// ── Nurse Patient ─────────────────────────────────────────────────────────
export type NursePatient = {
  id: string;
  name: string;
  age: number;
  gender: string;
  time: string;
  status: NursePatientStatus;
};
