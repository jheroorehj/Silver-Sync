import React, { useEffect, useState } from 'react';
import QRCode from 'react-qr-code';
import {
  ArrowLeft, Check, ChevronRight, Footprints, HeartHandshake, MapPin, Phone, Pill,
  QrCode, Siren, Stethoscope, Sun, Moon, Volume2, Square, Type, X, Clock,
} from 'lucide-react';

// 고령·디지털 취약 계층을 위한 환자 화면
// - 한 화면에 한 가지 일, 본문 20px 이상, 버튼 높이 64px 이상
// - 아이콘에는 항상 글자를 함께, 색만으로 의미를 전달하지 않음
// - 어려운 의학 용어 대신 쉬운 말, 읽어주기·글자 크게 제공

type View = 'home' | 'qr' | 'pharmacy' | 'help';

const PATIENT = { name: '박대호', clinic: '실버싱크 내과' };

const MEDICINES = [
  { plain: '혈압약', name: '암로디핀 5mg', when: '하루 1번, 아침 식사 후' },
  { plain: '당뇨약', name: '메트포르민 500mg', when: '하루 2번, 아침·저녁 식사 후' },
];

const PHARMACIES = [
  { no: 1, name: '행복 온누리 약국', walk: '걸어서 5분', dist: '350m', open: '저녁 9시까지 문 열어요', tel: '02-000-0001', stock: true },
  { no: 2, name: '건강제일 약국', walk: '걸어서 12분', dist: '800m', open: '저녁 7시까지 문 열어요', tel: '02-000-0002', stock: true },
  { no: 3, name: '사랑 약국', walk: '걸어서 18분', dist: '1.2km', open: '저녁 8시까지 문 열어요', tel: '02-000-0003', stock: false },
];

const CONTACTS = [
  { label: '딸 박지은', sub: '보호자', tel: '010-0000-0000', icon: HeartHandshake },
  { label: PATIENT.clinic, sub: '진료 병원', tel: '02-000-1000', icon: Stethoscope },
  { label: '방문 간호사', sub: '실버싱크 방문간호팀', tel: '02-000-2000', icon: Phone },
];

const LARGE_TEXT_KEY = 'silversync_patient_large_text';
const todayKey = () => new Date().toISOString().slice(0, 10);
const medsKey = () => `silversync_patient_meds_${todayKey()}`;

function formatDate(d: Date) {
  return d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' });
}

function nextVisitDate() {
  const d = new Date();
  d.setDate(d.getDate() + 28);
  return formatDate(d);
}

// ── 읽어주기 (브라우저 내장 음성) ─────────────────────────────────────────

function useSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  useEffect(() => () => { if (supported) window.speechSynthesis.cancel(); }, [supported]);

  const speak = (text: string) => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'ko-KR';
    u.rate = 0.85;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(u);
  };
  const stop = () => { if (supported) window.speechSynthesis.cancel(); setSpeaking(false); };

  return { supported, speaking, speak, stop };
}

// ── Main ──────────────────────────────────────────────────────────────────

