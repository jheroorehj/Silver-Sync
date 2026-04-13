# Silver-Sync

고령 고혈압·당뇨 환자 추적관찰 자동 스크리닝 시스템.
강원도 지역 65세 이상 만성질환 환자를 대상으로 AI 멀티에이전트가 생성한 트리아지 결과를 의료진에게 제공하고, 합병증 위험도를 시각화하는 의료 협업 플랫폼 데모입니다.

---

## 프로젝트 구조

| 폴더 | 설명 |
|------|------|
| `FE_DEMO/` | 의사·간호사·환자 역할별 뷰를 포함한 프론트엔드 데모 |
| `genticsimlaw-flowchart/` | 유전 심폐소생술 법 RAG 처리 흐름 Mermaid 다이어그램 시각화 |

---

## 빠른 시작

각 폴더로 이동 후 실행합니다.

```bash
# FE 데모
cd FE_DEMO
npm install
npm run dev   # → http://localhost:3000

# 플로우차트
cd genticsimlaw-flowchart
npm install
npm run dev   # → http://localhost:3000
```

자세한 내용은 각 폴더의 `README.md`를 참고하세요.

---

## FE_DEMO 주요 구현 현황

### 역할별 뷰

| 탭 | 주요 기능 |
|----|---------|
| 의사 | AI 분석 결과, SOAP 노트, CGM 인트라데이 혈당 차트, 에이전트 메타 패널 |
| 간호사 | 방문 일정 관리, 건강 스크리닝 체크리스트, AI 대화 요약 |
| 환자 | 개인 건강 데이터·자가 문진 뷰 |

### 임상 안전 및 보안

- AI 생성 콘텐츠 면책 배너 (`본 내용은 AI 에이전트가 생성한 참고 자료이며...`)
- 환자 식별번호 마스킹 (`720315-1******`)
- 세션 타임아웃 (10분 미사용 → 경고 → 화면 잠금)
- FHIR 어댑터 레이어 분리 (API 전환 시 `patientAdapter.ts`만 수정)

### 접근성 (WCAG AA)

- `role="tablist/tab"`, `aria-selected`, `aria-expanded`, `aria-controls`, `aria-label` 적용
- 아이콘 단독 사용 금지, 텍스트 라벨 병기
- 버튼 최소 44×44 px 클릭 영역

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | React 19, TypeScript ~5.8, Vite 6, Tailwind CSS 4 |
| 차트 | recharts 3 |
| 애니메이션 | motion/react 12 |
| 아이콘 | lucide-react |
| 백엔드 (예정) | FastAPI, KR Core FHIR |

---

## 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 안정 배포 브랜치 |
| `feature/main-rag-registry` | Main RAG 및 임상 금기 레지스터 개발 |
