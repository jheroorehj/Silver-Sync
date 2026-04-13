import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** 주민번호·환자 식별번호를 "xxxxxx-x******" 형태로 마스킹 */
export function maskPatientId(id: string): string {
  return id.replace(/^(\d{6}-\d)\d{6}$/, '$1******');
}
