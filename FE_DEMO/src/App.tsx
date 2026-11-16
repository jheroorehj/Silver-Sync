/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { Stethoscope, ClipboardList, Smartphone, RotateCcw, Presentation, Play, X } from 'lucide-react';
import DoctorDashboard from './components/DoctorDashboard';
import NurseChecklist from './components/NurseChecklist';
import PatientApp from './components/PatientApp';
import { resetDemoData, isDemoUrl, startDemoTour, restartDemoTour, resumeDemoTour, endDemoTour, subscribeTour, getTourState } from './lib/demoTour';

// ?demo=true 접속: 화면이 저장된 데모 기록을 읽기 전에 먼저 초기화한다.
const AUTO_TOUR = isDemoUrl();
if (AUTO_TOUR) resetDemoData();

// 시연 리허설 후 간호사 기록·AI 분석 결과를 지우고 처음 상태로 되돌린다.
function resetDemo() {
  if (!window.confirm('간호사 기록, AI 분석 결과, 환자 복약 체크를 모두 지우고 처음 상태로 되돌릴까요?')) return;
  resetDemoData();
  window.location.reload();
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'doctor' | 'nurse' | 'patient'>('doctor');
  const tour = useSyncExternalStore(subscribeTour, getTourState);
  const tourActive = tour.mode === 'active';
  const tourPaused = tour.mode === 'paused';

  useEffect(() => {
    if (!AUTO_TOUR) return;
    const t = window.setTimeout(startDemoTour, 400); // 첫 화면이 그려진 뒤 시작
    return () => window.clearTimeout(t);
  }, []);

  return (
    <div className="min-h-screen bg-sky-50 flex flex-col font-sans selection:bg-cyan-100 selection:text-cyan-900">
      <header className="bg-white/60 backdrop-blur-2xl border-b border-sky-100/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 sm:h-20 gap-2">
            <div className="flex items-center">
              <div className="w-10 h-10 shrink-0 bg-gradient-to-br from-cyan-400 to-sky-500 rounded-2xl flex items-center justify-center sm:mr-4 shadow-lg shadow-cyan-200/50">
                <ActivityIcon className="w-6 h-6 text-white" strokeWidth={1.5} />
              </div>
              <span className="hidden sm:inline text-2xl font-extrabold text-slate-800 tracking-tight">Silver-Sync</span>
            </div>
            
            <div className="flex items-center gap-2">
            {/* Airy Segmented Control Navigation */}
            <nav aria-label="역할 선택" className="flex p-1 sm:p-1.5 space-x-1 sm:space-x-2 bg-sky-100/50 rounded-full border border-white/60 shadow-inner">
              <button
                onClick={() => setActiveTab('doctor')}
                aria-current={activeTab === 'doctor' ? 'page' : undefined}
                data-tour="nav-doctor"
                className={`flex items-center whitespace-nowrap px-3 sm:px-5 py-2 sm:py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
                  activeTab === 'doctor'
                    ? 'bg-white text-cyan-600 shadow-sm shadow-sky-200/50'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white/40'
                }`}
              >
                <Stethoscope className="w-4 h-4 mr-2" strokeWidth={2} />
                의사
              </button>
              <button
                onClick={() => setActiveTab('nurse')}
                aria-current={activeTab === 'nurse' ? 'page' : undefined}
                data-tour="nav-nurse"
                className={`flex items-center whitespace-nowrap px-3 sm:px-5 py-2 sm:py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
                  activeTab === 'nurse'
                    ? 'bg-white text-cyan-600 shadow-sm shadow-sky-200/50'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white/40'
                }`}
              >
                <ClipboardList className="w-4 h-4 mr-2" strokeWidth={2} />
                간호사
              </button>
              <button
                onClick={() => setActiveTab('patient')}
                aria-current={activeTab === 'patient' ? 'page' : undefined}
                data-tour="nav-patient"
                className={`flex items-center whitespace-nowrap px-3 sm:px-5 py-2 sm:py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
                  activeTab === 'patient'
                    ? 'bg-white text-cyan-600 shadow-sm shadow-sky-200/50'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white/40'
                }`}
              >
                <Smartphone className="w-4 h-4 mr-2" strokeWidth={2} />
                환자
              </button>
            </nav>

            {tourPaused ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={resumeDemoTour}
                  title="멈춘 단계부터 시연 가이드를 이어갑니다"
                  aria-label={`시연 이어하기, ${tour.step}단계부터`}
                  className="flex items-center gap-1.5 h-9 px-3 rounded-full text-sm font-bold whitespace-nowrap bg-sky-700 border border-sky-700 text-white shadow-md shadow-sky-200 ring-4 ring-sky-200/70 animate-pulse hover:animate-none"
                >
                  <Play className="w-4 h-4" strokeWidth={2.5} fill="currentColor" />
                  <span className="hidden md:inline">이어하기 {tour.step}/{tour.total}</span>
                </button>
                <button
                  onClick={endDemoTour}
                  title="시연 가이드 종료"
                  aria-label="시연 가이드 종료"
                  className="w-9 h-9 rounded-full flex items-center justify-center text-slate-500 hover:text-slate-700 hover:bg-white/70 border border-transparent"
                >
                  <X className="w-4 h-4" strokeWidth={2.5} />
                </button>
              </div>
            ) : (
              <button
                onClick={restartDemoTour}
                title="데모 기록을 초기화하고 시연 가이드를 1단계부터 시작합니다"
                aria-label={tourActive ? '시연 진행 중 (다시 시작)' : '시연 가이드 시작'}
                aria-pressed={tourActive}
                className={`flex items-center gap-1.5 h-9 px-3 rounded-full text-sm font-bold whitespace-nowrap border transition-colors ${
                  tourActive
                    ? 'bg-sky-700 border-sky-700 text-white'
                    : 'bg-white/70 border-sky-200 text-sky-700 hover:bg-white'
                }`}
              >
                <Presentation className="w-4 h-4" strokeWidth={2.25} />
                <span className="hidden md:inline">{tourActive ? `시연 진행 중 ${tour.step}/${tour.total}` : '시연 가이드'}</span>
              </button>
            )}

            <button
              onClick={resetDemo}
              title="데모 초기화"
              aria-label="데모 초기화"
              className="hidden sm:block p-2 rounded-full text-slate-300 hover:text-slate-500 hover:bg-white/60 transition-colors"
            >
              <RotateCcw className="w-4 h-4" strokeWidth={2} />
            </button>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full">
        {activeTab === 'doctor' && <DoctorDashboard />}
        {activeTab === 'nurse' && <NurseChecklist />}
        {activeTab === 'patient' && <PatientApp />}
      </main>
    </div>
  );
}

function ActivityIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}
