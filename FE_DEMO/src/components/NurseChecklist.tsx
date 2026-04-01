import React, { useState, useEffect } from 'react';
import {
  HeartPulse, Activity, Pill, Check, Plus, Minus, User, Stethoscope,
  Sparkles, ClipboardEdit, CalendarSync, UserPlus, CheckCircle2, Clock,
  ChevronLeft, ChevronRight, X
} from 'lucide-react';

// --- Types & Mock Data ---
type Patient = {
  id: string;
  name: string;
  age: number;
  gender: string;
  time: string;
  status: 'pending' | 'completed';
};

type ScheduleViewProps = {
  patients: Patient[];
  onLoadSchedule: () => void;
  onStartChecklist: (patient: Patient) => void;
  onOpenAddModal: () => void;
  isLoading: boolean;
};

type AddPatientModalProps = {
  onClose: () => void;
  onAdd: (patient: Omit<Patient, 'id' | 'status'>) => void;
};

const INITIAL_PATIENTS: Patient[] = [
  { id: '1', name: '김덕배', age: 72, gender: '남', time: '09:30', status: 'completed' },
  { id: '2', name: '이순자', age: 68, gender: '여', time: '11:00', status: 'pending' },
  { id: '3', name: '박상철', age: 75, gender: '남', time: '13:30', status: 'pending' },
];

const OBSERVATION_CHIPS = [
  '안색 양호', '부종 관찰', '인지 저하 의심', '거동 불편',
  '식욕 부진', '수면 장애', '어지러움 호소', '호흡 가쁨', '피부 건조'
];

// --- Main Container Component ---
export default function NurseMain() {
  const [view, setView] = useState<'schedule' | 'checklist'>('schedule');
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    loadSchedule();
  }, []);

  const loadSchedule = () => {
    setIsLoading(true);
    setTimeout(() => {
      setPatients(INITIAL_PATIENTS);
      setIsLoading(false);
    }, 600);
  };

  const handleStartChecklist = (patient: Patient) => {
    setSelectedPatient(patient);
    setView('checklist');
  };

  const handleCompleteChecklist = () => {
    if (selectedPatient) {
      setPatients(prev => prev.map(p =>
        p.id === selectedPatient.id ? { ...p, status: 'completed' } : p
      ));
    }
    setView('schedule');
    setSelectedPatient(null);
  };

  const handleAddPatient = (newPatient: Omit<Patient, 'id' | 'status'>) => {
    const patient: Patient = {
      ...newPatient,
      id: Math.random().toString(36).substring(2, 11),
      status: 'pending'
    };
    setPatients(prev => [...prev, patient]);
    setIsAddModalOpen(false);
  };

  return (
    <div className="min-h-screen bg-sky-50 font-sans selection:bg-cyan-100">
      {view === 'schedule' ? (
        <ScheduleView
          patients={patients}
          onLoadSchedule={loadSchedule}
          onStartChecklist={handleStartChecklist}
          onOpenAddModal={() => setIsAddModalOpen(true)}
          isLoading={isLoading}
        />
      ) : (
        <ChecklistForm
          patient={selectedPatient!}
          onBack={() => setView('schedule')}
          onComplete={handleCompleteChecklist}
        />
      )}

      {isAddModalOpen && (
        <AddPatientModal
          onClose={() => setIsAddModalOpen(false)}
          onAdd={handleAddPatient}
        />
      )}
    </div>
  );
}

