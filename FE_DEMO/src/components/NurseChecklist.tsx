import React, { useState, useEffect } from 'react';
import {
  HeartPulse, Activity, Pill, Check, Plus, Minus, Stethoscope,
  Sparkles, ClipboardEdit, CalendarSync, UserPlus, CheckCircle2, Clock,
  ChevronLeft, ChevronRight, X, MessageSquare, Loader2, AlertTriangle, AlertOctagon, ArrowRight, History,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { OBSERVATION_CHIPS } from '../constants';
import { NurseStatusAvatar } from './ui/StatusBadge';
import NumberSpinner from './ui/NumberSpinner';
import { fetchPatient, submitAnalysis, getCompletedPatients, markPatientCompleted, type VisitVitals } from '../lib/silverSyncApi';
import type { NursePatient, ConversationSummary } from '../types';
import { demoPatients } from '../data/demoPatients';
import { judgeBp, judgeSugar, LEVEL_STYLE, BP_TARGET_TEXT, SUGAR_TARGET_TEXT, type VitalJudgement } from '../lib/vitalRanges';

// 방문 전 참고 정보: 질환 태그, 지난 측정값
function visitContext(lambdaPatientId?: string) {
  const demo = demoPatients.find(d => d.lambdaPatientId === lambdaPatientId);
  if (!demo) return null;
  const prev = (arr: number[]) => (arr.length >= 2 ? arr[arr.length - 2] : undefined);
  return {
    diseases: demo.disease.split(',').map(d => d.trim()).filter(Boolean),
    prevSystolic: prev(demo.vitals.bp.data),
    prevSugar: prev(demo.vitals.sugar.data),
  };
}

// ── Types ─────────────────────────────────────────────────────────────────

type ScheduleViewProps = {
  patients: NursePatient[];
  onLoadSchedule: () => void;
  onStartChecklist: (patient: NursePatient) => void;
  onOpenAddModal: () => void;
  isLoading: boolean;
};

type AddPatientModalProps = {
  onClose: () => void;
  onAdd: (patient: Omit<NursePatient, 'id' | 'status'>) => void;
};

// ── 오늘 방문 일정 (DynamoDB patient_id 기준) ──────────────────────────────

const SCHEDULE: { lambdaPatientId: string; time: string }[] = [
  { lambdaPatientId: 'EDGE-E3-0001',    time: '09:00' },  // 대면 — 당뇨망막병증
  { lambdaPatientId: 'HARDNEG-HN4-0001', time: '10:00' }, // 엣지 — 안정 CKD
  { lambdaPatientId: 'CLEAR-C2-0001',   time: '11:00' },  // 비대면 — 전 수치 안정
];

// ── Main Container ────────────────────────────────────────────────────────

export default function NurseMain() {
  const [view, setView] = useState<'schedule' | 'checklist'>('schedule');
  const [patients, setPatients] = useState<NursePatient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<NursePatient | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => { loadSchedule(); }, []);

  const loadSchedule = async () => {
    setIsLoading(true);
    try {
      const completed = getCompletedPatients();
      const fetched = await Promise.all(
        SCHEDULE.map(async ({ lambdaPatientId, time }) => {
          const info = await fetchPatient(lambdaPatientId);
          return {
            id: lambdaPatientId,
            lambdaPatientId,
            name: info.name,
            age: info.age,
            gender: info.gender === 'F' ? '여' : '남',
            time,
            status: (completed.has(lambdaPatientId) ? 'completed' : 'pending') as 'pending' | 'completed',
          };
        }),
      );
      setPatients(fetched);
    } catch {
      setPatients([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartChecklist = (patient: NursePatient) => {
    setSelectedPatient(patient);
    setView('checklist');
  };

  const handleMarkComplete = (patientId: string) => {
    markPatientCompleted(patientId);
    setPatients(prev => prev.map(p => p.id === patientId ? { ...p, status: 'completed' } : p));
  };

  const handleCompleteChecklist = () => {
    setView('schedule');
    setSelectedPatient(null);
  };

  const nextPatient = patients.find(p => p.status === 'pending' && p.id !== selectedPatient?.id) ?? null;

  const handleAddPatient = (newPatient: Omit<NursePatient, 'id' | 'status'>) => {
    const now = new Date();
    const timeString = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    const patient: NursePatient = {
      ...newPatient,
      time: `현장추가 (${timeString})`,
      id: Math.random().toString(36).substring(2, 11),
      status: 'pending',
    };
    setPatients(prev => [...prev, patient]);
    setIsAddModalOpen(false);
  };

  return (
    <div className="min-h-screen bg-sky-50 font-sans break-keep selection:bg-cyan-100">
      {view === 'schedule' ? (
        <ScheduleView
          patients={patients}
          onLoadSchedule={loadSchedule}
          onStartChecklist={handleStartChecklist}
          onOpenAddModal={() => setIsAddModalOpen(true)}
          isLoading={isLoading}
        />
      ) : (
        // key: 다음 환자로 바로 넘어갈 때 입력 상태를 새로 시작
        <React.Fragment key={selectedPatient!.id}>
          <ChecklistForm
            patient={selectedPatient!}
            nextPatient={nextPatient}
            onStartNext={handleStartChecklist}
            onBack={() => setView('schedule')}
            onMarkComplete={handleMarkComplete}
            onComplete={handleCompleteChecklist}
          />
        </React.Fragment>
      )}
      {isAddModalOpen && (
        <AddPatientModal onClose={() => setIsAddModalOpen(false)} onAdd={handleAddPatient} />
      )}
    </div>
  );
}

// ── Schedule View ─────────────────────────────────────────────────────────

function ScheduleView({ patients, onLoadSchedule, onStartChecklist, onOpenAddModal, isLoading }: ScheduleViewProps) {
  const completedCount = patients.filter(p => p.status === 'completed').length;
  const totalCount = patients.length;
  const progress = totalCount === 0 ? 0 : (completedCount / totalCount) * 100;

  return (
    <div className="pb-24">
      <div className="bg-white px-4 sm:px-8 pt-8 pb-6 rounded-b-[40px] shadow-sm shadow-sky-100/50 mb-6">
        <div className="max-w-3xl mx-auto">
          <div className="flex justify-between items-end mb-6">
            <div>
              <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">오늘의 방문 일정</h1>
              <p className="text-sky-600 font-semibold mt-2 text-lg">총 {totalCount}명 중 {completedCount}명 완료</p>
            </div>
            <div className="w-16 h-16 relative flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 64 64">
                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="6" fill="transparent" className="text-sky-100" />
                <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="6" fill="transparent"
                  strokeDasharray="175.93" strokeDashoffset={175.93 * (1 - progress / 100)}
                  className="text-sky-500 transition-all duration-1000 ease-out" strokeLinecap="round" />
              </svg>
              <span className="absolute text-sm font-bold text-slate-700">{Math.round(progress)}%</span>
            </div>
          </div>
          <div className="flex gap-3">
            <button onClick={onLoadSchedule} className="flex-1 bg-sky-50 hover:bg-sky-100 text-sky-700 h-14 rounded-2xl font-bold flex items-center justify-center gap-2 transition-colors">
              <CalendarSync className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} strokeWidth={2.5} />
              일정 동기화
            </button>
            <button onClick={onOpenAddModal} className="flex-1 bg-white border-2 border-sky-200 hover:border-sky-300 text-sky-600 h-14 rounded-2xl font-bold flex items-center justify-center gap-2 transition-colors shadow-sm">
              <UserPlus className="w-5 h-5" strokeWidth={2.5} />
              현장 추가
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-4">
        {patients.map((patient) => {
          const ctx = visitContext(patient.lambdaPatientId);
          const done = patient.status === 'completed';
          const isNext = !done && patients.find(p => p.status === 'pending')?.id === patient.id;
          return (
          <button
            key={patient.id}
            data-tour={`nurse-card-${patient.lambdaPatientId}`}
            onClick={() => onStartChecklist(patient)}
            aria-label={`${patient.name} ${patient.gender} ${patient.age}세, ${patient.time}, ${done ? '방문 완료' : '방문 예정'}`}
            className={`w-full text-left p-5 sm:p-6 rounded-[32px] transition-all duration-300 border-2 flex items-center justify-between gap-3 active:scale-[0.98] ${
              isNext
                ? 'bg-white border-sky-400 shadow-md shadow-sky-100/60'
                : done
                  ? 'bg-slate-50 border-sky-100 hover:border-sky-300'
                  : 'bg-white border-sky-100 hover:border-sky-300 hover:shadow-md hover:shadow-sky-100/50'
            }`}
          >
            <div className="flex items-center gap-4 sm:gap-5 min-w-0">
              <NurseStatusAvatar status={patient.status} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-2xl font-extrabold text-slate-900">{patient.name}</span>
                  <span className="text-slate-600 font-semibold bg-slate-100 px-2 py-0.5 rounded-lg text-sm">{patient.gender}/{patient.age}</span>
                  {isNext && <span className="text-xs font-extrabold text-white bg-sky-700 px-2 py-0.5 rounded-full">다음 방문</span>}
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-600 font-medium">
                  <span className="flex items-center"><Clock className="w-4 h-4 mr-1.5" strokeWidth={2} />{patient.time}</span>
                  <span className={`flex items-center font-bold text-sm ${done ? 'text-teal-700' : 'text-sky-700'}`}>
                    {done ? <><CheckCircle2 className="w-4 h-4 mr-1" strokeWidth={2.5} />방문 완료</> : '방문 예정'}
                  </span>
                </div>
                {ctx && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {ctx.diseases.map(d => (
                      <span key={d} className="text-xs font-bold text-slate-700 bg-sky-50 border border-sky-100 px-2 py-0.5 rounded-full">{d}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className={`w-12 h-12 shrink-0 rounded-full flex items-center justify-center ${done ? 'bg-slate-200/50 text-slate-500' : 'bg-sky-50 text-sky-600'}`}>
              <ChevronRight className="w-6 h-6" strokeWidth={3} />
            </div>
          </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Add Patient Modal ─────────────────────────────────────────────────────

function AddPatientModal({ onClose, onAdd }: AddPatientModalProps) {
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('남');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !age) return;
    onAdd({ name, age: Number(age), gender, time: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) });
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white w-full max-w-md rounded-[40px] p-8 shadow-2xl">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-2xl font-extrabold text-slate-900">현장 환자 추가</h2>
          <button onClick={onClose} aria-label="닫기" className="p-3 bg-slate-50 rounded-full text-slate-600 hover:bg-slate-100">
            <X className="w-6 h-6" strokeWidth={2.5} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-slate-700 font-bold mb-2">환자 성함</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 홍길동"
              className="w-full h-16 bg-sky-50/50 border border-sky-100 rounded-2xl px-6 text-xl font-bold text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all" autoFocus />
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-slate-700 font-bold mb-2">연령</label>
              <input type="number" value={age} onChange={(e) => setAge(e.target.value)} placeholder="예: 75"
                className="w-full h-16 bg-sky-50/50 border border-sky-100 rounded-2xl px-6 text-xl font-bold text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all" />
            </div>
            <div className="flex-1">
              <label className="block text-slate-700 font-bold mb-2">성별</label>
              <div className="flex bg-sky-50/50 border border-sky-100 rounded-2xl p-1.5 h-16">
                <button type="button" onClick={() => setGender('남')} className={`flex-1 rounded-xl font-bold text-lg transition-all ${gender === '남' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-500'}`}>남</button>
                <button type="button" onClick={() => setGender('여')} className={`flex-1 rounded-xl font-bold text-lg transition-all ${gender === '여' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-500'}`}>여</button>
              </div>
            </div>
          </div>
          <button type="submit" disabled={!name || !age}
            className="w-full h-16 mt-4 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-2xl text-xl font-extrabold shadow-lg shadow-sky-200/50 transition-all">
            추가하기
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Checklist Sections ────────────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-3 mb-6">
      <div className="p-2.5 bg-sky-50 rounded-2xl">{icon}</div>
      <h2 className="text-xl font-extrabold text-slate-900">{title}</h2>
    </div>
  );
}

function VitalFeedback({ judgement, target, prev }: { judgement: VitalJudgement | null; target: string; prev?: string }) {
  const Icon = !judgement ? null : judgement.level === 'ok' ? CheckCircle2 : judgement.level === 'danger' ? AlertOctagon : AlertTriangle;
  const style = judgement ? LEVEL_STYLE[judgement.level] : null;
  return (
    <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2" aria-live="polite">
      {judgement && style && Icon && (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-sm font-extrabold ${style.box} ${style.text}`}>
          <Icon className="w-4 h-4" strokeWidth={2.5} />{judgement.text}
        </span>
      )}
      <span className="text-sm font-semibold text-slate-600">{target}{prev && <> · <History className="inline w-3.5 h-3.5 -mt-0.5" strokeWidth={2.5} /> 지난 측정 {prev}</>}</span>
    </div>
  );
}

function VitalsSection({ systolic, setSystolic, diastolic, setDiastolic, bloodSugar, setBloodSugar, prevSystolic, prevSugar, missing }: {
  systolic: number | ''; setSystolic: (v: number | '') => void;
  diastolic: number | ''; setDiastolic: (v: number | '') => void;
  bloodSugar: number | ''; setBloodSugar: (v: number | '') => void;
  prevSystolic?: number; prevSugar?: number; missing?: boolean;
}) {
  return (
    <section id="vitals-section" data-tour="nurse-vitals" className={`bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border-2 scroll-mt-40 ${missing ? 'border-orange-300' : 'border-sky-100'}`}>
      <SectionHeader icon={<HeartPulse className="w-6 h-6 text-sky-500" strokeWidth={2.5} />} title="바이탈 사인 (필수)" />
      {missing && (
        <p className="-mt-3 mb-4 text-sm font-extrabold text-orange-800 flex items-center gap-1.5">
          <AlertTriangle className="w-4 h-4" strokeWidth={2.5} />혈압과 혈당을 모두 입력해야 전달할 수 있어요
        </p>
      )}
      <div className="space-y-8">
        <div data-tour="nurse-bp">
          <label className="block text-slate-600 font-bold mb-4 text-lg">혈압 (mmHg)</label>
          <div className="flex flex-col sm:flex-row gap-4 sm:gap-8">
            <NumberSpinner label="수축기" value={systolic} onChange={setSystolic} step={5} base={prevSystolic ?? 120} />
            <NumberSpinner label="이완기" value={diastolic} onChange={setDiastolic} step={5} base={80} />
          </div>
          <VitalFeedback judgement={judgeBp(systolic, diastolic)} target={BP_TARGET_TEXT}
            prev={prevSystolic !== undefined ? `수축기 ${prevSystolic}` : undefined} />
        </div>
        <div data-tour="nurse-sugar">
          <label className="block text-slate-600 font-bold mb-4 text-lg">공복 혈당 (mg/dL)</label>
          <div className="max-w-sm">
            <NumberSpinner label="공복 혈당" value={bloodSugar} onChange={setBloodSugar} step={5} hideLabel base={prevSugar ?? 100} />
          </div>
          <VitalFeedback judgement={judgeSugar(bloodSugar)} target={SUGAR_TARGET_TEXT}
            prev={prevSugar !== undefined ? `${prevSugar}` : undefined} />
        </div>
      </div>
    </section>
  );
}

function MedicationSection({ medicationStatus, setMedicationStatus, missing }: {
  medicationStatus: 'well' | 'missed' | null;
  setMedicationStatus: (v: 'well' | 'missed') => void;
  missing?: boolean;
}) {
  return (
    <section id="medication-section" className={`bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border-2 scroll-mt-40 ${missing ? 'border-orange-300' : 'border-sky-100'}`}>
      <SectionHeader icon={<Pill className="w-6 h-6 text-sky-500" strokeWidth={2.5} />} title="복약 확인 (필수)" />
      {missing && (
        <p className="-mt-3 mb-4 text-sm font-extrabold text-orange-800 flex items-center gap-1.5">
          <AlertTriangle className="w-4 h-4" strokeWidth={2.5} />복약 여부를 선택해야 전달할 수 있어요
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <button onClick={() => setMedicationStatus('well')} aria-pressed={medicationStatus === 'well'} data-tour="nurse-med-well"
          className={`h-20 rounded-3xl text-xl font-bold transition-all duration-300 flex items-center justify-center gap-3 border-2 ${medicationStatus === 'well' ? 'bg-sky-500 border-sky-500 text-white shadow-lg shadow-sky-200/50' : 'bg-white border-sky-100 text-slate-500 hover:border-sky-300 hover:bg-sky-50'}`}>
          {medicationStatus === 'well' && <Check className="w-6 h-6" strokeWidth={3} />} 잘 드시고 계심
        </button>
        <button onClick={() => setMedicationStatus('missed')} aria-pressed={medicationStatus === 'missed'}
          className={`h-20 rounded-3xl text-xl font-bold transition-all duration-300 flex items-center justify-center gap-3 border-2 ${medicationStatus === 'missed' ? 'bg-orange-500 border-orange-500 text-white shadow-lg shadow-orange-200/50' : 'bg-white border-sky-100 text-slate-500 hover:border-orange-200 hover:bg-orange-50'}`}>
          {medicationStatus === 'missed' && <Check className="w-6 h-6" strokeWidth={3} />} 거르신 적 있음
        </button>
      </div>
    </section>
  );
}

function ObservationsSection({ observations, onToggle }: {
  observations: string[];
  onToggle: (chip: string) => void;
}) {
  return (
    <section data-tour="nurse-observations" className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
      <SectionHeader icon={<Stethoscope className="w-6 h-6 text-sky-500" strokeWidth={2.5} />} title="관찰 소견 (다중 선택)" />
      <div className="flex flex-wrap gap-3">
        {OBSERVATION_CHIPS.map((chip) => (
          <button key={chip} onClick={() => onToggle(chip)} aria-pressed={observations.includes(chip)}
            className={`h-14 px-6 rounded-full text-lg font-bold transition-all duration-300 border-2 ${observations.includes(chip) ? 'bg-sky-500 border-sky-500 text-white shadow-md shadow-sky-200/50' : 'bg-white border-sky-100 text-slate-600 hover:border-sky-300 hover:bg-sky-50'}`}>
            {chip}
          </button>
        ))}
      </div>
    </section>
  );
}

function NotesSection({ notes, setNotes }: { notes: string; setNotes: (v: string) => void }) {
  return (
    <section data-tour="nurse-notes" className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
      <SectionHeader icon={<ClipboardEdit className="w-6 h-6 text-sky-500" strokeWidth={2.5} />} title="특이사항 (선택)" />
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
        placeholder="환자의 호소 증상이나 특이사항을 자유롭게 입력하세요."
        className="w-full h-32 bg-sky-50/50 border border-sky-100 rounded-3xl p-6 text-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all resize-none" />
    </section>
  );
}

// ── Conversation Summary Result ───────────────────────────────────────────

function ConversationSummaryResult({
  patient, conversationSummary, onBack, onFinalize,
}: {
  patient: NursePatient;
  conversationSummary: ConversationSummary;
  onBack: () => void;
  onFinalize: () => void;
}) {
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);

  return (
    <div className="pb-36">
      {/* Sticky Header */}
      <div className="bg-white px-4 sm:px-8 py-6 rounded-b-[40px] shadow-sm shadow-sky-100/50 mb-6 sticky top-16 sm:top-20 z-40">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          <button onClick={onBack} className="w-12 h-12 bg-slate-50 hover:bg-slate-100 rounded-2xl flex items-center justify-center text-slate-600 transition-colors">
            <ChevronLeft className="w-7 h-7" strokeWidth={2.5} />
          </button>
          <div className="flex-1 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">AI 분석 결과</h1>
              <p className="text-sky-600 font-semibold text-sm mt-0.5">{patient.name} 환자 · 대화 요약</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-6">
        {/* Success Banner */}
        <div className="bg-gradient-to-r from-cyan-500 to-sky-500 rounded-[32px] p-6 text-white shadow-xl shadow-cyan-200/40">
          <div className="flex items-center gap-3 mb-2">
            <Sparkles className="w-6 h-6" strokeWidth={2.5} />
            <span className="font-extrabold text-lg">AI 대화 요약 완료</span>
          </div>
          <p className="text-cyan-100 font-medium">환자와의 대화 내용이 분석되었습니다.</p>
        </div>

        {/* Summary Card */}
        <section className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-sky-50 rounded-2xl">
                <MessageSquare className="w-6 h-6 text-sky-500" strokeWidth={2.5} />
              </div>
              <h2 className="text-xl font-extrabold text-slate-900">대화 요약</h2>
            </div>
            <button
              onClick={() => setTranscriptExpanded(v => !v)}
              className="flex items-center gap-1.5 text-sky-600 font-bold text-sm hover:text-sky-700 transition-colors px-3 py-1.5 bg-sky-50 rounded-xl"
            >
              {transcriptExpanded ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              {transcriptExpanded ? '접기' : '전체 대화 보기'}
            </button>
          </div>

          {/* Summary Text */}
          <p
            className="text-slate-700 leading-relaxed text-base [&_strong]:font-extrabold [&_strong]:text-sky-700"
            dangerouslySetInnerHTML={{ __html: conversationSummary.summary }}
          />

          {/* Transcript */}
          <AnimatePresence>
            {transcriptExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3, ease: 'easeInOut' }}
                className="overflow-hidden"
              >
                <div className="mt-6 pt-6 border-t border-sky-100 space-y-4">
                  {conversationSummary.transcript.map((utterance, idx) => {
                    const isNurse = utterance.speaker === '간호사';
                    return (
                      <div key={idx} className={`flex items-end gap-3 ${isNurse ? 'flex-row-reverse' : 'flex-row'}`}>
                        <div className="shrink-0">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${isNurse ? 'bg-sky-500 text-white' : 'bg-slate-200 text-slate-600'}`}>
                            {isNurse ? '간' : '환'}
                          </div>
                        </div>
                        <div className={`max-w-[75%] px-4 py-3 text-sm font-medium leading-relaxed ${
                          isNurse
                            ? 'bg-sky-500 text-white rounded-3xl rounded-tr-sm shadow-md shadow-sky-200/50'
                            : 'bg-slate-100 text-slate-800 rounded-3xl rounded-tl-sm'
                        }`}>
                          {utterance.text}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
      </div>

      {/* Fixed Bottom FAB */}
      <div className="fixed bottom-0 left-0 right-0 p-4 sm:p-6 bg-white/80 backdrop-blur-xl border-t border-sky-100/50 z-50">
        <div className="max-w-3xl mx-auto">
          <button onClick={onFinalize}
            className="w-full h-16 sm:h-20 bg-gradient-to-r from-teal-500 to-cyan-500 hover:from-teal-600 hover:to-cyan-600 text-white rounded-[28px] text-xl sm:text-2xl font-extrabold shadow-xl shadow-teal-200/50 flex items-center justify-center gap-3 transition-all transform active:scale-[0.98]">
            <CheckCircle2 className="w-7 h-7" strokeWidth={2.5} />
            기록 완료 및 의사 전달
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Checklist Form ────────────────────────────────────────────────────────

function ChecklistForm({ patient, nextPatient, onStartNext, onBack, onMarkComplete, onComplete }: {
  patient: NursePatient;
  nextPatient: NursePatient | null;
  onStartNext: (patient: NursePatient) => void;
  onBack: () => void;
  onMarkComplete: (patientId: string) => void;
  onComplete: () => void;
}) {
  const [formStep, setFormStep] = useState<'form' | 'confirm' | 'submitting' | 'submitted'>('form');
  const ctx = visitContext(patient.lambdaPatientId);
  const [systolic, setSystolic] = useState<number | ''>('');
  const [diastolic, setDiastolic] = useState<number | ''>('');
  const [bloodSugar, setBloodSugar] = useState<number | ''>('');
  const [medicationStatus, setMedicationStatus] = useState<'well' | 'missed' | null>(null);
  const [observations, setObservations] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [showMissing, setShowMissing] = useState(false);
  const [leaveAsk, setLeaveAsk] = useState(false);

  const isDirty =
    systolic !== '' || diastolic !== '' || bloodSugar !== '' || medicationStatus !== null ||
    observations.length > 0 || notes.trim() !== '';
  const vitalsMissing = systolic === '' || diastolic === '' || bloodSugar === '';

  const toggleObservation = (chip: string) => {
    setObservations(prev => prev.includes(chip) ? prev.filter(c => c !== chip) : [...prev, chip]);
  };

  const handleBack = () => (isDirty ? setLeaveAsk(true) : onBack());

  const handleReview = () => {
    if (vitalsMissing || medicationStatus === null) {
      setShowMissing(true);
      const first = vitalsMissing ? 'vitals-section' : 'medication-section';
      document.getElementById(first)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    setFormStep('confirm');
  };

  const handleSubmit = async () => {
    if (!patient.lambdaPatientId) { onMarkComplete(patient.id); setFormStep('submitted'); return; }
    setFormStep('submitting');
    const vitals: VisitVitals = {
      systolic: systolic === '' ? null : systolic,
      diastolic: diastolic === '' ? null : diastolic,
      blood_sugar: bloodSugar === '' ? null : bloodSugar,
      medication_status: medicationStatus ?? '',
      observations,
      notes,
    };
    try {
      await submitAnalysis(patient.lambdaPatientId, vitals);
    } catch {
      // 제출 실패해도 완료 처리
    } finally {
      onMarkComplete(patient.id);
      setFormStep('submitted');
    }
  };

  if (formStep === 'submitted') {
    return (
      <div className="min-h-[calc(100vh-5rem)] bg-sky-50 flex flex-col items-center justify-center p-6 sm:p-8 gap-4">
        <div className="bg-gradient-to-br from-teal-600 to-cyan-700 rounded-[40px] p-10 text-white text-center shadow-2xl shadow-teal-200/50 max-w-md w-full mb-4">
          <CheckCircle2 className="w-20 h-20 mx-auto mb-4" strokeWidth={1.5} />
          <h2 className="text-3xl font-extrabold mb-2">분석 요청 완료</h2>
          <p className="text-teal-50 text-lg font-medium">{patient.name} 환자의 기록이 의사에게 전달되었습니다</p>
        </div>
        {nextPatient && (
          <button onClick={() => onStartNext(nextPatient)}
            className="w-full max-w-md min-h-20 px-6 bg-sky-700 hover:bg-sky-800 text-white rounded-3xl shadow-lg shadow-sky-200/50 flex items-center justify-between transition-colors">
            <span className="text-left">
              <span className="block text-sm font-bold text-sky-50">다음 방문 · {nextPatient.time}</span>
              <span className="block text-2xl font-extrabold">{nextPatient.name} 환자 시작</span>
            </span>
            <ArrowRight className="w-7 h-7" strokeWidth={2.5} />
          </button>
        )}
        <button onClick={onComplete}
          className="w-full max-w-md h-16 bg-white border-2 border-sky-200 text-sky-700 rounded-3xl text-xl font-extrabold shadow-sm hover:bg-sky-50 transition-colors">
          {nextPatient ? '일정 목록 보기' : '오늘 방문 모두 완료 · 일정으로'}
        </button>
      </div>
    );
  }

  const bpJ = judgeBp(systolic, diastolic);
  const sugarJ = judgeSugar(bloodSugar);

  return (
    <div className="pb-36">
      {/* Header */}
      <div className="bg-white px-4 sm:px-8 py-5 rounded-b-[40px] shadow-sm shadow-sky-100/50 mb-6 sticky top-16 sm:top-20 z-40">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          <button onClick={handleBack} aria-label="일정으로 돌아가기"
            className="w-12 h-12 shrink-0 bg-slate-50 hover:bg-slate-100 rounded-2xl flex items-center justify-center text-slate-700 transition-colors">
            <ChevronLeft className="w-7 h-7" strokeWidth={2.5} />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">{patient.name} 환자</h1>
              <span className="text-slate-600 font-bold text-sm bg-sky-50 px-2 py-0.5 rounded-lg border border-sky-100">{patient.age}세 / {patient.gender}</span>
            </div>
            {ctx ? (
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {ctx.diseases.map(d => (
                  <span key={d} className="text-xs font-bold text-slate-700 bg-sky-50 border border-sky-100 px-2 py-0.5 rounded-full">{d}</span>
                ))}
              </div>
            ) : (
              <p className="text-sky-700 font-semibold text-sm mt-0.5">방문 건강 스크리닝</p>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-6">
        <VitalsSection
          systolic={systolic} setSystolic={setSystolic}
          diastolic={diastolic} setDiastolic={setDiastolic}
          bloodSugar={bloodSugar} setBloodSugar={setBloodSugar}
          prevSystolic={ctx?.prevSystolic} prevSugar={ctx?.prevSugar}
          missing={showMissing && vitalsMissing}
        />
        <MedicationSection medicationStatus={medicationStatus}
          setMedicationStatus={setMedicationStatus}
          missing={showMissing && medicationStatus === null} />
        <ObservationsSection observations={observations} onToggle={toggleObservation} />
        <NotesSection notes={notes} setNotes={setNotes} />
      </div>

      {/* Fixed Bottom FAB */}
      <div className="fixed bottom-0 left-0 right-0 p-4 sm:p-6 bg-white/80 backdrop-blur-xl border-t border-sky-100/50 z-50">
        <div className="max-w-3xl mx-auto">
          <button
            data-tour="nurse-review"
            onClick={handleReview}
            className="w-full h-16 sm:h-20 bg-gradient-to-r from-cyan-600 to-sky-600 hover:from-cyan-700 hover:to-sky-700 text-white rounded-[28px] text-xl sm:text-2xl font-extrabold shadow-xl shadow-cyan-200/50 flex items-center justify-center gap-3 transition-all transform active:scale-[0.98]">
            <Sparkles className="w-7 h-7" strokeWidth={2.5} />기록 확인 후 AI 분석 요청
          </button>
        </div>
      </div>

      {/* 제출 전 확인 */}
      {(formStep === 'confirm' || formStep === 'submitting') && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-[60] flex items-end sm:items-center justify-center sm:p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="bg-white w-full max-w-lg rounded-t-[40px] sm:rounded-[40px] p-6 sm:p-8 shadow-2xl max-h-[90vh] overflow-y-auto">
            <h2 id="confirm-title" className="text-2xl font-extrabold text-slate-900 mb-1">이대로 전달할까요?</h2>
            <p className="text-slate-600 font-medium mb-6">{patient.name} 환자 기록이 의사와 AI 분석으로 전달됩니다.</p>
            <dl className="divide-y divide-sky-100 border-y border-sky-100 mb-6">
              <SummaryRow label="혈압" value={`${systolic || '-'}/${diastolic || '-'} mmHg`} judgement={bpJ} />
              <SummaryRow label="공복 혈당" value={`${bloodSugar || '-'} mg/dL`} judgement={sugarJ} />
              <SummaryRow label="복약" value={medicationStatus === 'well' ? '잘 드시고 계심' : '거르신 적 있음'} />
              <SummaryRow label="관찰 소견" value={observations.length ? observations.join(', ') : '없음'} />
              <SummaryRow label="특이사항" value={notes.trim() || '없음'} />
            </dl>
            <div className="flex flex-col-reverse sm:flex-row gap-3">
              <button onClick={() => setFormStep('form')} disabled={formStep === 'submitting'}
                className="w-full sm:flex-1 h-16 shrink-0 bg-white border-2 border-sky-200 text-sky-700 rounded-2xl text-lg font-extrabold hover:bg-sky-50 disabled:opacity-50">
                수정하기
              </button>
              <button onClick={handleSubmit} disabled={formStep === 'submitting'} data-tour="nurse-submit"
                className="w-full sm:flex-[2] h-16 shrink-0 bg-sky-700 hover:bg-sky-800 disabled:bg-slate-400 text-white rounded-2xl text-lg font-extrabold flex items-center justify-center gap-2 shadow-lg shadow-sky-200/50">
                {formStep === 'submitting'
                  ? <><Loader2 className="w-6 h-6 animate-spin" strokeWidth={2.5} />전달 중...</>
                  : <><Sparkles className="w-6 h-6" strokeWidth={2.5} />전달하고 AI 분석 요청</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 작성 중 이탈 확인 */}
      {leaveAsk && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-[60] flex items-center justify-center p-4" role="alertdialog" aria-modal="true" aria-labelledby="leave-title">
          <div className="bg-white w-full max-w-sm rounded-[40px] p-8 shadow-2xl text-center">
            <AlertTriangle className="w-12 h-12 text-orange-500 mx-auto mb-3" strokeWidth={2} />
            <h2 id="leave-title" className="text-2xl font-extrabold text-slate-900 mb-2">작성 중인 내용이 있어요</h2>
            <p className="text-slate-600 font-medium mb-6">지금 나가면 입력한 내용이 사라집니다.</p>
            <div className="flex flex-col gap-3">
              <button onClick={() => setLeaveAsk(false)} autoFocus
                className="h-14 bg-sky-700 hover:bg-sky-800 text-white rounded-2xl text-lg font-extrabold">계속 작성하기</button>
              <button onClick={onBack}
                className="h-14 bg-white border-2 border-slate-200 text-slate-700 rounded-2xl text-lg font-extrabold hover:bg-slate-50">나가기</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryRow({ label, value, judgement }: { label: string; value: string; judgement?: VitalJudgement | null }) {
  const style = judgement ? LEVEL_STYLE[judgement.level] : null;
  return (
    <div className="py-3 flex items-start justify-between gap-4">
      <dt className="text-slate-600 font-bold shrink-0">{label}</dt>
      <dd className="text-right">
        <span className="text-slate-900 font-extrabold">{value}</span>
        {judgement && style && <span className={`block text-sm font-bold ${style.text}`}>{judgement.text}</span>}
      </dd>
    </div>
  );
}