export default function PatientApp() {
  const [view, setView] = useState<View>('home');
  const [largeText, setLargeText] = useState(() => localStorage.getItem(LARGE_TEXT_KEY) === '1');
  const [meds, setMeds] = useState<{ morning: boolean; evening: boolean }>(() => {
    try { return JSON.parse(localStorage.getItem(medsKey()) ?? '') ; } catch { return { morning: false, evening: false }; }
  });
  const speech = useSpeech();

  useEffect(() => { localStorage.setItem(LARGE_TEXT_KEY, largeText ? '1' : '0'); }, [largeText]);
  useEffect(() => { localStorage.setItem(medsKey(), JSON.stringify(meds)); }, [meds]);

  const go = (v: View) => { speech.stop(); setView(v); window.scrollTo({ top: 0 }); };

  const visit = nextVisitDate();
  const readTexts: Record<View, string> = {
    home: `${PATIENT.name} 님, 안녕하세요. 의사 선생님 안내입니다. 건강 상태가 안정적이에요. 지금 드시는 약을 그대로 드세요. 다음 진료는 ${visit} 오전 10시에 전화로 합니다. 병원에 오지 않으셔도 됩니다. 오늘 아침 약은 ${meds.morning ? '드셨습니다' : '아직 안 드셨습니다'}. 저녁 약은 ${meds.evening ? '드셨습니다' : '아직 안 드셨습니다'}.`,
    qr: `약국에 가시면 약사님께 이 화면을 보여주세요. 처방 약은 ${MEDICINES.map(m => `${m.plain}, ${m.when}`).join('. ')}입니다.`,
    pharmacy: `가까운 약국입니다. ${PHARMACIES.map(p => `${p.no}번 ${p.name}, ${p.walk}, ${p.stock ? '약이 있어요' : '이 약이 없어요'}`).join('. ')}.`,
    help: `도움이 필요하시면 전화할 분을 누르세요. ${CONTACTS.map(c => c.label).join(', ')}에게 전화할 수 있어요. 숨이 차거나 가슴이 아프면 119를 누르세요.`,
  };

  return (
    <div className="max-w-md mx-auto bg-sky-50 min-h-screen font-sans break-keep selection:bg-sky-200">
      {/* 도구 막대: 처음으로 · 읽어주기 · 글자 크게 */}
      <div className="px-4 pt-4 flex items-center gap-2">
        {view !== 'home' ? (
          <button onClick={() => go('home')}
            className="h-16 px-4 bg-white rounded-2xl border-2 border-sky-200 flex items-center gap-2 text-xl font-extrabold text-slate-800 active:scale-[0.97] transition-transform">
            <ArrowLeft className="w-6 h-6 text-sky-600" strokeWidth={3} />
            처음으로
          </button>
        ) : <div className="flex-1" />}
        {view !== 'home' && <div className="flex-1" />}
        {speech.supported && (
          <button onClick={() => speech.speaking ? speech.stop() : speech.speak(readTexts[view])}
            aria-pressed={speech.speaking}
            className={`h-16 w-20 rounded-2xl border-2 flex flex-col items-center justify-center text-[15px] font-extrabold transition-colors ${speech.speaking ? 'bg-sky-700 border-sky-700 text-white' : 'bg-white border-sky-200 text-slate-800'}`}>
            {speech.speaking ? <Square className="w-6 h-6" strokeWidth={3} /> : <Volume2 className="w-6 h-6 text-sky-600" strokeWidth={2.5} />}
            {speech.speaking ? '멈추기' : '읽어주기'}
          </button>
        )}
        <button onClick={() => setLargeText(v => !v)} aria-pressed={largeText}
          className={`h-16 w-20 rounded-2xl border-2 flex flex-col items-center justify-center text-[15px] font-extrabold transition-colors ${largeText ? 'bg-sky-700 border-sky-700 text-white' : 'bg-white border-sky-200 text-slate-800'}`}>
          <Type className={`w-6 h-6 ${largeText ? 'text-white' : 'text-sky-600'}`} strokeWidth={2.5} />
          {largeText ? '보통 글자' : '글자 크게'}
        </button>
      </div>

      <div style={{ zoom: largeText ? 1.18 : 1 }} className="px-4 pt-5 pb-12">
        {view === 'home' && <HomeView visit={visit} meds={meds} setMeds={setMeds} go={go} />}
        {view === 'qr' && <PrescriptionView />}
        {view === 'pharmacy' && <PharmacyView />}
        {view === 'help' && <HelpView />}
      </div>
    </div>
  );
}

// ── 홈 ────────────────────────────────────────────────────────────────────

