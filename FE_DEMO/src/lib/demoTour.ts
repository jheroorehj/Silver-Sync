// 현장 시연용 가이드 투어 (driver.js)
// - 클릭 단계: 강조된 요소를 실제로 눌러야만 다음으로 (배경 클릭·ESC로 건너뛰기 불가)
// - 입력 단계: 값을 채워야 켜지는 "입력 완료" 버튼으로만 다음으로
// - 대기 단계: AI 에이전트 분석이 끝날 때까지 기다렸다가 자동으로 다음으로
// - 일시정지: 어두운 화면을 걷고 자유롭게 확인한 뒤, 헤더 "이어하기"로 멈춘 단계부터 계속
// - ?demo=true 로 접속하면 데모 데이터를 초기화하고 1단계부터 자동 시작

import { driver, type Driver, type DriveStep, type Side } from 'driver.js';
import 'driver.js/dist/driver.css';
import { clearCache, getDemoAnalysis, getNurseQueue } from './silverSyncApi';

const DEMO_PATIENT = 'EDGE-E3-0001';
const sel = (key: string) => `[data-tour="${key}"]`;

type Base = { target: string; action: string; meaning: string; side?: Side };
type ClickStep = Base & { kind: 'click' };
type GateStep = Base & {
  kind: 'gate';
  doneText: string;
  ready: (el: Element) => boolean;
  example?: { label: string; fill: (el: Element) => void };
};
type WaitStep = Base & { kind: 'wait' };
type TourStep = ClickStep | GateStep | WaitStep;

// ── 입력 도우미: React 제어 컴포넌트에 값 넣기 ─────────────────────────────

function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

const filledInputs = (el: Element) =>
  [...el.querySelectorAll('input')].every(i => (i as HTMLInputElement).value.trim() !== '');

// ── 시연 순서 ─────────────────────────────────────────────────────────────

