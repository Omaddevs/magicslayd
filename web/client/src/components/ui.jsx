import { useEffect } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { initials } from '../lib/format.js';
import { t } from '../lib/i18n.js';
import { insideTelegram } from '../lib/telegram.js';
import { ChevronLeft } from './Icons.jsx';

/** Ichki sahifa sarlavhasi. Telegram ichida «orqaga» tugmasi Telegram'ning o'zida bo'ladi. */
export function TopBar({ title, right }) {
  const { pop } = useApp();
  return (
    <header className="topbar">
      {!insideTelegram && (
        <button className="back-btn pressable" onClick={pop} aria-label={t('Orqaga')}>
          <ChevronLeft size={22} />
        </button>
      )}
      <h1>{title}</h1>
      {right}
    </header>
  );
}

export function Empty({ icon, title, text, children }) {
  return (
    <div className="empty">
      <div className="empty__icon">{icon}</div>
      <b>{title}</b>
      {text && <span>{text}</span>}
      {children}
    </div>
  );
}

export function Skeleton({ height = 80, count = 3 }) {
  return (
    <div className="list">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton" style={{ height }} />
      ))}
    </div>
  );
}

export function Sheet({ title, onClose, children }) {
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="sheet__handle" />
        {title && <h2 className="sheet__title">{title}</h2>}
        {children}
      </div>
    </>
  );
}

export function Toast() {
  const { toastState } = useApp();
  if (!toastState) return null;
  return (
    <div key={toastState.key} className={`toast ${toastState.type === 'error' ? 'toast--error' : ''}`} role="status">
      {toastState.text}
    </div>
  );
}

export function Avatar({ user, large }) {
  return (
    <div className={`avatar ${large ? 'avatar--lg' : ''}`}>
      {user.photoUrl ? <img src={user.photoUrl} alt="" /> : initials(user.fullName)}
    </div>
  );
}