// --- Schedule View Component ---
function ScheduleView({ patients, onLoadSchedule, onStartChecklist, onOpenAddModal, isLoading }: ScheduleViewProps) {
  const completedCount = patients.filter(p => p.status === 'completed').length;
  const totalCount = patients.length;
  const progress = totalCount === 0 ? 0 : (completedCount / totalCount) * 100;

  return (
    <div className="pb-24">
      {/* Header */}
      <div className="bg-white px-4 sm:px-8 pt-8 pb-6 rounded-b-[40px] shadow-sm shadow-sky-100/50 mb-6 sticky top-0 z-30">
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
            <button
              onClick={onLoadSchedule}
              className="flex-1 bg-sky-50 hover:bg-sky-100 text-sky-700 h-14 rounded-2xl font-bold flex items-center justify-center gap-2 transition-colors"
            >
              <CalendarSync className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} strokeWidth={2.5} />
              일정 동기화
            </button>
            <button
              onClick={onOpenAddModal}
              className="flex-1 bg-white border-2 border-sky-200 hover:border-sky-300 text-sky-600 h-14 rounded-2xl font-bold flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              <UserPlus className="w-5 h-5" strokeWidth={2.5} />
              현장 추가
            </button>
          </div>
        </div>
      </div>

      {/* Patient List */}
      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-4">
        {patients.map((patient) => (
          <button
            key={patient.id}
            onClick={() => onStartChecklist(patient)}
            className={`w-full text-left p-6 rounded-[32px] transition-all duration-300 border-2 flex items-center justify-between ${
              patient.status === 'completed'
                ? 'bg-slate-50 border-sky-100 hover:border-sky-300 hover:shadow-md hover:shadow-sky-100/50 active:scale-[0.98]'
                : 'bg-white border-sky-100 hover:border-sky-300 hover:shadow-md hover:shadow-sky-100/50 active:scale-[0.98]'
            }`}
          >
            <div className="flex items-center gap-5">
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
                patient.status === 'completed' ? 'bg-teal-100 text-teal-600' : 'bg-sky-100 text-sky-600'
              }`}>
                {patient.status === 'completed'
                  ? <CheckCircle2 className="w-7 h-7" strokeWidth={2.5} />
                  : <User className="w-7 h-7" strokeWidth={2.5} />
                }
              </div>
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <span className="text-2xl font-extrabold text-slate-900">{patient.name}</span>
                  <span className="text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded-lg text-sm">
                    {patient.gender}/{patient.age}
                  </span>
                </div>
                <div className="flex items-center text-slate-500 font-medium">
                  <Clock className="w-4 h-4 mr-1.5" strokeWidth={2} />
                  {patient.time}
                </div>
              </div>
            </div>

            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
              patient.status === 'completed' ? 'bg-slate-200/50 text-slate-500' : 'bg-sky-50 text-sky-500'
            }`}>
              <ChevronRight className="w-6 h-6" strokeWidth={3} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// --- Add Patient Modal ---
function AddPatientModal({ onClose, onAdd }: AddPatientModalProps) {
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState('남');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !age) return;

    const now = new Date();
    const timeString = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

    onAdd({ name, age: Number(age), gender, time: `현장추가 (${timeString})` });
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white w-full max-w-md rounded-[40px] p-8 shadow-2xl">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-2xl font-extrabold text-slate-900">현장 환자 추가</h2>
          <button onClick={onClose} className="p-2 bg-slate-50 rounded-full text-slate-500 hover:bg-slate-100">
            <X className="w-6 h-6" strokeWidth={2.5} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-slate-700 font-bold mb-2">환자 성함</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 홍길동"
              className="w-full h-16 bg-sky-50/50 border border-sky-100 rounded-2xl px-6 text-xl font-bold text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all"
              autoFocus
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-slate-700 font-bold mb-2">연령</label>
              <input
                type="number"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="예: 75"
                className="w-full h-16 bg-sky-50/50 border border-sky-100 rounded-2xl px-6 text-xl font-bold text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all"
              />
            </div>
            <div className="flex-1">
              <label className="block text-slate-700 font-bold mb-2">성별</label>
              <div className="flex bg-sky-50/50 border border-sky-100 rounded-2xl p-1.5 h-16">
                <button type="button" onClick={() => setGender('남')} className={`flex-1 rounded-xl font-bold text-lg transition-all ${gender === '남' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-500'}`}>남</button>
                <button type="button" onClick={() => setGender('여')} className={`flex-1 rounded-xl font-bold text-lg transition-all ${gender === '여' ? 'bg-white text-sky-600 shadow-sm' : 'text-slate-500'}`}>여</button>
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={!name || !age}
            className="w-full h-16 mt-4 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-2xl text-xl font-extrabold shadow-lg shadow-sky-200/50 transition-all"
          >
            추가하기
          </button>
        </form>
      </div>
    </div>
  );
}