const STEPS: TourStep[] = [
  { kind: 'click', target: 'nav-nurse', side: 'bottom',
    action: '상단의 ‘간호사’ 탭을 눌러보세요',
    meaning: '방문 간호사가 현장에서 쓰는 화면으로 전환합니다.' },
  { kind: 'click', target: `nurse-card-${DEMO_PATIENT}`, side: 'bottom',
    action: '첫 방문 환자 ‘홍영희’ 님을 선택하세요',
    meaning: '질환과 지난 측정값이 표시된 방문 기록지가 열립니다.' },
  { kind: 'gate', target: 'nurse-bp', side: 'bottom', doneText: '입력 완료',
    action: '측정한 혈압을 입력하세요 (예: 138 / 88)',
    meaning: '입력하는 즉시 진료지침 목표(130/80 미만)와 비교해 경고가 표시됩니다.',
    ready: filledInputs,
    example: { label: '예시 값 넣기', fill: (el) => {
      const [s, d] = [...el.querySelectorAll('input')] as HTMLInputElement[];
      setNativeValue(s, '138'); setNativeValue(d, '88');
    } } },
  { kind: 'gate', target: 'nurse-sugar', side: 'bottom', doneText: '입력 완료',
    action: '공복 혈당을 입력하세요 (예: 138)',
    meaning: '목표(80–130)를 벗어나면 판정 근거에 함께 기록됩니다.',
    ready: filledInputs,
    example: { label: '예시 값 넣기', fill: (el) => {
      const g = el.querySelector('input') as HTMLInputElement | null;
      if (g) setNativeValue(g, '138');
    } } },
  { kind: 'click', target: 'nurse-med-well', side: 'bottom',
    action: '복약 확인에서 ‘잘 드시고 계심’을 눌러보세요',
    meaning: '복약 순응도도 판정 근거에 함께 들어갑니다.' },
  { kind: 'gate', target: 'nurse-observations', side: 'top', doneText: '선택 완료',
    action: '관찰된 소견을 골라주세요 (예: 어지러움 호소)',
    meaning: '부종·어지러움·호흡 가쁨은 합병증 의심 신호로 판정에 반영됩니다.',
    ready: (el) => !!el.querySelector('button[aria-pressed="true"]') },
  { kind: 'gate', target: 'nurse-notes', side: 'top', doneText: '입력 완료',
    action: '환자가 말한 증상을 특이사항에 적어주세요',
    meaning: '자유 서술 속 ‘시야 흐림’ 같은 증상도 안전 규칙이 찾아냅니다.',
    ready: (el) => ((el.querySelector('textarea') as HTMLTextAreaElement | null)?.value.trim().length ?? 0) >= 2,
    example: { label: '예시 문장 넣기', fill: (el) => {
      const t = el.querySelector('textarea') as HTMLTextAreaElement | null;
      if (t) setNativeValue(t, '2주 전부터 시야가 흐리고 눈앞에 날파리가 보인다고 함');
    } } },
  { kind: 'click', target: 'nurse-review', side: 'top',
    action: '‘기록 확인 후 AI 분석 요청’을 누르세요',
    meaning: '빠진 항목이 없는지 요약해서 한 번 더 확인합니다.' },
  { kind: 'click', target: 'nurse-submit', side: 'top',
    action: '‘전달하고 AI 분석 요청’을 누르세요',
    meaning: '입력한 값이 멀티에이전트 AI 분석으로 전달됩니다.' },
  { kind: 'click', target: 'nav-doctor', side: 'bottom',
    action: '상단의 ‘의사’ 탭으로 이동하세요',
    meaning: '분석 결과는 의사 화면에 자동으로 도착합니다.' },
  { kind: 'wait', target: `doctor-patient-${DEMO_PATIENT}`, side: 'right',
    action: 'AI 에이전트가 분석하고 있습니다',
    meaning: '' },
  { kind: 'click', target: `doctor-patient-${DEMO_PATIENT}`, side: 'right',
    action: '분석이 끝났습니다. ‘홍영희’ 님을 선택하세요',
    meaning: '입력한 값과 발동한 안전 규칙을 근거로 한 판정을 보여줍니다.' },
  { kind: 'click', target: 'doctor-tab-soap', side: 'top',
    action: '‘SOAP 노트’ 탭을 눌러보세요',
    meaning: '간호사 입력으로 진료 기록이 자동 작성되고, 진료지침 원문 근거가 붙습니다.' },
  { kind: 'click', target: 'nav-patient', side: 'bottom',
    action: '상단의 ‘환자’ 탭을 눌러보세요',
    meaning: '환자에게는 같은 결과가 쉬운 말로 전달됩니다.' },
];

const TOTAL = STEPS.length;
const FINAL_TARGET = 'patient-doctor-note';

// ── 데모 데이터 / URL ────────────────────────────────────────────────────

export function resetDemoData() {
  clearCache();
  Object.keys(localStorage)
    .filter(k => k.startsWith('silversync_patient_meds_'))
    .forEach(k => localStorage.removeItem(k));
}

export const isDemoUrl = () => new URLSearchParams(window.location.search).get('demo') === 'true';

function demoUrl(on: boolean) {
  const url = new URL(window.location.href);
  if (on) url.searchParams.set('demo', 'true'); else url.searchParams.delete('demo');
  return url.toString();
}

// ── 상태 (헤더 버튼 표시용) ───────────────────────────────────────────────

export type TourState = { mode: 'idle' | 'active' | 'paused'; step: number; total: number };

let tour: Driver | null = null;
let pausing = false;
let pausedIndex = 0;
let state: TourState = { mode: 'idle', step: 0, total: TOTAL };
let stepCleanup: (() => void) | null = null;
const listeners = new Set<() => void>();

function setState(next: Partial<TourState>) {
  state = { ...state, ...next };
  listeners.forEach(l => l());
}
export const subscribeTour = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
export const getTourState = () => state;

function runCleanup() { stepCleanup?.(); stepCleanup = null; }

// ── 말풍선 꾸미기 ─────────────────────────────────────────────────────────

