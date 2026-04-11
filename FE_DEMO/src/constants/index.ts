import type { StatusTheme } from '../types';

export const DAYS = ['월', '화', '수', '목', '금'];

export const OBSERVATION_CHIPS = [
  '안색 양호', '부종 관찰', '인지 저하 의심', '거동 불편',
  '식욕 부진', '수면 장애', '어지러움 호소', '호흡 가쁨', '피부 건조',
];

export const STATUS_THEME_MAP: Record<string, StatusTheme> = {
  orange: {
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
  },
  amber: {
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
  },
  teal: {
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
  },
};
