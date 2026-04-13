import rawPatients from '../data/patients.json';
import type { DocPatient } from '../types';

/** 목업 데이터 → DocPatient 목록. 실제 FHIR API 전환 시 이 함수만 교체 */
export function getDocPatients(): DocPatient[] {
  return rawPatients as DocPatient[];
}

/** NurseChecklist에서 이름으로 환자를 검색. 향후 API 전환 시 여기서 변환 로직 추가 */
export function getNursePatientById(name: string): DocPatient | undefined {
  return (rawPatients as DocPatient[]).find(p => p.name === name);
}