function HomeView({ visit, meds, setMeds, go }: {
  visit: string;
  meds: { morning: boolean; evening: boolean };
  setMeds: React.Dispatch<React.SetStateAction<{ morning: boolean; evening: boolean }>>;
  go: (v: View) => void;
}) {
  return (
    <div className="space-y-5">
      <div className="px-1">
        <p className="text-lg font-bold text-slate-600">{formatDate(new Date())}</p>
        <h1 className="text-3xl font-black text-slate-900 leading-snug mt-1">{PATIENT.name} 님,<br />안녕하세요</h1>
      </div>

      {/* 의사 선생님 안내 */}
      <section aria-labelledby="doctor-note" data-tour="patient-doctor-note" className="bg-white rounded-[32px] p-6 border-2 border-teal-200 shadow-sm shadow-teal-100/50">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-2xl bg-teal-100 flex items-center justify-center shrink-0">
            <Check className="w-7 h-7 text-teal-700" strokeWidth={3} />
          </div>
          <div>
            <p className="text-base font-bold text-teal-700">의사 선생님 안내</p>
            <h2 id="doctor-note" className="text-2xl font-black text-slate-900">건강 상태가 안정적이에요</h2>
          </div>
        </div>
        <ul className="space-y-3 text-xl font-semibold text-slate-800 leading-relaxed">
          <li className="flex gap-3"><Pill className="w-6 h-6 text-teal-600 shrink-0 mt-1" strokeWidth={2.5} />지금 드시는 약을 그대로 드세요.</li>
          <li className="flex gap-3"><Phone className="w-6 h-6 text-teal-600 shrink-0 mt-1" strokeWidth={2.5} />
            <span>다음 진료는 <strong className="font-black text-slate-900">전화로</strong> 해요.<br />병원에 오지 않으셔도 돼요.</span>
          </li>
        </ul>
        <div className="mt-5 bg-teal-50 rounded-2xl p-4 flex items-center gap-3">
          <Clock className="w-7 h-7 text-teal-700 shrink-0" strokeWidth={2.5} />
          <p className="text-xl font-black text-slate-900">{visit}<br /><span className="text-teal-800">오전 10시</span></p>
        </div>
      </section>

      {/* 오늘 약 */}
      <section aria-labelledby="meds-today" className="bg-white rounded-[32px] p-6 border border-sky-100 shadow-sm shadow-sky-100/40">
        <h2 id="meds-today" className="text-2xl font-black text-slate-900 mb-1">오늘 약 드셨나요?</h2>
        <p className="text-lg font-semibold text-slate-600 mb-4">드신 다음 버튼을 눌러주세요.</p>
        <div className="grid grid-cols-2 gap-3">
          {([['morning', '아침 약', Sun], ['evening', '저녁 약', Moon]] as const).map(([key, label, Icon]) => {
            const done = meds[key];
            return (
              <button key={key} onClick={() => setMeds(m => ({ ...m, [key]: !m[key] }))} aria-pressed={done}
                className={`min-h-28 rounded-3xl border-2 p-3 flex flex-col items-center justify-center gap-1 transition-colors active:scale-[0.97] ${done ? 'bg-teal-700 border-teal-700 text-white' : 'bg-white border-sky-200 text-slate-800'}`}>
                <Icon className={`w-8 h-8 ${done ? 'text-white' : 'text-sky-600'}`} strokeWidth={2.5} />
                <span className="text-xl font-black">{label}</span>
                <span className={`text-base font-bold flex items-center gap-1 ${done ? 'text-teal-50' : 'text-slate-600'}`}>
                  {done ? <><Check className="w-5 h-5" strokeWidth={3} />먹었어요</> : '아직이에요'}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* 큰 메뉴 */}
      <nav aria-label="환자 메뉴" className="space-y-3">
        <MenuButton icon={QrCode} title="처방전 보여주기" sub="약국에서 이 화면을 보여주세요" onClick={() => go('qr')} primary />
        <MenuButton icon={MapPin} title="가까운 약국 찾기" sub="걸어서 갈 수 있는 약국" onClick={() => go('pharmacy')} />
        <MenuButton icon={HeartHandshake} title="도움이 필요해요" sub="가족·병원에 전화하기" onClick={() => go('help')} />
      </nav>
    </div>
  );
}

function MenuButton({ icon: Icon, title, sub, onClick, primary }: {
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  title: string; sub: string; onClick: () => void; primary?: boolean;
}) {
  return (
    <button onClick={onClick}
      className={`w-full min-h-24 rounded-[28px] px-5 py-4 flex items-center gap-4 text-left border-2 transition-transform active:scale-[0.98] ${primary ? 'bg-gradient-to-r from-sky-700 to-cyan-700 border-transparent text-white shadow-lg shadow-cyan-200/50' : 'bg-white border-sky-200 text-slate-900'}`}>
      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${primary ? 'bg-white/20' : 'bg-sky-50'}`}>
        <Icon className={`w-8 h-8 ${primary ? 'text-white' : 'text-sky-600'}`} strokeWidth={2.5} />
      </div>
      <div className="flex-1">
        <p className="text-2xl font-black">{title}</p>
        <p className={`text-lg font-semibold ${primary ? 'text-white' : 'text-slate-600'}`}>{sub}</p>
      </div>
      <ChevronRight className={`w-7 h-7 shrink-0 ${primary ? 'text-white' : 'text-sky-600'}`} strokeWidth={3} />
    </button>
  );
}

// ── 처방전 QR ─────────────────────────────────────────────────────────────

function PrescriptionView() {
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-black text-slate-900 leading-snug px-1">약사님께<br /><span className="text-sky-700">이 화면을 보여주세요</span></h1>

      <div className="bg-white p-6 rounded-[32px] shadow-xl shadow-slate-200/50 border border-slate-100 flex justify-center">
        <QRCode value="https://silver-sync.app/prescription/12345" size={240} level="H" fgColor="#0f172a"
          title={`${PATIENT.name} 님 처방전 QR 코드`} />
      </div>
      <p className="text-lg font-semibold text-slate-600 text-center">화면이 어두우면 밝기를 올려주세요.</p>

      <section aria-labelledby="rx-list" className="bg-white rounded-[32px] p-6 border border-sky-100">
        <h2 id="rx-list" className="text-2xl font-black text-slate-900 mb-4">처방 받은 약</h2>
        <ul className="space-y-4">
          {MEDICINES.map(m => (
            <li key={m.name} className="flex gap-4 items-start">
              <div className="w-12 h-12 rounded-2xl bg-sky-50 flex items-center justify-center shrink-0">
                <Pill className="w-7 h-7 text-sky-600" strokeWidth={2.5} />
              </div>
              <div>
                <p className="text-xl font-black text-slate-900">{m.plain} <span className="text-lg font-semibold text-slate-600">({m.name})</span></p>
                <p className="text-xl font-semibold text-slate-700">{m.when}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// ── 약국 찾기 ─────────────────────────────────────────────────────────────

function PharmacyMap() {
  // 외부 이미지 없이 그린 간단한 동네 지도 (오프라인에서도 표시)
  const pins = [
    { no: 1, x: 255, y: 70, stock: true },
    { no: 2, x: 90, y: 60, stock: true },
    { no: 3, x: 300, y: 175, stock: false },
  ];
  return (
    <svg viewBox="0 0 360 220" role="img" aria-label="내 위치와 가까운 약국 3곳을 표시한 지도" className="w-full h-auto rounded-[28px] bg-sky-50 border border-sky-100">
      <rect x="0" y="0" width="360" height="220" fill="#f0f9ff" />
      {/* 공원 */}
      <rect x="20" y="130" width="90" height="70" rx="14" fill="#ccfbf1" />
      <text x="65" y="170" textAnchor="middle" fontSize="13" fontWeight="700" fill="#0f766e">공원</text>
      {/* 도로 */}
      <path d="M0 110 H360" stroke="#ffffff" strokeWidth="22" />
      <path d="M170 0 V220" stroke="#ffffff" strokeWidth="22" />
      <path d="M0 110 H360 M170 0 V220" stroke="#e0f2fe" strokeWidth="2" strokeDasharray="8 8" />
      {/* 내 위치 */}
      <circle cx="170" cy="110" r="22" fill="#0ea5e9" opacity="0.18" />
      <circle cx="170" cy="110" r="10" fill="#0284c7" stroke="#ffffff" strokeWidth="4" />
      <rect x="128" y="132" width="84" height="26" rx="13" fill="#0369a1" />
      <text x="170" y="150" textAnchor="middle" fontSize="14" fontWeight="800" fill="#ffffff">내 위치</text>
      {/* 약국 */}
      {pins.map(p => (
        <g key={p.no}>
          <circle cx={p.x} cy={p.y} r="17" fill={p.stock ? '#0f766e' : '#64748b'} stroke="#ffffff" strokeWidth="3" />
          <text x={p.x} y={p.y + 6} textAnchor="middle" fontSize="17" fontWeight="900" fill="#ffffff">{p.no}</text>
        </g>
      ))}
    </svg>
  );
}

function PharmacyView() {
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-black text-slate-900 px-1">가까운 약국</h1>
      <PharmacyMap />
      <ul className="space-y-4">
        {PHARMACIES.map(p => (
          <li key={p.no} className={`rounded-[28px] p-5 border-2 ${p.stock ? 'bg-white border-sky-100' : 'bg-slate-50 border-slate-200'}`}>
            <div className="flex items-start gap-3 mb-3">
              <span aria-hidden className={`w-10 h-10 rounded-full flex items-center justify-center text-xl font-black text-white shrink-0 ${p.stock ? 'bg-teal-700' : 'bg-slate-500'}`}>{p.no}</span>
              <div className="flex-1">
                <h2 className="text-2xl font-black text-slate-900">{p.name}</h2>
                <p className="text-lg font-bold text-slate-700 flex items-center gap-2 mt-1">
                  <Footprints className="w-5 h-5 text-sky-600" strokeWidth={2.5} />{p.walk} <span className="text-slate-600 font-semibold">({p.dist})</span>
                </p>
              </div>
            </div>
            <p className={`text-xl font-black flex items-center gap-2 mb-1 ${p.stock ? 'text-teal-700' : 'text-slate-700'}`}>
              {p.stock ? <Check className="w-6 h-6" strokeWidth={3} /> : <X className="w-6 h-6" strokeWidth={3} />}
              {p.stock ? '처방 약이 있어요' : '이 약국에는 처방 약이 없어요'}
            </p>
            <p className="text-lg font-semibold text-slate-600 mb-4">{p.open}</p>
            {p.stock && (
              <a href={`tel:${p.tel}`}
                className="w-full h-16 bg-sky-700 text-white rounded-2xl flex items-center justify-center gap-2 text-xl font-black active:scale-[0.98] transition-transform">
                <Phone className="w-6 h-6" strokeWidth={2.5} /> 약국에 전화하기
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── 도움 요청 ─────────────────────────────────────────────────────────────

function HelpView() {
  return (
    <div className="space-y-5">
      <h1 className="text-3xl font-black text-slate-900 leading-snug px-1">누구에게<br />전화할까요?</h1>
      <ul className="space-y-3">
        {CONTACTS.map(c => (
          <li key={c.label}>
            <a href={`tel:${c.tel}`}
              className="block w-full bg-white rounded-[28px] p-5 border-2 border-sky-200 active:scale-[0.98] transition-transform">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-14 h-14 rounded-2xl bg-sky-50 flex items-center justify-center shrink-0">
                  <c.icon className="w-8 h-8 text-sky-600" strokeWidth={2.5} />
                </div>
                <div className="flex-1">
                  <p className="text-2xl font-black text-slate-900">{c.label}</p>
                  <p className="text-lg font-semibold text-slate-600">{c.sub}</p>
                </div>
              </div>
              <span className="w-full h-16 rounded-2xl bg-sky-700 text-white text-xl font-black flex items-center justify-center gap-2">
                <Phone className="w-6 h-6" strokeWidth={2.5} />전화하기
              </span>
            </a>
          </li>
        ))}
      </ul>

      <div className="bg-white rounded-[28px] p-5 border-2 border-red-200">
        <p className="text-xl font-bold text-slate-800 mb-3">숨이 차거나 가슴이 아프면<br />바로 119에 전화하세요.</p>
        <a href="tel:119"
          className="w-full h-16 bg-red-600 text-white rounded-2xl flex items-center justify-center gap-2 text-2xl font-black active:scale-[0.98] transition-transform">
          <Siren className="w-7 h-7" strokeWidth={2.5} /> 119 응급 전화
        </a>
      </div>
    </div>
  );
}