function decoratePopover(wrapper: HTMLElement, label: string) {
  const title = wrapper.querySelector('.driver-popover-title');
  if (title && !title.querySelector('.ss-tour-progress')) {
    title.insertAdjacentHTML('afterbegin', `<span class="ss-tour-progress">${label}</span>`);
  }
  if (!wrapper.querySelector('.ss-tour-controls')) {
    const bar = document.createElement('div');
    bar.className = 'ss-tour-controls';
    bar.innerHTML =
      '<button type="button" data-act="restart">처음부터</button><span aria-hidden="true">·</span>' +
      '<button type="button" data-act="pause">일시정지</button><span aria-hidden="true">·</span>' +
      '<button type="button" data-act="end">시연 종료</button>';
    bar.addEventListener('click', (e) => {
      const act = (e.target as HTMLElement).closest('button')?.dataset.act;
      if (act === 'restart') restartDemoTour();
      if (act === 'pause') pauseDemoTour();
      if (act === 'end') endDemoTour();
    });
    wrapper.appendChild(bar);
  }
}

// ── 단계 만들기 ───────────────────────────────────────────────────────────

function toDriveStep(s: TourStep, i: number): DriveStep {
  const label = `${i + 1} / ${TOTAL}`;
  const base = { element: sel(s.target), waitForElement: 10000 };

  if (s.kind === 'click') {
    return {
      ...base,
      advanceOn: 'click',
      popover: { title: s.action, description: s.meaning, side: s.side, align: 'center', showButtons: [],
        onPopoverRender: (p) => decoratePopover(p.wrapper, label) },
    };
  }

  if (s.kind === 'gate') {
    return {
      ...base,
      popover: {
        title: s.action, description: s.meaning, side: s.side, align: 'center',
        showButtons: ['next'], nextBtnText: s.doneText,
        onPopoverRender: (p) => {
          decoratePopover(p.wrapper, label);
          p.nextButton.disabled = true;
          if (s.example && !p.footer.querySelector('.ss-tour-example')) {
            const ex = document.createElement('button');
            ex.type = 'button';
            ex.className = 'ss-tour-example';
            ex.textContent = s.example.label;
            ex.addEventListener('click', () => {
              const el = document.querySelector(sel(s.target));
              if (el) s.example!.fill(el);
            });
            p.footer.prepend(ex);
          }
        },
      },
      onHighlighted: (el) => {
        if (!el) return;
        const check = () => {
          const btn = tour?.getState('popover')?.nextButton as HTMLButtonElement | undefined;
          if (btn) btn.disabled = !s.ready(el);
        };
        const onClick = () => window.setTimeout(check, 0);
        el.addEventListener('input', check);
        el.addEventListener('click', onClick);
        check();
        runCleanup();
        stepCleanup = () => { el.removeEventListener('input', check); el.removeEventListener('click', onClick); };
      },
      onDeselected: runCleanup,
    };
  }

  // wait: 에이전트 진행 상황을 보여주다가 분석이 끝나면 자동으로 다음 단계
  return {
    ...base,
    disableActiveInteraction: true,
    popover: { title: s.action, description: '<ul class="ss-tour-agents"><li class="now">분석 준비 중</li></ul>', side: s.side, align: 'center', showButtons: [],
      onPopoverRender: (p) => decoratePopover(p.wrapper, label) },
    onHighlighted: (el) => {
      const trace = getDemoAnalysis(DEMO_PATIENT)?.agentTrace ?? [
        '데이터 정리 에이전트 · 입력값 정리', 'CDS 안전 규칙 · 규칙 검토', '임상 추론 에이전트 · 진료지침 검토', '최종 판정',
      ];
      const started = Date.now();
      // 이미 분석이 끝난 상태(이어하기 등)면 빠르게 훑고 넘어감
      const STAGE_MS = (el as HTMLElement | undefined)?.dataset.analysis === 'done' ? 400 : 1300;
      let finishedAt = 0;
      const render = () => {
        const desc = tour?.getState('popover')?.description as HTMLElement | undefined;
        const done = (el as HTMLElement | undefined)?.dataset.analysis === 'done';
        const shown = Math.min(trace.length, Math.floor((Date.now() - started) / STAGE_MS) + 1);
        const allDone = done && shown >= trace.length;
        if (desc) {
          desc.style.display = '';
          desc.innerHTML = '<ul class="ss-tour-agents">' + trace.map((t, k) => {
            if (k >= shown) return `<li class="todo">${t.split(' · ')[0]}</li>`;
            const current = k === shown - 1 && !allDone;
            return `<li class="${current ? 'now' : 'ok'}">${t}</li>`;
          }).join('') + '</ul>';
        }
        if (allDone && !finishedAt) finishedAt = Date.now();
        if (finishedAt && Date.now() - finishedAt > 900) { runCleanup(); tour?.moveNext(); }
      };
      const timer = window.setInterval(render, 250);
      render();
      runCleanup();
      stepCleanup = () => window.clearInterval(timer);
    },
    onDeselected: runCleanup,
  };
}

