/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { Stethoscope, ClipboardList, Smartphone } from 'lucide-react';
import DoctorDashboard from './components/DoctorDashboard';
import NurseChecklist from './components/NurseChecklist';
import PatientApp from './components/PatientApp';
import { SessionTimeoutModal } from './components/SessionTimeoutModal';
import { useSessionTimeout } from './hooks/useSessionTimeout';

export default function App() {
  const [activeTab, setActiveTab] = useState<'doctor' | 'nurse' | 'patient'>('doctor');
  const [showTimeoutWarn, setShowTimeoutWarn] = useState(false);
  const [isLocked, setIsLocked] = useState(false);

  useSessionTimeout({
    onWarn: () => setShowTimeoutWarn(true),
    onLogout: () => {
      setShowTimeoutWarn(false);
      setIsLocked(true);
    },
  });

  return (
    <div className="min-h-screen bg-sky-50 flex flex-col font-sans selection:bg-cyan-100 selection:text-cyan-900">
      <header className="bg-white/60 backdrop-blur-2xl border-b border-sky-100/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row justify-between items-center h-auto sm:h-20 py-4 sm:py-0 gap-4 sm:gap-0">
            <div className="flex items-center">
              <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-sky-500 rounded-2xl flex items-center justify-center mr-4 shadow-lg shadow-cyan-200/50">
                <ActivityIcon className="w-6 h-6 text-white" strokeWidth={1.5} />
              </div>
              <span className="text-2xl font-extrabold text-slate-800 tracking-tight">Silver-Sync</span>
            </div>

            {/* Airy Segmented Control Navigation */}
            <nav className="flex p-1.5 space-x-2 bg-sky-100/50 rounded-full border border-white/60 shadow-inner">
              <button
                onClick={() => setActiveTab('doctor')}
                aria-current={activeTab === 'doctor' ? 'page' : undefined}
                className={`flex items-center px-5 py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
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
                className={`flex items-center px-5 py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
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
                className={`flex items-center px-5 py-2.5 rounded-full text-[15px] font-bold transition-all duration-300 ${
                  activeTab === 'patient'
                    ? 'bg-white text-cyan-600 shadow-sm shadow-sky-200/50'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-white/40'
                }`}
              >
                <Smartphone className="w-4 h-4 mr-2" strokeWidth={2} />
                환자
              </button>
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto w-full">
        {activeTab === 'doctor' && <DoctorDashboard />}
        {activeTab === 'nurse' && <NurseChecklist />}
        {activeTab === 'patient' && <PatientApp />}
      </main>

      {(showTimeoutWarn || isLocked) && (
        <SessionTimeoutModal
          isLocked={isLocked}
          onContinue={() => setShowTimeoutWarn(false)}
          onUnlock={() => setIsLocked(false)}
        />
      )}
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
