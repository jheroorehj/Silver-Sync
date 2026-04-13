import { useEffect, useCallback, useRef } from 'react';

export function useSessionTimeout(options: {
  warnAfterMs?: number;
  logoutAfterMs?: number;
  onWarn: () => void;
  onLogout: () => void;
}) {
  const {
    warnAfterMs = 10 * 60 * 1000,
    logoutAfterMs = 5 * 60 * 1000,
    onWarn,
    onLogout,
  } = options;

  const warnTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onWarnRef = useRef(onWarn);
  const onLogoutRef = useRef(onLogout);

  useEffect(() => { onWarnRef.current = onWarn; }, [onWarn]);
  useEffect(() => { onLogoutRef.current = onLogout; }, [onLogout]);

  const reset = useCallback(() => {
    if (warnTimerRef.current) clearTimeout(warnTimerRef.current);
    if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);

    warnTimerRef.current = setTimeout(() => {
      onWarnRef.current();
      logoutTimerRef.current = setTimeout(() => {
        onLogoutRef.current();
      }, logoutAfterMs);
    }, warnAfterMs);
  }, [warnAfterMs, logoutAfterMs]);

  useEffect(() => {
    const events = ['mousemove', 'keydown', 'click', 'touchstart'] as const;
    events.forEach(e => window.addEventListener(e, reset));
    reset();

    return () => {
      events.forEach(e => window.removeEventListener(e, reset));
      if (warnTimerRef.current) clearTimeout(warnTimerRef.current);
      if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    };
  }, [reset]);
}