function buildSteps(): DriveStep[] {
  const finalStep: DriveStep = {
    element: sel(FINAL_TARGET),
    waitForElement: 10000,
    popover: {
      title: '시연이 끝났습니다',
      description: '간호사 입력 → 안전 규칙·AI 판정 → 의사 확인 → 환자 안내가 하나로 이어집니다. 환자 화면은 읽어주기·글자 크게로 고령 환자도 쉽게 쓸 수 있습니다.',
      side: 'bottom', align: 'center', showButtons: ['next'], doneBtnText: '시연 마치기',
      onPopoverRender: (p) => decoratePopover(p.wrapper, '완료'),
    },
  };
  return [...STEPS.map(toDriveStep), finalStep];
}

// ── 시작 · 일시정지 · 이어하기 · 종료 ─────────────────────────────────────

function launch(startIndex: number) {
  tour?.destroy();
  tour = driver({
    steps: buildSteps(),
    allowClose: false,
    overlayClickBehavior: 'none',
    allowKeyboardControl: false,
    animate: true,
    smoothScroll: true,
    overlayColor: '#0f172a',
    overlayOpacity: 0.6,
    stagePadding: 10,
    stageRadius: 24,
    popoverClass: 'ss-tour-popover',
    onHighlightStarted: (_el, _step, opts) => setState({ mode: 'active', step: (opts.index ?? 0) + 1 }),
    onDestroyed: () => {
      runCleanup();
      tour = null;
      window.history.replaceState(null, '', demoUrl(false));
      setState(pausing ? { mode: 'paused', step: pausedIndex + 1 } : { mode: 'idle', step: 0 });
      pausing = false;
    },
  });
  setState({ mode: 'active', step: startIndex + 1 });
  tour.drive(startIndex);
}

export function startDemoTour() { launch(0); }

/** 데모 데이터를 지우고 새로 불러와 1단계부터 (헤더 버튼 · 처음부터) */
export function restartDemoTour() {
  resetDemoData();
  window.location.href = demoUrl(true);
}

export function pauseDemoTour() {
  if (!tour) return;
  pausedIndex = tour.getActiveIndex() ?? 0;
  pausing = true;
  tour.destroy();
}

/**
 * 멈춘 단계부터 이어간다.
 * - 일시정지 중에 사용자가 그 단계를 직접 진행했으면(예: 간호사 기록을 직접 전달) 이미 끝난 단계로 되돌아가지 않는다.
 * - 그 사이 화면이 바뀌었으면 지금 화면에 있는 가장 가까운 이전 단계부터.
 */
export function resumeDemoTour() {
  const visible = (key: string) => {
    const el = document.querySelector(sel(key));
    return !!el && el.getClientRects().length > 0;
  };
  // 간호사 기록 전달은 되돌릴 수 없는 진행: 이미 전달했으면 간호사 단계(1~9)는 끝난 것으로 본다
  const submitted = getNurseQueue().some(e => e.patientId === DEMO_PATIENT);
  const floor = submitted ? STEPS.findIndex(s => s.target === 'nav-doctor') : 0;

  let i = Math.max(Math.min(pausedIndex, TOTAL), floor);
  if (i === TOTAL && !visible(FINAL_TARGET)) i = TOTAL - 1;
  while (i > floor && i < TOTAL && !visible(STEPS[i].target)) i--;
  launch(i);
}

export function endDemoTour() {
  if (tour) { tour.destroy(); return; }
  setState({ mode: 'idle', step: 0 });
}
