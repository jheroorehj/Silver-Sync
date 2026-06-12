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
  Loader2,
  BookOpen,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts';
import { getSchedule, fetchPatient, getNurseQueue, getNurseVitals, getNurseFullVitals, runAndPoll } from '../lib/silverSyncApi';
import type { NurseVitalsSnapshot, LambdaStatus, LambdaVerdict, VisitVitals } from '../lib/silverSyncApi';
import { DAYS, STATUS_THEME_MAP } from '../constants';
import { DocStatusBadge } from './ui/StatusBadge';
import type { DocPatient, DocPatientStatus, StatusTheme, SoapNote } from '../types';

// ── Lambda helpers ────────────────────────────────────────────────────────

function verdictToStatus(verdict: LambdaVerdict): DocPatientStatus {
  return verdict.verdictLevel === 'red' ? 'orange'
    : verdict.verdictLevel === 'yellow' ? 'amber'
    : 'teal';
}

function effectiveStatus(_patient: DocPatient, ls?: LambdaStatus): DocPatientStatus {
  if (ls?.type === 'done') return verdictToStatus(ls.verdict);
  return 'pending';
}

function DeadlineBadge({ days }: { days: number }) {
  const label = days === 0 ? 'D-day' : `D-${days}`;
  const cls = days === 0
    ? 'bg-red-100 text-red-700 border border-red-200'
    : days <= 2
    ? 'bg-orange-100 text-orange-700 border border-orange-200'
    : days <= 4
    ? 'bg-amber-100 text-amber-700 border border-amber-200'
    : 'bg-slate-100 text-slate-500 border border-slate-200';
  return (
    <span className={`text-xs font-extrabold px-2 py-0.5 rounded-full shrink-0 ${cls}`}>
      {label}
    </span>
  );
}

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

