# Silver-Sync FE Demo

고령 고혈압·당뇨 환자 추적관찰 자동 스크리닝 시스템의 프론트엔드 데모입니다.
의사·간호사·환자 세 가지 역할 뷰를 포함하며, AI 멀티에이전트의 트리아지 결과를 정형화된 UI로 제공합니다.

---

## 기술 스택

| 항목 | 버전 |
|------|------|
| React | 19 |
| TypeScript | ~5.8 |
| Vite | 6 |
| Tailwind CSS | 4 |
| recharts | 3 |
| motion/react | 12 |
| lucide-react | 0.546 |

---

## 실행 방법

**필수 조건:** Node.js 18+

```bash
# 1. 의존성 설치
npm install

# 2. 개발 서버 실행
npm run dev
# → http://localhost:3000 (포트 사용 중이면 3001로 자동 변경)

# 3. 타입 검사
npm run lint   # tsc --noEmit

# 4. 프로덕션 빌드
npm run build
```

---

## 주요 기능

### 의사 탭 (Doctor Dashboard)

| 기능 | 설명 |
|------|------|
| AI 분석 뷰 | AI 멀티에이전트 트리아지 결과, 권고 이유, 상세 다변수 맥락 추론 |
| SOAP 노트 탭 | Subjective / Objective / Assessment / Plan 4개 섹션, 이상 수치 오렌지 강조, 인쇄·PDF 저장 |
| CGM 인트라데이 차트 | Objective 섹션에 24시간 혈당 AreaChart, 참고범위(70–140 mg/dL) 점선, 이탈 구간 오렌지 dot |
| 에이전트 메타 패널 | 신뢰도 점수, 의견 불일치(dissensionFlag) 경고, 토론 로그 접기/펼치기 |
| 환자 ID 마스킹 | 주민번호를 `720315-1******` 형태로 마스킹 표시 |
| AI 면책 배너 | AI 분석·SOAP 탭 상단에 임상 판단 책임 고지 배너 고정 |
| 접근성 | `role="tablist/tab"`, `aria-selected`, `aria-expanded`, `aria-controls`, `aria-label` |

### 간호사 탭 (Nurse Checklist)

| 기능 | 설명 |
|------|------|
| 방문 일정 관리 | 오늘 방문 환자 목록, 완료율 원형 프로그레스, 일정 동기화, 현장 환자 추가 |
| 건강 스크리닝 체크리스트 | 혈압·혈당 스피너 입력, 복약 상태, 관찰 소견 다중 선택, 특이사항 |
| AI 대화 요약 | 간호사-환자 대화 요약 텍스트, 채팅 버블 형태 원문 대화록 펼치기/접기 |
| AI 면책 배너 | AI 분석 결과 화면에 임상 판단 책임 고지 배너 |
| 접근성 | 뒤로 가기·완료 버튼 `aria-label`, 대화록 토글 `aria-expanded/aria-controls` |

### 환자 탭 (Patient App)

개인 건강 데이터 확인 및 자가 문진 뷰.

### 세션 타임아웃

- 마우스·키보드·터치 이벤트 감지로 타이머 리셋
- 기본 10분 미사용 시 카운트다운 경고 모달 표시
- 추가 5분 경과 시 화면 잠금 → 잠금 해제 버튼으로 복귀

---

## 디렉토리 구조

```
src/
├── adapters/
│   └── patientAdapter.ts      # FHIR 어댑터 레이어 (API 전환 시 이 파일만 수정)
├── components/
│   ├── DoctorDashboard.tsx
│   ├── NurseChecklist.tsx
│   ├── PatientApp.tsx
│   ├── SessionTimeoutModal.tsx
│   └── ui/
│       ├── NumberSpinner.tsx  # +/- 숫자 입력 컴포넌트
│       └── StatusBadge.tsx    # 상태 배지·아바타 컴포넌트
├── constants/
│   └── index.ts               # DAYS, OBSERVATION_CHIPS, STATUS_THEME_MAP
├── data/
│   └── patients.json          # 목업 환자 데이터 (4명)
├── hooks/
│   └── useSessionTimeout.ts   # 세션 타임아웃 훅
├── lib/
│   └── utils.ts               # cn(), maskPatientId()
├── types/
│   └── index.ts               # 공유 타입 정의
├── App.tsx
└── main.tsx
```

---

## 목업 환자 데이터

| 환자 | 상태 | 특이사항 |
|------|------|---------|
| 김덕배 (72세/남) | orange — 대면 진료 권고 | 고혈압·당뇨, 수축기 혈압 145mmHg |
| 이순자 (68세/여) | teal — 비대면 가능 | 고혈압, 모든 수치 정상 |
| 박상철 (75세/남) | amber — 집중 모니터링 | 당뇨, CGM 데이터 포함, 에이전트 의견 불일치 |
| 최영희 (81세/여) | teal — 최적 상태 | 고혈압·고지혈증, 고령 우수 관리 |

---

## 임상 안전 규칙 (FRONTEND_GUIDE_v1.md 기반)

- 모든 수치 표시에 단위 및 참고 범위 병기
- AI 생성 콘텐츠에 면책 배너 고정
- 환자 식별번호 마스킹 필수
- 색상 단독 정보 전달 금지 (아이콘+텍스트 병기)
- `tsc --noEmit` 오류 없이 유지