// --- Checklist Form Component ---
function ChecklistForm({ patient, onBack, onComplete }: { patient: Patient; onBack: () => void; onComplete: () => void }) {
  const [systolic, setSystolic] = useState<number | ''>(120);
  const [diastolic, setDiastolic] = useState<number | ''>(80);
  const [bloodSugar, setBloodSugar] = useState<number | ''>(100);
  const [medicationStatus, setMedicationStatus] = useState<'well' | 'missed' | null>(null);
  const [observations, setObservations] = useState<string[]>([]);
  const [notes, setNotes] = useState('');

  const toggleObservation = (chip: string) => {
    setObservations(prev => prev.includes(chip) ? prev.filter(c => c !== chip) : [...prev, chip]);
  };

  const adjustValue = (setter: React.Dispatch<React.SetStateAction<number | ''>>, current: number | '', amount: number) => {
    const val = current === '' ? 0 : current;
    setter(Math.max(0, val + amount));
  };

  return (
    <div className="pb-36">
      {/* Header with Back Button */}
      <div className="bg-white px-4 sm:px-8 py-6 rounded-b-[40px] shadow-sm shadow-sky-100/50 mb-6 sticky top-0 z-40">
        <div className="max-w-3xl mx-auto flex items-center gap-4">
          <button onClick={onBack} className="w-12 h-12 bg-slate-50 hover:bg-slate-100 rounded-2xl flex items-center justify-center text-slate-600 transition-colors">
            <ChevronLeft className="w-7 h-7" strokeWidth={2.5} />
          </button>
          <div className="flex-1 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-sky-100 rounded-full flex items-center justify-center">
                <User className="w-7 h-7 text-sky-600" strokeWidth={2} />
              </div>
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">{patient.name} 환자</h1>
                <p className="text-sky-600 font-semibold text-sm mt-0.5">방문 건강 스크리닝</p>
              </div>
            </div>
            <div className="hidden sm:block bg-sky-50 px-4 py-2 rounded-2xl border border-sky-100">
              <span className="text-slate-600 font-bold">{patient.age}세 / {patient.gender}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 space-y-6">
        {/* Section 1: Vitals */}
        <section className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-sky-50 rounded-2xl">
              <HeartPulse className="w-6 h-6 text-sky-500" strokeWidth={2.5} />
            </div>
            <h2 className="text-xl font-extrabold text-slate-900">바이탈 사인</h2>
          </div>

          <div className="space-y-8">
            <div>
              <label className="block text-slate-500 font-bold mb-4 text-lg">혈압 (mmHg)</label>
              <div className="flex flex-col sm:flex-row gap-4 sm:gap-8">
                <div className="flex-1 bg-sky-50/50 rounded-3xl p-4 border border-sky-100 flex items-center justify-between">
                  <button onClick={() => adjustValue(setSystolic, systolic, -5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Minus className="w-6 h-6" strokeWidth={2.5} /></button>
                  <div className="flex flex-col items-center">
                    <input type="number" value={systolic} onChange={(e) => setSystolic(e.target.value === '' ? '' : Number(e.target.value))} className="w-24 text-center text-4xl font-extrabold text-slate-900 bg-transparent outline-none focus:ring-0 p-0" />
                    <span className="text-sky-600 font-bold text-sm">수축기</span>
                  </div>
                  <button onClick={() => adjustValue(setSystolic, systolic, 5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Plus className="w-6 h-6" strokeWidth={2.5} /></button>
                </div>
                <div className="flex-1 bg-sky-50/50 rounded-3xl p-4 border border-sky-100 flex items-center justify-between">
                  <button onClick={() => adjustValue(setDiastolic, diastolic, -5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Minus className="w-6 h-6" strokeWidth={2.5} /></button>
                  <div className="flex flex-col items-center">
                    <input type="number" value={diastolic} onChange={(e) => setDiastolic(e.target.value === '' ? '' : Number(e.target.value))} className="w-24 text-center text-4xl font-extrabold text-slate-900 bg-transparent outline-none focus:ring-0 p-0" />
                    <span className="text-sky-600 font-bold text-sm">이완기</span>
                  </div>
                  <button onClick={() => adjustValue(setDiastolic, diastolic, 5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Plus className="w-6 h-6" strokeWidth={2.5} /></button>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-slate-500 font-bold mb-4 text-lg">공복 혈당 (mg/dL)</label>
              <div className="bg-sky-50/50 rounded-3xl p-4 border border-sky-100 flex items-center justify-between max-w-sm">
                <button onClick={() => adjustValue(setBloodSugar, bloodSugar, -5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Minus className="w-6 h-6" strokeWidth={2.5} /></button>
                <input type="number" value={bloodSugar} onChange={(e) => setBloodSugar(e.target.value === '' ? '' : Number(e.target.value))} className="w-28 text-center text-4xl font-extrabold text-slate-900 bg-transparent outline-none focus:ring-0 p-0" />
                <button onClick={() => adjustValue(setBloodSugar, bloodSugar, 5)} className="w-14 h-14 rounded-2xl bg-white border border-sky-200 flex items-center justify-center text-sky-600 hover:bg-sky-50 active:bg-sky-100 transition-colors shadow-sm"><Plus className="w-6 h-6" strokeWidth={2.5} /></button>
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Medication */}
        <section className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-sky-50 rounded-2xl">
              <Pill className="w-6 h-6 text-sky-500" strokeWidth={2.5} />
            </div>
            <h2 className="text-xl font-extrabold text-slate-900">복약 확인</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button onClick={() => setMedicationStatus('well')} className={`h-20 rounded-3xl text-xl font-bold transition-all duration-300 flex items-center justify-center gap-3 border-2 ${medicationStatus === 'well' ? 'bg-sky-500 border-sky-500 text-white shadow-lg shadow-sky-200/50' : 'bg-white border-sky-100 text-slate-500 hover:border-sky-300 hover:bg-sky-50'}`}>
              {medicationStatus === 'well' && <Check className="w-6 h-6" strokeWidth={3} />} 잘 드시고 계심
            </button>
            <button onClick={() => setMedicationStatus('missed')} className={`h-20 rounded-3xl text-xl font-bold transition-all duration-300 flex items-center justify-center gap-3 border-2 ${medicationStatus === 'missed' ? 'bg-orange-500 border-orange-500 text-white shadow-lg shadow-orange-200/50' : 'bg-white border-sky-100 text-slate-500 hover:border-orange-200 hover:bg-orange-50'}`}>
              거르신 적 있음
            </button>
          </div>
        </section>

        {/* Section 3: Observations */}
        <section className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-sky-50 rounded-2xl">
              <Stethoscope className="w-6 h-6 text-sky-500" strokeWidth={2.5} />
            </div>
            <h2 className="text-xl font-extrabold text-slate-900">관찰 소견 (다중 선택)</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            {OBSERVATION_CHIPS.map((chip) => (
              <button key={chip} onClick={() => toggleObservation(chip)} className={`h-14 px-6 rounded-full text-lg font-bold transition-all duration-300 border-2 ${observations.includes(chip) ? 'bg-sky-500 border-sky-500 text-white shadow-md shadow-sky-200/50' : 'bg-white border-sky-100 text-slate-600 hover:border-sky-300 hover:bg-sky-50'}`}>
                {chip}
              </button>
            ))}
          </div>
        </section>

        {/* Section 4: Notes */}
        <section className="bg-white rounded-[32px] p-6 sm:p-8 shadow-sm shadow-sky-100/40 border border-sky-100">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 bg-sky-50 rounded-2xl">
              <ClipboardEdit className="w-6 h-6 text-sky-500" strokeWidth={2.5} />
            </div>
            <h2 className="text-xl font-extrabold text-slate-900">특이사항 (선택)</h2>
          </div>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="환자의 호소 증상이나 특이사항을 자유롭게 입력하세요." className="w-full h-32 bg-sky-50/50 border border-sky-100 rounded-3xl p-6 text-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:bg-white transition-all resize-none" />
        </section>
      </div>

      {/* Fixed Bottom FAB */}
      <div className="fixed bottom-0 left-0 right-0 p-4 sm:p-6 bg-white/80 backdrop-blur-xl border-t border-sky-100/50 z-50">
        <div className="max-w-3xl mx-auto">
          <button onClick={onComplete} className="w-full h-16 sm:h-20 bg-gradient-to-r from-cyan-500 to-sky-500 hover:from-cyan-600 hover:to-sky-600 text-white rounded-[28px] text-xl sm:text-2xl font-extrabold shadow-xl shadow-cyan-200/50 flex items-center justify-center gap-3 transition-all transform active:scale-[0.98]">
            <Sparkles className="w-7 h-7" strokeWidth={2.5} />
            기록 완료 및 AI 분석 요청
          </button>
        </div>
      </div>
    </div>
  );
}
