import React, { useState, useEffect } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Activity,
  HeartPulse,
  Pill,
  ChevronRight,
  Phone,
  FileText,
  Sparkles,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Info,
  AlertTriangle,
  Video,
  Stethoscope
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';
import patientsData from '../data/patients.json';

const patients = patientsData;
const DAYS = ['월', '화', '수', '목', '금'];

type StatusTheme = {
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

function getStatusTheme(status: string): StatusTheme {
  if (status === 'orange') return {
    gradient: 'from-orange-50 to-amber-50/30',
    border: 'border-orange-100/50',
    iconColor: 'text-orange-500',
    labelColor: 'text-orange-600',
    highlightColor: 'text-orange-500',
    detailsButtonColor: 'text-orange-500 hover:text-orange-600',
    detailBorder: 'border-orange-100',
    detailBg: 'bg-orange-50/50',
    detailStatColor: 'text-orange-600',
    footerBtn1: 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50',
    footerBtn2: 'bg-orange-500 text-white border-transparent shadow-lg shadow-orange-200/50 hover:bg-orange-600',
  };
  if (status === 'amber') return {
    gradient: 'from-amber-50 to-yellow-50/30',
    border: 'border-amber-100/50',
    iconColor: 'text-amber-500',
    labelColor: 'text-amber-600',
    highlightColor: 'text-amber-500',
    detailsButtonColor: 'text-amber-500 hover:text-amber-600',
    detailBorder: 'border-amber-100',
    detailBg: 'bg-amber-50/50',
    detailStatColor: 'text-amber-600',
    footerBtn1: 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50',
    footerBtn2: 'bg-amber-500 text-white border-transparent shadow-lg shadow-amber-200/50 hover:bg-amber-600',
  };
  return {
    gradient: 'from-teal-50 to-cyan-50/30',
    border: 'border-teal-100/50',
    iconColor: 'text-teal-500',
    labelColor: 'text-teal-600',
    highlightColor: 'text-teal-500',
    detailsButtonColor: 'text-teal-500 hover:text-teal-600',
    detailBorder: 'border-teal-100',
    detailBg: 'bg-teal-50/50',
    detailStatColor: 'text-teal-600',
    footerBtn1: 'bg-teal-500 text-white border-transparent shadow-lg shadow-teal-200/50 hover:bg-teal-600',
    footerBtn2: 'bg-white text-teal-600 border-teal-200 hover:bg-teal-50',
  };
}

// Safely renders text that contains <span class="font-bold text-slate-900">...</span> markers
function SafeText({ html }: { html: string }) {
  const parts = html.split(/(<span class="font-bold text-slate-900">.*?<\/span>)/g);
  return (
    <>
      {parts.map((part, i) => {
        const match = part.match(/^<span class="font-bold text-slate-900">(.*?)<\/span>$/);
        return match ? (
          <span key={i} className="font-bold text-slate-900">{match[1]}</span>
        ) : part;
      })}
    </>
  );
}

function VitalCard({
  isHovered,
  onMouseEnter,
  onMouseLeave,
  chartLabel,
  chartData,
  yDomain,
  children,
}: {
  isHovered: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  chartLabel: string;
  chartData: number[];
  yDomain: [number | string, number | string];
  children: React.ReactNode;
}) {
  const chartDataFormatted = chartData.map((v, i) => ({ day: DAYS[i], val: v }));

  return (
    <div
      className="bg-sky-50/50 rounded-2xl p-5 border border-sky-100/50 relative overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-sky-100/30 h-40"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <AnimatePresence mode="wait">
        {isHovered ? (
          <motion.div
            key="chart"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="h-full flex flex-col"
          >
            <span className="text-xs font-bold text-sky-600 mb-2">{chartLabel}</span>
            <div className="flex-1 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartDataFormatted}>
                  <Line type="monotone" dataKey="val" stroke="#0ea5e9" strokeWidth={3} dot={{ r: 4, fill: '#0ea5e9' }} />
                  <XAxis dataKey="day" hide />
                  <YAxis hide domain={yDomain} />
                  <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="info"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function DoctorDashboard() {
  const [selectedPatientId, setSelectedPatientId] = useState(1);
  const [showAiDetails, setShowAiDetails] = useState(false);
  const [hoveredVital, setHoveredVital] = useState<string | null>(null);

  const selectedPatient = patients.find(p => p.id === selectedPatientId) || patients[0];
  const theme = getStatusTheme(selectedPatient.status);

  useEffect(() => {
    setShowAiDetails(false);
  }, [selectedPatientId]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-[calc(100vh-5rem)] flex flex-col lg:flex-row gap-8">

      {/* Left Column: Patient List */}
      <div className="w-full lg:w-1/3 flex flex-col h-full">
        <div className="flex items-center justify-between mb-6 px-2">
          <h2 className="text-xl font-extrabold text-slate-800 tracking-tight">대기 환자</h2>
          <span className="bg-cyan-100 text-cyan-700 px-3 py-1 rounded-full text-sm font-bold">총 {patients.length}명</span>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 space-y-4 pb-8">
          {patients.map((patient) => (
            <button
              key={patient.id}
              onClick={() => setSelectedPatientId(patient.id)}
              className={`w-full text-left p-5 rounded-3xl transition-all duration-300 border ${
                selectedPatientId === patient.id
                  ? 'bg-white border-sky-200 shadow-lg shadow-sky-100/60 ring-1 ring-sky-100'
                  : 'bg-white/40 border-transparent hover:bg-white/80 hover:shadow-md hover:shadow-sky-100/30'
              }`}
            >
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3">
                  <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${
                    patient.status === 'orange' ? 'bg-orange-50 border-orange-200 text-orange-600' :
                    patient.status === 'amber' ? 'bg-amber-50 border-amber-200 text-amber-600' :
                    'bg-teal-50 border-teal-200 text-teal-600'
                  }`}>
                    <div className={`w-1.5 h-1.5 rounded-full ${
                      patient.status === 'orange' ? 'bg-orange-500' :
                      patient.status === 'amber' ? 'bg-amber-500' :
                      'bg-teal-500'
                    }`} />
                    <span className="text-[10px] font-bold whitespace-nowrap">
                      {patient.status === 'orange' ? '대면권고' :
                       patient.status === 'amber' ? '주의' : '비대면'}
                    </span>
                  </div>
                  <span className="text-lg font-bold text-slate-900">{patient.name}</span>
                  <span className="text-sm font-medium text-slate-500">{patient.gender}/{patient.age}</span>
                </div>
                <div className="flex items-center text-slate-400 text-sm font-medium">
                  <Clock className="w-3.5 h-3.5 mr-1" strokeWidth={2} />
                  {patient.time}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500 bg-slate-100/80 px-3 py-1 rounded-full">
                  {patient.disease}
                </span>
                {selectedPatientId === patient.id && (
                  <ChevronRight className="w-5 h-5 text-cyan-500" strokeWidth={2} />
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right Column: Main AI Card */}
      <div className="w-full lg:w-2/3 flex flex-col h-full">
        <div className="bg-white/70 backdrop-blur-2xl rounded-[32px] border border-white shadow-xl shadow-sky-100/50 flex-1 overflow-hidden flex flex-col">

          {/* Header */}
          <div className="p-8 pb-6 border-b border-sky-50/50 flex justify-between items-center">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">{selectedPatient.name}</h1>
                <span className="text-lg text-slate-500 font-medium">{selectedPatient.gender} / {selectedPatient.age}세</span>
              </div>
              <div className="flex gap-2">
                {selectedPatient.disease.split(', ').map(d => (
                  <span key={d} className="px-3 py-1 bg-sky-50 text-sky-600 rounded-full text-sm font-bold">{d}</span>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button className="p-3 bg-slate-50 hover:bg-slate-100 text-slate-600 rounded-2xl transition-colors">
                <FileText className="w-5 h-5" strokeWidth={1.5} />
              </button>
              <button className="p-3 bg-slate-50 hover:bg-slate-100 text-slate-600 rounded-2xl transition-colors">
                <Phone className="w-5 h-5" strokeWidth={1.5} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-8 space-y-8">

            {/* AI Recommendation Hero */}
            <div className={`rounded-3xl p-6 border relative overflow-hidden bg-gradient-to-br ${theme.gradient} ${theme.border}`}>
              <div className="absolute top-0 right-0 p-6 opacity-10">
                {selectedPatient.status === 'orange' ? (
                  <Stethoscope className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
                ) : selectedPatient.status === 'amber' ? (
                  <AlertTriangle className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
                ) : (
                  <Video className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
                )}
              </div>

              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-4">
                  <Sparkles className={`w-5 h-5 ${theme.iconColor}`} strokeWidth={2} />
                  <span className={`font-bold tracking-wide ${theme.labelColor}`}>AI 분석 결과</span>
                </div>
                <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 mb-4">
                  {selectedPatient.aiRecommendation.title}<br/>
                  <span className={theme.highlightColor}>
                    {selectedPatient.aiRecommendation.highlight}
                  </span>됩니다.
                </h2>

                <div className="space-y-4">
                  {selectedPatient.aiRecommendation.reasons.map((reason, idx) => (
                    <div key={idx} className="flex items-start gap-3">
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                        reason.type === 'check' ? 'bg-teal-100' : 'bg-orange-100'
                      }`}>
                        {reason.type === 'up' && <ArrowUpRight className="w-3.5 h-3.5 text-orange-600" strokeWidth={2.5} />}
                        {reason.type === 'alert' && <AlertCircle className="w-3.5 h-3.5 text-orange-600" strokeWidth={2.5} />}
                        {reason.type === 'check' && <CheckCircle2 className="w-3.5 h-3.5 text-teal-600" strokeWidth={2.5} />}
                      </div>
                      <p className="text-slate-700 text-lg leading-relaxed">
                        <SafeText html={reason.text} />
                      </p>
                    </div>
                  ))}
                </div>

                {/* AI Detail Section */}
                <div className="mt-2">
                  <button
                    onClick={() => setShowAiDetails(!showAiDetails)}
                    className={`flex items-center gap-2 font-bold transition-colors ml-auto bg-transparent px-2 py-1 rounded-xl ${theme.detailsButtonColor}`}
                  >
                    {showAiDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    상세 보기
                  </button>

                  <AnimatePresence>
                    {showAiDetails && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className={`mt-6 p-6 bg-white/60 rounded-2xl border space-y-4 ${theme.detailBorder}`}>
                          <div className="flex items-center gap-2 text-slate-800 font-bold">
                            <Info className={`w-4 h-4 ${theme.iconColor}`} />
                            <span>다변수 맥락 추론 상세</span>
                          </div>
                          <p className="text-slate-600 text-sm leading-relaxed">
                            {selectedPatient.aiRecommendation.details}
                          </p>
                          <div className="grid grid-cols-2 gap-4 pt-2">
                            {selectedPatient.aiRecommendation.stats.map((stat, idx) => (
                              <div key={idx} className={`p-3 rounded-xl ${theme.detailBg}`}>
                                <span className={`text-xs font-bold block mb-1 ${theme.detailStatColor}`}>{stat.label}</span>
                                <span className="text-sm font-bold text-slate-800">{stat.value}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            </div>

            {/* Vitals Summary */}
            <div>
              <h3 className="text-lg font-bold text-slate-800 mb-4 px-1">최근 바이탈 요약</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <VitalCard
                  isHovered={hoveredVital === 'bp'}
                  onMouseEnter={() => setHoveredVital('bp')}
                  onMouseLeave={() => setHoveredVital(null)}
                  chartLabel="혈압 추이 (5일)"
                  chartData={selectedPatient.vitals.bp.data}
                  yDomain={['dataMin - 10', 'dataMax + 10']}
                >
                  <div className="flex items-center gap-2 mb-3 text-slate-500">
                    <HeartPulse className="w-4 h-4" strokeWidth={2} />
                    <span className="font-semibold text-sm">혈압 (mmHg)</span>
                  </div>
                  <div className="flex items-end gap-2">
                    <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
                      {selectedPatient.vitals.bp.current.split('/')[0]}
                      <span className="text-xl text-slate-400 font-medium">/{selectedPatient.vitals.bp.current.split('/')[1]}</span>
                    </span>
                  </div>
                  <p className={`text-sm font-medium mt-2 flex items-center ${selectedPatient.vitals.bp.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
                    {selectedPatient.vitals.bp.trendUp && <ArrowUpRight className="w-3 h-3 mr-1" strokeWidth={2.5} />}
                    {selectedPatient.vitals.bp.trend}
                  </p>
                </VitalCard>

                <VitalCard
                  isHovered={hoveredVital === 'sugar'}
                  onMouseEnter={() => setHoveredVital('sugar')}
                  onMouseLeave={() => setHoveredVital(null)}
                  chartLabel="혈당 추이 (5일)"
                  chartData={selectedPatient.vitals.sugar.data}
                  yDomain={['dataMin - 10', 'dataMax + 10']}
                >
                  <div className="flex items-center gap-2 mb-3 text-slate-500">
                    <Activity className="w-4 h-4" strokeWidth={2} />
                    <span className="font-semibold text-sm">공복혈당 (mg/dL)</span>
                  </div>
                  <div className="flex items-end gap-2">
                    <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
                      {selectedPatient.vitals.sugar.current}
                    </span>
                  </div>
                  <p className={`text-sm font-medium mt-2 flex items-center ${selectedPatient.vitals.sugar.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
                    {selectedPatient.vitals.sugar.status}
                  </p>
                </VitalCard>

                <VitalCard
                  isHovered={hoveredVital === 'adherence'}
                  onMouseEnter={() => setHoveredVital('adherence')}
                  onMouseLeave={() => setHoveredVital(null)}
                  chartLabel="복약 순응도 (5일)"
                  chartData={selectedPatient.vitals.adherence.data}
                  yDomain={[0, 110]}
                >
                  <div className="flex items-center gap-2 mb-3 text-slate-500">
                    <Pill className="w-4 h-4" strokeWidth={2} />
                    <span className="font-semibold text-sm">복약 순응도</span>
                  </div>
                  <div className="flex items-end gap-2">
                    <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
                      {selectedPatient.vitals.adherence.current}
                      <span className="text-xl text-slate-400 font-medium">%</span>
                    </span>
                  </div>
                  <p className="text-sm text-slate-500 font-medium mt-2 flex items-center">
                    최근 7일 기준
                  </p>
                </VitalCard>
              </div>
            </div>

          </div>

          {/* Footer Actions */}
          <div className="p-6 border-t border-sky-50/50 bg-white/50 flex gap-4">
            <button className={`flex-1 font-bold py-4 rounded-2xl transition-all text-lg border ${theme.footerBtn1}`}>
              기존 처방 유지
            </button>
            <button className={`flex-1 font-bold py-4 rounded-2xl transition-all text-lg border ${theme.footerBtn2}`}>
              {selectedPatient.footerAction}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