function SoapNoteView({ patient, theme, guidelineEvidence }: {
  patient: DocPatient;
  theme: StatusTheme;
  guidelineEvidence?: { source: string; content: string }[];
}) {
  const soap = patient.soapNote as SoapNote;
  // lambdaState에서 직접 내려온 값 우선, 없으면 soapNote 안의 값 사용
  const evidence = (guidelineEvidence ?? soap.guidelineEvidence ?? []);

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
          {section.key === 'A' && evidence.length > 0 && (
            <div className="mt-4 pt-4 border-t border-white/60 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-500">
                <BookOpen className="w-3.5 h-3.5" />
                <span>참조 근거 지침</span>
              </div>
              {evidence.map((ev, i) => (
                <div key={i} className="p-3 bg-white/70 rounded-xl border border-white/80">
                  <p className={`text-xs font-bold mb-1 ${theme.detailStatColor}`}>{ev.source}</p>
                  <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">"{ev.content}"</p>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

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

function LambdaVerdictBanner({ lambdaState }: { lambdaState?: LambdaStatus }) {
  if (!lambdaState || lambdaState.type === 'idle') return null;

  if (lambdaState.type === 'loading') {
    return (
      <div className="flex items-center gap-3 px-5 py-4 rounded-2xl bg-sky-50 border border-sky-200 mb-5">
        <Loader2 className="w-5 h-5 text-sky-500 animate-spin shrink-0" />
        <div>
          <p className="font-bold text-sky-700 text-sm">Silver-Sync 멀티에이전트 분석 중...</p>
          <p className="text-sky-500 text-xs mt-0.5">AI 에이전트가 진료 지침 및 임상 데이터를 검토하고 있습니다</p>
        </div>
      </div>
    );
  }

  if (lambdaState.type === 'error') {
    return (
      <div className="flex items-center gap-3 px-5 py-4 rounded-2xl bg-slate-50 border border-slate-200 mb-5">
        <AlertCircle className="w-5 h-5 text-slate-400 shrink-0" />
        <p className="text-slate-500 text-sm font-medium">AI 분석 결과를 불러오지 못했습니다</p>
      </div>
    );
  }

  if (lambdaState.type === 'done') {
    const { verdict } = lambdaState;
    const isInPerson = verdict.consultationType === '대면';
    return (
      <div className={`flex items-center justify-between px-5 py-4 rounded-2xl border mb-5 ${
        isInPerson
          ? 'bg-orange-50 border-orange-200'
          : 'bg-teal-50 border-teal-200'
      }`}>
        <div className="flex items-center gap-3">
          {isInPerson
            ? <Stethoscope className="w-6 h-6 text-orange-600 shrink-0" strokeWidth={1.5} />
            : <Video className="w-6 h-6 text-teal-600 shrink-0" strokeWidth={1.5} />
          }
          <div>
            <p className={`font-bold text-base leading-tight ${isInPerson ? 'text-orange-700' : 'text-teal-700'}`}>
              {verdict.consultationType} 진료 {isInPerson ? '권고' : '가능'}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              신뢰도 {verdict.confidence}% · Silver-Sync AI
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-slate-800">
            {verdict.riskScore}
            <span className="text-sm font-normal text-slate-400">/100</span>
          </p>
          <p className="text-xs text-slate-500">위험도 점수</p>
        </div>
      </div>
    );
  }

  return null;
}

function AIRecommendationSection({
  patient, theme, lambdaState, showAiDetails, onToggleDetails,
}: {
  patient: DocPatient;
  theme: StatusTheme;
  lambdaState?: LambdaStatus;
  showAiDetails: boolean;
  onToggleDetails: () => void;
}) {
  // Grey placeholder for all non-done states
  if (!lambdaState || lambdaState.type !== 'done') {
    return (
      <div className="rounded-3xl p-8 border border-slate-200/50 bg-gradient-to-br from-slate-50 to-slate-100/30 relative overflow-hidden">
        <div className="flex items-center gap-2 mb-6">
          <Sparkles className="w-5 h-5 text-slate-300" strokeWidth={2} />
          <span className="font-bold tracking-wide text-slate-400">AI 분석 결과</span>
        </div>
        <div className="flex flex-col items-center justify-center py-8 gap-4 text-center">
          {lambdaState?.type === 'loading' ? (
            <>
              <div className="w-16 h-16 rounded-full bg-sky-50 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-sky-400 animate-spin" strokeWidth={1.5} />
              </div>
              <div>
                <p className="font-extrabold text-slate-500 text-xl">Silver-Sync 분석 중</p>
                <p className="text-slate-400 text-sm mt-2 leading-relaxed">
                  AI 에이전트가 진료 지침 및<br/>임상 데이터를 검토하고 있습니다
                </p>
              </div>
            </>
          ) : lambdaState?.type === 'error' ? (
            <>
              <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center">
                <AlertCircle className="w-8 h-8 text-slate-300" strokeWidth={1.5} />
              </div>
              <div>
                <p className="font-extrabold text-slate-400 text-xl">분석 결과를 불러오지 못했습니다</p>
                <p className="text-slate-400 text-sm mt-2">잠시 후 다시 시도해주세요</p>
              </div>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center">
                <Clock className="w-8 h-8 text-slate-300" strokeWidth={1.5} />
              </div>
              <div>
                <p className="font-extrabold text-slate-400 text-xl">간호사 방문 측정 대기 중</p>
                <p className="text-slate-400 text-sm mt-2 leading-relaxed">
                  간호사가 환자 수치를 입력하면<br/>AI 분석이 자동으로 시작됩니다
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // Full colored section when AI analysis is done
  const verdict = lambdaState.verdict;
  return (
    <div className={`rounded-3xl p-6 border relative overflow-hidden bg-gradient-to-br ${theme.gradient} ${theme.border}`}>
      <div className="absolute top-0 right-0 p-6 opacity-10">
        {verdict.verdictLevel === 'red'
          ? <Stethoscope className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
          : verdict.verdictLevel === 'yellow'
          ? <AlertTriangle className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
          : <Video className={`w-32 h-32 ${theme.iconColor}`} strokeWidth={1} />
        }
      </div>
      <div className="relative z-10">
        <LambdaVerdictBanner lambdaState={lambdaState} />
        <div className="flex items-center gap-2 mb-4">
          <Sparkles className={`w-5 h-5 ${theme.iconColor}`} strokeWidth={2} />
          <span className={`font-bold tracking-wide ${theme.labelColor}`}>AI 분석 결과</span>
        </div>
        <h2 className="text-xl sm:text-2xl font-bold text-slate-900 mb-4">
          {patient.aiRecommendation?.title}<br/>
          <span className={theme.highlightColor}>{patient.aiRecommendation?.highlight}</span>됩니다.
        </h2>
        <div className="space-y-3">
          {(patient.aiRecommendation?.reasons ?? []).map((reason, idx) => (
            <div key={idx} className="flex items-start gap-3">
              <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${reason.type === 'check' ? 'bg-teal-100' : 'bg-orange-100'}`}>
                {reason.type === 'up'    && <ArrowUpRight className="w-3 h-3 text-orange-600" strokeWidth={2.5} />}
                {reason.type === 'alert' && <AlertCircle  className="w-3 h-3 text-orange-600" strokeWidth={2.5} />}
                {reason.type === 'check' && <CheckCircle2 className="w-3 h-3 text-teal-600"   strokeWidth={2.5} />}
              </div>
              <p className="text-slate-700 text-sm leading-relaxed"><SafeText html={reason.text} /></p>
            </div>
          ))}
        </div>
        <div className="mt-2">
          <button
            onClick={onToggleDetails}
            className={`flex items-center gap-2 font-bold transition-colors ml-auto bg-transparent px-2 py-1 rounded-xl ${theme.detailsButtonColor}`}
          >
            {showAiDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            상세 보기
          </button>
          <AnimatePresence>
            {showAiDetails && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                <div className={`mt-6 p-6 bg-white/60 rounded-2xl border space-y-4 ${theme.detailBorder}`}>
                  <div className="flex items-center gap-2 text-slate-800 font-bold">
                    <Info className={`w-4 h-4 ${theme.iconColor}`} />
                    <span>다변수 맥락 추론 상세</span>
                  </div>
                  <p className="text-slate-600 text-sm leading-relaxed">{patient.aiRecommendation?.details}</p>
                  <div className="grid grid-cols-2 gap-4 pt-2">
                    {(patient.aiRecommendation?.stats ?? []).map((stat, idx) => (
                      <div key={idx} className={`p-3 rounded-xl ${theme.detailBg}`}>
                        <span className={`text-xs font-bold block mb-1 ${theme.detailStatColor}`}>{stat.label}</span>
                        <span className="text-sm font-bold text-slate-800">{stat.value}</span>
                      </div>
                    ))}
                  </div>
                  {verdict.guidelineEvidence && verdict.guidelineEvidence.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
                      <div className="flex items-center gap-2 text-slate-800 font-bold">
                        <BookOpen className={`w-4 h-4 ${theme.iconColor}`} />
                        <span>참조 근거 지침</span>
                      </div>
                      {verdict.guidelineEvidence.slice(0, 3).map((ev, i) => (
                        <div key={i} className="p-3 bg-white/60 rounded-xl border border-slate-100">
                          <p className={`text-xs font-bold mb-1 ${theme.detailStatColor}`}>
                            {ev.source === 'dynamodb_guidelines' ? '당뇨병 진료지침 2025' : ev.source}
                          </p>
                          <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">{ev.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

// ── Vitals Section ────────────────────────────────────────────────────────

function VitalsSection({ patient, hoveredVital, onHover, nurseSnapshot }: {
  patient: DocPatient;
  hoveredVital: string | null;
  onHover: (key: string | null) => void;
  nurseSnapshot?: NurseVitalsSnapshot;
}) {
  if (!patient.vitals) {
    return (
      <div>
        <h3 className="text-lg font-bold text-slate-800 mb-4 px-1">최근 바이탈 요약</h3>
        <div className="flex items-center justify-center py-10 text-slate-300">
          <p className="font-bold text-sm">바이탈 데이터 대기 중</p>
        </div>
      </div>
    );
  }

  const bpDisplay = nurseSnapshot?.bp || patient.vitals.bp.current;
  const sugarDisplay = nurseSnapshot?.sugar || patient.vitals.sugar.current;
  const isLive = !!nurseSnapshot;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4 px-1">
        <h3 className="text-lg font-bold text-slate-800">최근 바이탈 요약</h3>
        {isLive && (
          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 border border-sky-200">
            방문 측정값 반영
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <VitalCard isHovered={hoveredVital === 'bp'} onMouseEnter={() => onHover('bp')} onMouseLeave={() => onHover(null)} chartLabel="혈압 추이 (5일)" chartData={patient.vitals.bp.data} yDomain={['dataMin - 10', 'dataMax + 10']}>
          <div className="flex items-center gap-2 mb-3 text-slate-500"><HeartPulse className="w-4 h-4" strokeWidth={2} /><span className="font-semibold text-sm">혈압 (mmHg)</span></div>
          <div className="flex items-end gap-2">
            <span className="text-3xl font-extrabold text-slate-900 tracking-tighter">
              {bpDisplay.split('/')[0]}
              <span className="text-xl text-slate-400 font-medium">/{bpDisplay.split('/')[1]}</span>
            </span>
          </div>
          <p className={`text-sm font-medium mt-2 flex items-center ${patient.vitals.bp.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
            {patient.vitals.bp.trendUp && <ArrowUpRight className="w-3 h-3 mr-1" strokeWidth={2.5} />}
            {isLive ? '방문 간호 측정값' : patient.vitals.bp.trend}
          </p>
        </VitalCard>

        <VitalCard isHovered={hoveredVital === 'sugar'} onMouseEnter={() => onHover('sugar')} onMouseLeave={() => onHover(null)} chartLabel="혈당 추이 (5일)" chartData={patient.vitals.sugar.data} yDomain={['dataMin - 10', 'dataMax + 10']}>
          <div className="flex items-center gap-2 mb-3 text-slate-500"><Activity className="w-4 h-4" strokeWidth={2} /><span className="font-semibold text-sm">공복혈당 (mg/dL)</span></div>
          <div className="flex items-end gap-2"><span className="text-3xl font-extrabold text-slate-900 tracking-tighter">{sugarDisplay}</span></div>
          <p className={`text-sm font-medium mt-2 flex items-center ${patient.vitals.sugar.trendUp ? 'text-orange-500' : 'text-teal-500'}`}>
            {isLive ? '방문 간호 측정값' : patient.vitals.sugar.status}
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

function PatientListPanel({ patients, selectedPatientId, onSelect, lambdaStates }: {
  patients: DocPatient[];
  selectedPatientId: number | null;
  onSelect: (id: number) => void;
  lambdaStates: Record<number, LambdaStatus>;
}) {
  return (
    <div className="w-full lg:w-1/3 flex flex-col h-full">
      <div className="flex items-center justify-between mb-6 px-2">
        <h2 className="text-xl font-extrabold text-slate-800 tracking-tight">재진 대상 환자</h2>
        <span className="bg-cyan-100 text-cyan-700 px-3 py-1 rounded-full text-sm font-bold">총 {patients.length}명</span>
      </div>
      <div className="flex-1 overflow-y-auto pr-2 space-y-4 pb-8">
        {patients.map((patient) => {
          const ls = lambdaStates[patient.id];
          const status = effectiveStatus(patient, ls);
          return (
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
                <div className="flex items-center gap-2 min-w-0">
                  <DocStatusBadge status={status} />
                  <span className="text-lg font-bold text-slate-900 truncate">{patient.name}</span>
                  <span className="text-sm font-medium text-slate-500 shrink-0">{patient.gender}/{patient.age}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                  {ls?.type === 'loading' && (
                    <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500 bg-slate-100/80 px-3 py-1 rounded-full">{patient.disease}</span>
                {ls?.type === 'done' && (
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                    ls.verdict.consultationType === '대면'
                      ? 'bg-orange-100 text-orange-700'
                      : 'bg-teal-100 text-teal-700'
                  }`}>
                    {ls.verdict.consultationType}
                  </span>
                )}
                {selectedPatientId === patient.id && !ls?.type && (
                  <ChevronRight className="w-5 h-5 text-cyan-500" strokeWidth={2} />
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Patch verdict with nurse's actual submitted vitals ────────────────────
// S3 파싱값보다 간호사가 직접 입력한 localStorage 값이 신뢰도 높음

function patchVerdictWithNurse(verdict: LambdaVerdict, fv: VisitVitals): LambdaVerdict {
  const bpStr = (fv.systolic && fv.diastolic)
    ? `${fv.systolic}/${fv.diastolic}`
    : verdict.bpCurrent;
  const sugarStr = fv.blood_sugar != null
    ? String(fv.blood_sugar)
    : verdict.sugarCurrent;

  // 히스토리 데이터의 마지막 포인트를 실제 측정값으로 교체 (더 신뢰 가능한 값)
  const bpData = verdict.bpData ? [...verdict.bpData] : [];
  if (fv.systolic) {
    if (bpData.length > 0) bpData[bpData.length - 1] = fv.systolic;
    else bpData.push(fv.systolic);
  }
  const sugarData = verdict.sugarData ? [...verdict.sugarData] : [];
  if (fv.blood_sugar != null) {
    if (sugarData.length > 0) sugarData[sugarData.length - 1] = fv.blood_sugar;
    else sugarData.push(fv.blood_sugar);
  }

  // SOAP S: 간호사가 선택한 관찰 항목 + 메모
  const subjectiveParts = [...fv.observations, fv.notes].filter(Boolean);
  const nurseSubjective = subjectiveParts.join('. ');

  // SOAP O: 간호사가 직접 측정한 수치
  const objParts: string[] = [];
  if (fv.systolic && fv.diastolic) objParts.push(`혈압 ${fv.systolic}/${fv.diastolic} mmHg`);
  if (fv.blood_sugar != null) objParts.push(`공복혈당 ${fv.blood_sugar} mg/dL`);
  if (fv.medication_status === 'well') objParts.push('복약 순응 양호');
  else if (fv.medication_status === 'missed') objParts.push('복약 미순응');
  // HbA1c/순응도는 S3 파싱값 유지
  const originalObj = verdict.soapNote?.objective ?? '';
  const hba1cMatch = originalObj.match(/HbA1c [\d.]+%/);
  const adherenceMatch = originalObj.match(/복약 순응도 \d+%/);
  if (hba1cMatch) objParts.push(hba1cMatch[0]);
  if (adherenceMatch) objParts.push(adherenceMatch[0]);

  // AI Recommendation stats 패치 (다변수 맥락 추론 상세 그리드)
  const patchedStats = (verdict.recommendation?.stats ?? []).map(s => {
    if (s.label === '혈압' && fv.systolic && fv.diastolic)
      return { ...s, value: `${fv.systolic}/${fv.diastolic} mmHg` };
    if (s.label === '공복혈당' && fv.blood_sugar != null)
      return { ...s, value: `${fv.blood_sugar} mg/dL` };
    return s;
  });

  return {
    ...verdict,
    bpCurrent: bpStr,
    sugarCurrent: sugarStr,
    bpTrendUp: fv.systolic != null && bpData.length >= 2
      ? fv.systolic > bpData[bpData.length - 2]
      : verdict.bpTrendUp,
    sugarTrendUp: fv.blood_sugar != null && sugarData.length >= 2
      ? fv.blood_sugar > sugarData[sugarData.length - 2]
      : verdict.sugarTrendUp,
    bpData,
    sugarData,
    soapNote: verdict.soapNote ? {
      ...verdict.soapNote,
      subjective: nurseSubjective || verdict.soapNote.subjective,
      objective: objParts.length > 0 ? objParts.join('. ') : verdict.soapNote.objective,
    } : undefined,
    recommendation: verdict.recommendation ? {
      ...verdict.recommendation,
      stats: patchedStats,
    } : undefined,
  };
}

// fullVitals 없을 때 NurseVitalsSnapshot으로 최소한 bp/sugar 패치
function snapshotToVisitVitals(snap: NurseVitalsSnapshot): VisitVitals {
  const parts = snap.bp.split('/');
  return {
    systolic: parts[0] ? Number(parts[0]) : null,
    diastolic: parts[1] ? Number(parts[1]) : null,
    blood_sugar: snap.sugar ? Number(snap.sugar) : null,
    medication_status: '',
    observations: [],
    notes: '',
  };
}

// ── Apply verdict to patient state ────────────────────────────────────────

function applyVerdictToPatient(patient: DocPatient, verdict: LambdaVerdict): DocPatient {
  const status = verdict.verdictLevel === 'red' ? 'orange' : verdict.verdictLevel === 'yellow' ? 'amber' : 'teal';
  return {
    ...patient,
    status,
    disease: verdict.conditions?.join(', ') || patient.disease,
    vitals: verdict.bpData ? {
      bp: { current: verdict.bpCurrent!, trendUp: verdict.bpTrendUp, data: verdict.bpData },
      sugar: { current: verdict.sugarCurrent!, trendUp: verdict.sugarTrendUp, data: verdict.sugarData! },
      adherence: { current: String(verdict.adherenceRate ?? 0), data: verdict.adherenceData! },
    } : patient.vitals,
    soapNote: verdict.soapNote ?? patient.soapNote,
    aiRecommendation: verdict.recommendation ?? patient.aiRecommendation,
    footerAction: verdict.footerAction ?? patient.footerAction,
  };
}

// ── Main Dashboard ─────────────────────────────────────────────────────────

export default function DoctorDashboard() {
  const [patients, setPatients] = useState<DocPatient[]>([]);
  const [isLoadingPatients, setIsLoadingPatients] = useState(true);
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const [showAiDetails, setShowAiDetails] = useState(false);
  const [hoveredVital, setHoveredVital] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<'ai' | 'soap'>('ai');
  const [lambdaStates, setLambdaStates] = useState<Record<number, LambdaStatus>>({});
  const [nurseVitals, setNurseVitals] = useState<Record<number, NurseVitalsSnapshot>>({});

  // 스케줄 로드 → 환자 정보 fetch → 제출된 환자 Lambda 폴링
  useEffect(() => {
    const schedule = getSchedule();
    const controllers: AbortController[] = [];
    let isMounted = true;

    (async () => {
      if (schedule.length === 0) {
        setIsLoadingPatients(false);
        return;
      }

      const results = await Promise.all(
        schedule.map(async ({ lambdaPatientId, time }, idx) => {
          try {
            const info = await fetchPatient(lambdaPatientId);
            return {
              id: idx + 1,
              name: info.name,
              age: info.age,
              gender: info.gender === 'F' ? '여' : '남',
              time,
              status: 'pending' as const,
              lambdaPatientId,
              disease: info.conditions.join(', '),
            } as DocPatient;
          } catch {
            return null;
          }
        })
      );

      if (!isMounted) return;

      const valid = results
        .filter((p): p is DocPatient => p !== null)
        .sort((a, b) => a.time.localeCompare(b.time));

      setPatients(valid);
      if (valid.length > 0) setSelectedPatientId(valid[0].id);
      setIsLoadingPatients(false);

      // 이미 제출된 환자 폴링
      const queue = getNurseQueue();
      queue.forEach(({ patientId }) => {
        const patient = valid.find(p => p.lambdaPatientId === patientId);
        if (!patient) return;

        setLambdaStates(prev => ({ ...prev, [patient.id]: { type: 'loading' } }));
        const ctrl = new AbortController();
        controllers.push(ctrl);

        runAndPoll(
          patientId,
          (rawVerdict) => {
            if (!isMounted) return;
            const fullVitals = getNurseFullVitals(patientId);
            const snapshot = getNurseVitals(patientId);
            // fullVitals 우선, 없으면 snapshot(bp+sugar만)으로라도 패치
            const vitalsSource = fullVitals ?? (snapshot ? snapshotToVisitVitals(snapshot) : null);
            const verdict = vitalsSource ? patchVerdictWithNurse(rawVerdict, vitalsSource) : rawVerdict;
            setLambdaStates(prev => ({ ...prev, [patient.id]: { type: 'done', verdict } }));
            setPatients(prev => prev.map(p =>
              p.id === patient.id ? applyVerdictToPatient(p, verdict) : p
            ));
            if (snapshot) setNurseVitals(prev => ({ ...prev, [patient.id]: snapshot }));
          },
          ctrl.signal,
        ).catch(() => {
          if (!ctrl.signal.aborted && isMounted) {
            setLambdaStates(prev => ({ ...prev, [patient.id]: { type: 'error' } }));
          }
        });
      });
    })();

    return () => {
      isMounted = false;
      controllers.forEach(c => c.abort());
    };
  }, []);

  useEffect(() => {
    setShowAiDetails(false);
    setActivePanel('ai');
  }, [selectedPatientId]);

  // 로딩 중
  if (isLoadingPatients) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-5rem)]">
        <div className="flex flex-col items-center gap-4 text-slate-400">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p className="font-bold">오늘의 방문 일정을 불러오는 중...</p>
        </div>
      </div>
    );
  }

  // 일정 없음 (간호사 앱 미실행)
  if (patients.length === 0) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-5rem)]">
        <div className="flex flex-col items-center gap-4 text-slate-400">
          <ClipboardList className="w-12 h-12 opacity-30" />
          <p className="font-bold text-lg">오늘 예정된 방문 환자가 없습니다</p>
          <p className="text-sm">간호사 앱에서 오늘의 일정을 먼저 로드해주세요</p>
        </div>
      </div>
    );
  }

  const selectedPatient = patients.find(p => p.id === selectedPatientId) ?? patients[0];
  const lambdaState = lambdaStates[selectedPatient.id];
  const theme = STATUS_THEME_MAP[effectiveStatus(selectedPatient, lambdaState)];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 h-[calc(100vh-5rem)] flex flex-col lg:flex-row gap-8">

      <PatientListPanel
        patients={patients}
        selectedPatientId={selectedPatientId}
        onSelect={setSelectedPatientId}
        lambdaStates={lambdaStates}
      />

      {/* Right Column */}
      <div className="w-full lg:w-2/3 flex flex-col h-full">
        <div className="bg-white/70 backdrop-blur-2xl rounded-[32px] border border-white shadow-xl shadow-sky-100/50 flex-1 overflow-hidden flex flex-col">

          {/* Header */}
          <div className="p-8 pb-6 border-b border-sky-50/50 flex justify-between items-center print:hidden">
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

          {/* Tab Bar */}
          <div className="px-8 pt-3 flex gap-1 border-b border-sky-50/50 print:hidden">
            {([
              { id: 'ai',   label: 'AI 분석',   icon: <Sparkles  className="w-4 h-4" /> },
              { id: 'soap', label: 'SOAP 노트', icon: <FileText  className="w-4 h-4" /> },
            ] as const).map(tab => (
              <button
                key={tab.id}
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
                  lambdaState={lambdaState}
                  showAiDetails={showAiDetails}
                  onToggleDetails={() => setShowAiDetails(v => !v)}
                />
                <VitalsSection
                  patient={selectedPatient}
                  hoveredVital={hoveredVital}
                  onHover={setHoveredVital}
                  nurseSnapshot={nurseVitals[selectedPatient.id]}
                />
              </>
            ) : selectedPatient.soapNote ? (
              <SoapNoteView
                patient={selectedPatient}
                theme={theme}
                guidelineEvidence={lambdaState?.type === 'done' ? lambdaState.verdict.guidelineEvidence : undefined}
              />
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
              {lambdaState?.type === 'done' ? (selectedPatient.footerAction ?? '진료 예약하기') : 'AI 분석 후 결정'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
