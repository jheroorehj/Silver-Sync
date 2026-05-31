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
  Stethoscope,
  Printer,
  Download,
  MessageSquare,
  ClipboardList,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  AreaChart,
  Area,
  ReferenceLine,
} from 'recharts';
import { getDocPatients } from '../adapters/patientAdapter';
import { maskPatientId } from '../lib/utils';
import { DAYS, STATUS_THEME_MAP } from '../constants';
import { DocStatusBadge } from './ui/StatusBadge';
import type { DocPatient, StatusTheme, SoapNote } from '../types';

const patients = getDocPatients();

// ── Helpers ───────────────────────────────────────────────────────────────

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

function AnomalyHighlightedText({ text, anomalies }: { text: string; anomalies: string[] }) {
  if (!anomalies || anomalies.length === 0) return <>{text}</>;
  const parts = text.split(/([\d]+(?:\/[\d]+)?\s*(?:mmHg|mg\/dL))/g);
  return (
    <>
      {parts.map((part, i) => {
        const bpMatch = part.match(/^(\d+)\/(\d+)\s*mmHg$/);
        const sugarMatch = part.match(/^(\d+)\s*mg\/dL$/);
        if (bpMatch && anomalies.includes('bp') && Number(bpMatch[1]) >= 140) {
          return <span key={i} className="font-bold text-orange-500">{part}</span>;
        }
        if (sugarMatch && anomalies.includes('sugar') && Number(sugarMatch[1]) >= 126) {
          return <span key={i} className="font-bold text-orange-500">{part}</span>;
        }
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </>
  );
}

// ── AI 면책 배너 ──────────────────────────────────────────────────────────

function AiDisclaimerBanner() {
  return (
    <div
      role="note"
      className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 text-xs text-amber-700 font-medium"
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
      본 내용은 AI 에이전트가 생성한 참고 자료이며, 최종 임상 판단은 담당 의료진의 책임입니다.
    </div>
  );
}

// ── 에이전트 메타데이터 패널 ──────────────────────────────────────────────

function AgentMetaPanel({ agentMeta }: { agentMeta: NonNullable<DocPatient['agentMeta']> }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-2xl border border-slate-100 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls="agent-meta-content"
        className={`w-full flex items-center justify-between px-5 py-4 text-sm font-bold transition-colors ${
          agentMeta.dissensionFlag
            ? 'bg-orange-50 text-orange-700 hover:bg-orange-100'
            : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
        }`}
      >
        <span className="flex items-center gap-2">
          {agentMeta.dissensionFlag && <AlertTriangle className="w-4 h-4" />}
          {agentMeta.dissensionFlag ? '⚠ 에이전트 의견 불일치' : '에이전트 판단 근거'}
          <span className="font-medium text-xs opacity-70">(신뢰도 {agentMeta.confidenceScore}%)</span>
        </span>
        {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            id="agent-meta-content"
            key="agent-meta-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="px-5 py-4 space-y-2 bg-white border-t border-slate-100">
              {agentMeta.debateLog.map((entry, i) => (
                <p key={i} className="text-sm text-slate-600 leading-relaxed">{entry}</p>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── CGM 차트 ──────────────────────────────────────────────────────────────

function CgmChart({
  data,
  referenceMin,
  referenceMax,
}: {
  data: { time: string; value: number }[];
  referenceMin: number;
  referenceMax: number;
}) {
  return (
    <div className="mt-4 pt-4 border-t border-slate-100">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold text-teal-600">CGM 인트라데이 혈당 (mg/dL)</span>
        <span className="text-xs text-slate-400 font-medium">
          참고 범위 {referenceMin}–{referenceMax} mg/dL
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 8, right: 16, left: -24, bottom: 0 }}>
          <defs>
            <linearGradient id="cgmGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            tick={{ fontSize: 9 }}
            interval={3}
            tickLine={false}
          />
          <YAxis
            domain={[60, 180]}
            tick={{ fontSize: 9 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              borderRadius: '12px',
              border: 'none',
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              fontSize: '12px',
            }}
            formatter={(v: number) => [`${v} mg/dL`, '혈당']}
          />
          <ReferenceLine
            y={referenceMax}
            stroke="#f97316"
            strokeDasharray="4 4"
            strokeWidth={1.5}
          />
          <ReferenceLine
            y={referenceMin}
            stroke="#f97316"
            strokeDasharray="4 4"
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#14b8a6"
            strokeWidth={2}
            fill="url(#cgmGradient)"
            dot={(props: { cx: number; cy: number; payload: { time: string; value: number } }) => {
              const { cx, cy, payload } = props;
              const isOut = payload.value > referenceMax || payload.value < referenceMin;
              return (
                <circle
                  key={`cgm-dot-${payload.time}`}
                  cx={cx}
                  cy={cy}
                  r={isOut ? 4 : 2.5}
                  fill={isOut ? '#f97316' : '#14b8a6'}
                  stroke="white"
                  strokeWidth={1.5}
                />
              );
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── VitalCard ─────────────────────────────────────────────────────────────

function VitalCard({
  isHovered, onMouseEnter, onMouseLeave,
  chartLabel, chartData, yDomain, children,
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
          <motion.div key="chart" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full flex flex-col">
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
          <motion.div key="info" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── SOAP Note View ────────────────────────────────────────────────────────

function SoapNoteView({ patient, theme }: { patient: DocPatient; theme: StatusTheme }) {
  const soap = patient.soapNote as SoapNote;

  const SOAP_SECTIONS = [
    {
      key: 'S', label: 'Subjective', sublabel: '주관적 정보 (환자 호소)',
      content: soap.subjective,
      accent: 'border-sky-400', bg: 'bg-sky-50/40',
      icon: <MessageSquare className="w-5 h-5 text-sky-500" />,
    },
    {
      key: 'O', label: 'Objective', sublabel: '객관적 정보 (측정값)',
      content: soap.objective,
      accent: 'border-teal-400', bg: 'bg-teal-50/40',
      icon: <Activity className="w-5 h-5 text-teal-500" />,
      anomaly: true,
    },
    {
      key: 'A', label: 'Assessment', sublabel: 'AI 평가',
      content: soap.assessment,
      accent: `border-${patient.status === 'orange' ? 'orange' : patient.status === 'amber' ? 'amber' : 'teal'}-400`,
      bg: `bg-${patient.status === 'orange' ? 'orange' : patient.status === 'amber' ? 'amber' : 'teal'}-50/40`,
      icon: <Sparkles className={`w-5 h-5 ${theme.iconColor}`} />,
    },
    {
      key: 'P', label: 'Plan', sublabel: '처치 계획',
      content: soap.plan,
      accent: 'border-slate-400', bg: 'bg-slate-50/40',
      icon: <ClipboardList className="w-5 h-5 text-slate-500" />,
    },
  ] as const;

  return (
    <div className="space-y-4">
      {/* AI 면책 배너 */}
      <AiDisclaimerBanner />

      {/* Print-only header */}
      <div className="hidden print:block mb-6 pb-4 border-b border-slate-200">
        <h1 className="text-2xl font-extrabold text-slate-900">Silver-Sync SOAP 노트</h1>
        <p className="text-slate-500 mt-1">{patient.name} ({patient.gender} / {patient.age}세) — {patient.disease}</p>
        <p className="text-xs text-slate-400 mt-1">출력일: {new Date().toLocaleDateString('ko-KR')}</p>
      </div>

      {SOAP_SECTIONS.map((section) => (
        <div key={section.key} className={`rounded-2xl border-l-4 p-6 border border-slate-100/50 ${section.accent} ${section.bg}`}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-white shadow-sm flex items-center justify-center font-extrabold text-slate-700 text-sm">
              {section.key}
            </div>
            {section.icon}
            <div>
              <span className="font-extrabold text-slate-800">{section.label}</span>
              <span className="text-slate-400 text-sm ml-2">{section.sublabel}</span>
            </div>
          </div>
          <p className="text-slate-700 leading-relaxed text-sm">
            {'anomaly' in section && section.anomaly
              ? <AnomalyHighlightedText text={section.content} anomalies={soap.anomalies} />
              : section.content
            }
          </p>
          {/* CGM 차트 — Objective 섹션에만 표시 */}
          {section.key === 'O' && patient.vitals.sugar.timeSeries && (
            <CgmChart
              data={patient.vitals.sugar.timeSeries}
              referenceMin={70}
              referenceMax={140}
            />
          )}
        </div>
      ))}

      {/* 에이전트 메타데이터 패널 */}
      {patient.agentMeta && (
        <AgentMetaPanel agentMeta={patient.agentMeta} />
      )}

      {/* Print/PDF buttons */}
      <div className="flex gap-3 pt-2 print:hidden">
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-5 py-3 bg-white border border-slate-200 rounded-2xl text-slate-700 font-bold hover:bg-slate-50 transition-colors shadow-sm"
        >
          <Printer className="w-4 h-4" strokeWidth={2} />
          인쇄하기
        </button>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-5 py-3 bg-sky-500 text-white rounded-2xl font-bold hover:bg-sky-600 transition-colors shadow-md shadow-sky-200/50"
        >
          <Download className="w-4 h-4" strokeWidth={2} />
          PDF 저장
        </button>
      </div>
    </div>
  );
}

// ── AI Recommendation Section ──────────────────────────────────────────────

function AIRecommendationSection({
  patient, theme, showAiDetails, onToggleDetails,
}: {
  patient: DocPatient;
  theme: StatusTheme;
  showAiDetails: boolean;
  onToggleDetails: () => void;
}) {
  return (
    <div className="space-y-3">
      {/* AI 면책 배너 */}
      <AiDisclaimerBanner />

      {/* 에이전트 의견 불일치 인라인 경고 */}
      {patient.agentMeta?.dissensionFlag && (
        <div className="flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-2xl px-4 py-2.5 text-sm text-orange-700 font-bold">
          <AlertTriangle className="w-4 h-4 shrink-0 text-orange-500" />
          에이전트 간 의견 불일치가 감지되었습니다. SOAP 탭의 판단 근거 패널을 참고하세요.
        </div>
      )}

      <div className={`rounded-3xl p-6 border relative overflow-hidden bg-gradient-to-br ${theme.gradient} ${theme.border}`}>
        <div className="absolute top-0 right-0 p-6 opacity-10">
          {patient.status === 'orange'
            ? <Stethoscope className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
            : patient.status === 'amber'
            ? <AlertTriangle className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
            : <Video className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
          }
        </div>
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className={`w-5 h-5 ${theme.iconColor}`} strokeWidth={2} />
            <span className={`font-bold tracking-wide ${theme.labelColor}`}>AI 분석 결과</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 mb-4">
            {patient.aiRecommendation.title}<br/>
            <span className={theme.highlightColor}>{patient.aiRecommendation.highlight}</span>됩니다.
          </h2>
          <div className="space-y-4">
            {patient.aiRecommendation.reasons.map((reason, idx) => (
              <div key={idx} className="flex items-start gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${reason.type === 'check' ? 'bg-teal-100' : 'bg-orange-100'}`}>
                  {reason.type === 'up'    && <ArrowUpRight className="w-3.5 h-3.5 text-orange-600" strokeWidth={2.5} />}
                  {reason.type === 'alert' && <AlertCircle  className="w-3.5 h-3.5 text-orange-600" strokeWidth={2.5} />}
                  {reason.type === 'check' && <CheckCircle2 className="w-3.5 h-3.5 text-teal-600"   strokeWidth={2.5} />}
                </div>
                <p className="text-slate-700 text-lg leading-relaxed"><SafeText html={reason.text} /></p>
              </div>
            ))}
          </div>
          <div className="mt-2">
            <button
              onClick={onToggleDetails}
              aria-expanded={showAiDetails}
              aria-controls="ai-details"
              className={`flex items-center gap-2 font-bold transition-colors ml-auto bg-transparent px-2 py-1 rounded-xl ${theme.detailsButtonColor}`}
            >
              {showAiDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              상세 보기
            </button>
            <AnimatePresence>
              {showAiDetails && (
                <motion.div
                  id="ai-details"
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
                    <p className="text-slate-600 text-sm leading-relaxed">{patient.aiRecommendation.details}</p>
                    <div className="grid grid-cols-2 gap-4 pt-2">
                      {patient.aiRecommendation.stats.map((stat, idx) => (
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
    </div>
  );
}

// ── Vitals Section ────────────────────────────────────────────────────────

function VitalsSection({ patient, hoveredVital, onHover }: {
  patient: DocPatient;
  hoveredVital: string | null;
  onHover: (key: string | null) => void;
}) {
  return (
    <div>
      <h3 className="text-lg font-bold text-slate-800 mb-4 px-1">최근 바이탈 요약</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <VitalCard isHovered={hoveredVital === 'bp'} onMouseEnter={() => onHover('bp')} onMouseLeave={() => onHover(null)} chartLabel="혈압 추이 (5일)" chartData={patient.vitals.bp.data} yDomain={['dataMin - 10', 'dataMax + 10']}>
          <div className="flex items-center gap-2 mb-3 text-slate-500"><HeartPulse className="w-4 h-4" strokeWidth={2} /><span className="font-semibold text-sm">혈압 (mmHg)</span></div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
              {patient.vitals.bp.current.split('/')[0]}
              <span className="text-xl text-slate-400 font-medium">/{patient.vitals.bp.current.split('/')[1]}</span>
            </span>
          </div>
          <p className={`text-sm font-medium mt-2 flex items-center ${patient.vitals.bp.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
            {patient.vitals.bp.trendUp && <ArrowUpRight className="w-3 h-3 mr-1" strokeWidth={2.5} />}
            {patient.vitals.bp.trend}
          </p>
        </VitalCard>

        <VitalCard isHovered={hoveredVital === 'sugar'} onMouseEnter={() => onHover('sugar')} onMouseLeave={() => onHover(null)} chartLabel="혈당 추이 (5일)" chartData={patient.vitals.sugar.data} yDomain={['dataMin - 10', 'dataMax + 10']}>
          <div className="flex items-center gap-2 mb-3 text-slate-500"><Activity className="w-4 h-4" strokeWidth={2} /><span className="font-semibold text-sm">공복혈당 (mg/dL)</span></div>
          <div className="flex items-end gap-2"><span className="text-3xl font-extrabold text-slate-900 tracking-tighter">{patient.vitals.sugar.current}</span></div>
          <p className={`text-sm font-medium mt-2 flex items-center ${patient.vitals.sugar.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
            {patient.vitals.sugar.status}
          </p>
        </VitalCard>

        <VitalCard isHovered={hoveredVital === 'adherence'} onMouseEnter={() => onHover('adherence')} onMouseLeave={() => onHover(null)} chartLabel="복약 순응도 (5일)" chartData={patient.vitals.adherence.data} yDomain={[0, 110]}>
          <div className="flex items-center gap-2 mb-3 text-slate-500"><Pill className="w-4 h-4" strokeWidth={2} /><span className="font-semibold text-sm">복약 순응도</span></div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
              {patient.vitals.adherence.current}
              <span className="text-xl text-slate-400 font-medium">%</span>
            </span>
          </div>
          <p className="text-sm text-slate-500 font-medium mt-2">최근 7일 기준</p>
        </VitalCard>
      </div>
    </div>
  );
}

// ── Patient List Panel ────────────────────────────────────────────────────

function PatientListPanel({ selectedPatientId, onSelect }: {
  selectedPatientId: number;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="w-full lg:w-1/3 flex flex-col h-full">
      <div className="flex items-center justify-between mb-6 px-2">
        <h2 className="text-xl font-extrabold text-slate-800 tracking-tight">대기 환자</h2>
        <span className="bg-cyan-100 text-cyan-700 px-3 py-1 rounded-full text-sm font-bold">총 {patients.length}명</span>
      </div>
      <div className="flex-1 overflow-y-auto pr-2 space-y-4 pb-8">
        {patients.map((patient) => (
          <button
            key={patient.id}
            onClick={() => onSelect(patient.id)}
            className={`w-full text-left p-5 rounded-3xl transition-all duration-300 border ${
              selectedPatientId === patient.id
                ? 'bg-white border-sky-200 shadow-lg shadow-sky-100/60 ring-1 ring-sky-100'
                : 'bg-white/40 border-transparent hover:bg-white/80 hover:shadow-md hover:shadow-sky-100/30'
            }`}
          >
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-3">
                <DocStatusBadge status={patient.status} />
                <span className="text-lg font-bold text-slate-900">{patient.name}</span>
                <span className="text-sm font-medium text-slate-500">{patient.gender}/{patient.age}</span>
              </div>
              <div className="flex items-center text-slate-400 text-sm font-medium">
                <Clock className="w-3.5 h-3.5 mr-1" strokeWidth={2} />
                {patient.time}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500 bg-slate-100/80 px-3 py-1 rounded-full">{patient.disease}</span>
              {selectedPatientId === patient.id && <ChevronRight className="w-5 h-5 text-cyan-500" strokeWidth={2} />}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────

export default function DoctorDashboard() {
  const [selectedPatientId, setSelectedPatientId] = useState(1);
  const [showAiDetails, setShowAiDetails] = useState(false);
  const [hoveredVital, setHoveredVital] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<'ai' | 'soap'>('ai');

  const selectedPatient = patients.find(p => p.id === selectedPatientId) || patients[0];
  const theme = STATUS_THEME_MAP[selectedPatient.status];

  useEffect(() => {
    setShowAiDetails(false);
    setActivePanel('ai');
  }, [selectedPatientId]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-[calc(100vh-5rem)] flex flex-col lg:flex-row gap-8">

      <PatientListPanel selectedPatientId={selectedPatientId} onSelect={setSelectedPatientId} />

      {/* Right Column */}
      <div className="w-full lg:w-2/3 flex flex-col h-full">
        <div className="bg-white/70 backdrop-blur-2xl rounded-[32px] border border-white shadow-xl shadow-sky-100/50 flex-1 overflow-hidden flex flex-col">

          {/* Header */}
          <div className="p-8 pb-6 border-b border-sky-50/50 flex justify-between items-center print:hidden">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">{selectedPatient.name}</h1>
                <span className="text-lg text-slate-500 font-medium">{selectedPatient.gender} / {selectedPatient.age}세</span>
              </div>
              {selectedPatient.patientNo && (
                <span className="text-xs text-slate-400 font-mono block mb-2">
                  {maskPatientId(selectedPatient.patientNo)}
                </span>
              )}
              <div className="flex gap-2">
                {selectedPatient.disease.split(', ').map(d => (
                  <span key={d} className="px-3 py-1 bg-sky-50 text-sky-600 rounded-full text-sm font-bold">{d}</span>
                ))}
              </div>
            </div>
            <div className="flex gap-3">
              <button
                aria-label="진료 기록 열기"
                className="p-3 bg-slate-50 hover:bg-slate-100 text-slate-600 rounded-2xl transition-colors"
              >
                <FileText className="w-5 h-5" strokeWidth={1.5} />
              </button>
              <button
                aria-label="환자에게 전화하기"
                className="p-3 bg-slate-50 hover:bg-slate-100 text-slate-600 rounded-2xl transition-colors"
              >
                <Phone className="w-5 h-5" strokeWidth={1.5} />
              </button>
            </div>
          </div>

          {/* Tab Bar */}
          <div role="tablist" className="px-8 pt-3 flex gap-1 border-b border-sky-50/50 print:hidden">
            {([
              { id: 'ai',   label: 'AI 분석',   icon: <Sparkles  className="w-4 h-4" /> },
              { id: 'soap', label: 'SOAP 노트', icon: <FileText  className="w-4 h-4" /> },
            ] as const).map(tab => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={activePanel === tab.id}
                onClick={() => setActivePanel(tab.id)}
                className={`px-5 py-2.5 rounded-t-2xl text-sm font-bold flex items-center gap-2 border-b-2 transition-all ${
                  activePanel === tab.id
                    ? 'text-sky-600 border-sky-400 bg-sky-50/50'
                    : 'text-slate-400 border-transparent hover:text-slate-600'
                }`}
              >
                {tab.icon}{tab.label}
              </button>
            ))}
          </div>

          {/* Scrollable Content */}
          <div id="soap-print-area" className="flex-1 overflow-y-auto p-8 space-y-8">
            {activePanel === 'ai' ? (
              <>
                <AIRecommendationSection
                  patient={selectedPatient}
                  theme={theme}
                  showAiDetails={showAiDetails}
                  onToggleDetails={() => setShowAiDetails(v => !v)}
                />
                <VitalsSection patient={selectedPatient} hoveredVital={hoveredVital} onHover={setHoveredVital} />
              </>
            ) : selectedPatient.soapNote ? (
              <SoapNoteView patient={selectedPatient} theme={theme} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
                <ClipboardList className="w-12 h-12 opacity-30" />
                <p className="font-bold">SOAP 노트 데이터가 없습니다.</p>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="p-6 border-t border-sky-50/50 bg-white/50 flex gap-4 print:hidden">
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
