import React, { useState, useEffect } from 'react';
import { AlertTriangle, Lock } from 'lucide-react';

type Props = {
  isLocked: boolean;
  onContinue: () => void;
  onUnlock: () => void;
  logoutAfterMs?: number;
};

export function SessionTimeoutModal({
  isLocked,
  onContinue,
  onUnlock,
  logoutAfterMs = 5 * 60 * 1000,
}: Props) {
  const [secondsLeft, setSecondsLeft] = useState(Math.ceil(logoutAfterMs / 1000));

  useEffect(() => {
    if (isLocked) return;
    setSecondsLeft(Math.ceil(logoutAfterMs / 1000));
    const interval = setInterval(() => {
      setSecondsLeft(s => Math.max(0, s - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [isLocked, logoutAfterMs]);

  const minutes = Math.floor(secondsLeft / 60);
  const secs = secondsLeft % 60;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="timeout-title"
      className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
    >
      <div className="bg-white/70 backdrop-blur-2xl rounded-[32px] border border-white shadow-2xl p-8 max-w-sm w-full text-center">
        {isLocked ? (
          <>
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Lock className="w-8 h-8 text-slate-500" strokeWidth={1.5} />
            </div>
            <h2 id="timeout-title" className="text-2xl font-extrabold text-slate-900 mb-2">
              화면이 잠겼습니다
            </h2>
            <p className="text-slate-500 mb-6 text-sm leading-relaxed">
              보안을 위해 화면이 잠겼습니다.<br />
              다시 시작하려면 아래 버튼을 누르세요.
            </p>
            <button
              onClick={onUnlock}
              className="w-full h-14 bg-sky-500 hover:bg-sky-600 text-white rounded-2xl font-extrabold text-lg transition-colors shadow-md shadow-sky-200/50"
            >
              잠금 해제
            </button>
          </>
        ) : (
          <>
            <div className="w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-8 h-8 text-amber-500" strokeWidth={1.5} />
            </div>
            <h2 id="timeout-title" className="text-2xl font-extrabold text-slate-900 mb-2">
              자동 로그아웃 예정
            </h2>
            <p className="text-slate-500 mb-1 text-sm leading-relaxed">
              비활성 상태가 감지되었습니다.
            </p>
            <p className="text-sm mb-6">
              <span className="font-bold text-amber-600">{minutes}분 {String(secs).padStart(2, '0')}초</span>
              <span className="text-slate-500"> 후 화면이 자동으로 잠깁니다.</span>
            </p>
            <button
              onClick={onContinue}
              className="w-full h-14 bg-sky-500 hover:bg-sky-600 text-white rounded-2xl font-extrabold text-lg transition-colors shadow-md shadow-sky-200/50"
            >
              계속 사용하기
            </button>
          </>
        )}
      </div>
    </div>
  );
}
