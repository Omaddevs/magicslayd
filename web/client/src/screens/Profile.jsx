import { useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import Flag from '../components/Flag.jsx';
import {
  BellIcon, ChatIcon, ChevronRight, HelpIcon, HistoryIcon, IdCardIcon, MoonIcon, PlusIcon, SunIcon,
} from '../components/Icons.jsx';
import { Avatar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { money } from '../lib/format.js';
import { LANGS, t, useLang } from '../lib/i18n.js';
import { confirmDialog, haptic, openLink } from '../lib/telegram.js';
import { setTheme, useTheme } from '../lib/theme.js';

const STAT_KINDS = [
  ['pres', 'Taqdimot'],
  ['referat', 'Referat'],
  ['kurs', 'Kurs ishi'],
  ['mustaqil', 'Mustaqil'],
];

/** Kunduzgi / tungi rejim almashtirgichi (quyosh ↔ oy). */
function ThemeSwitch() {
  const theme = useTheme();
  const dark = theme === 'dark';
  return (
    <button
      className={`theme-switch ${dark ? 'theme-switch--dark' : ''}`}
      role="switch"
      aria-checked={dark}
      aria-label={dark ? t('Tungi rejim yoqilgan') : t('Kunduzgi rejim yoqilgan')}
      onClick={() => {
        haptic('select');
        setTheme(dark ? 'light' : 'dark');
      }}
    >
      <span className="theme-switch__icon theme-switch__icon--sun"><SunIcon size={20} /></span>
      <span className="theme-switch__icon theme-switch__icon--moon"><MoonIcon size={18} /></span>
    </button>
  );
}

const ShieldIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.8 4.5 5.6v5.8c0 4.7 3.2 8.3 7.5 9.8 4.3-1.5 7.5-5.1 7.5-9.8V5.6z" />
    <path d="M9 12h6M12 9v6" />
  </svg>
);
const KeyIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="8" cy="15" r="4.5" />
    <path d="m11.2 11.8 8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2" />
  </svg>
);
const LogoutIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 4.5h3.5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H14" />
    <path d="M10 16.5 5.5 12 10 7.5M5.5 12H15" />
  </svg>
);
const ShieldCheck = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 2.8 4.5 5.6v5.8c0 4.7 3.2 8.3 7.5 9.8 4.3-1.5 7.5-5.1 7.5-9.8V5.6z" />
    <path d="m8.8 12 2.2 2.2 4.3-4.4" />
  </svg>
);
/** «文A» — til ikonkasi */
const TranslateIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3.5 5.5h9M8 3.5v2M10.5 5.5c-.7 3.6-3 6.4-6.5 8" />
    <path d="M5.8 8.6c1 2 2.6 3.6 4.7 4.6" />
    <path d="m12.5 20.5 4-9.5 4 9.5M14 17h5" />
  </svg>
);

/** Mehmon uchun: kirish / ro'yxatdan o'tish taklifi. */
function GuestCard() {
  const { openAuth, boot } = useApp();
  // Telegram'da yangi user — avval «Ro'yxatdan o'tish», avval ro'yxatdan o'tgan bo'lsa — «Kirish»
  const registerFirst = Boolean(boot.authHint) && !boot.authHint.registered;
  const [first, second] = registerFirst ? ['register', 'login'] : ['login', 'register'];
  const label = (view) => (view === 'register' ? t("Ro'yxatdan o'tish") : t('Kirish'));
  return (
    <section className="guest-card">
      <div className="guest-card__glow" aria-hidden="true" />
      <div className="guest-card__badge">🔐 {t('Mehmon rejimi')}</div>
      <h2>{t('Hisobingizga kiring')}</h2>
      <p>{t("Ish yaratish, saqlash va yoqtirish uchun ro'yxatdan o'ting. Loyihalar va balans istalgan qurilmada siz bilan.")}</p>
      <ul className="guest-card__perks">
        <li>📂 {t('Loyihalar saqlanadi')}</li>
        <li>💳 {t("Balans va to'lovlar")}</li>
        <li>📱 {t('Har qanday qurilmadan')}</li>
      </ul>
      <div className="guest-card__actions">
        <button className="btn guest-card__primary pressable" onClick={() => openAuth({ view: first })}>
          {label(first)}
        </button>
        <button className="btn guest-card__ghost pressable" onClick={() => openAuth({ view: second })}>
          {label(second)}
        </button>
      </div>
    </section>
  );
}

export default function Profile() {
  const { boot, push, openSheet, topup, refreshBalance, authed, openAuth, signOut } = useApp();
  const [stats, setStats] = useState(null);
  const lang = useLang();
  const currentLang = LANGS.find((l) => l.code === lang);

  useEffect(() => {
    if (!authed) return;
    refreshBalance().catch(() => {});
    api('/stats').then(setStats).catch(() => setStats({ byKind: {}, spent: 0 }));
  }, [refreshBalance, authed]);

  const logout = async () => {
    haptic('warning');
    if (await confirmDialog(t("Hisobdan chiqasizmi? Qayta kirish uchun raqam va parol kerak bo'ladi."))) signOut();
  };

  const support = boot.settings.support;
  const menu = [
    ...(authed
      ? [
          { label: t("Titul ma'lumotlari"), hint: t('Muqovaga yoziladi'), Icon: IdCardIcon, bg: 'var(--grad-blue)', onClick: () => push('title') },
          { label: t('Hamyon tarixi'), hint: t("To'lov va xarajatlar"), Icon: HistoryIcon, bg: 'var(--grad-green)', onClick: () => openSheet('wallet') },
        ]
      : []),
    { label: t('Yordam va narxlar'), hint: t('Qanday ishlaydi'), Icon: HelpIcon, bg: 'var(--grad-orange)', onClick: () => openSheet('help') },
  ];
  // Admin paneli: hamma userlarga bildirishnoma (ilova + Telegram bot)
  if (boot.isAdmin) {
    menu.unshift({
      label: t('Admin panel'),
      hint: t("Statistika, userlar, to'lovlar"),
      Icon: ShieldIcon,
      bg: 'linear-gradient(150deg, #4b5563 0%, #111827 100%)',
      onClick: () => push('admin'),
    });
    menu.splice(1, 0, {
      label: t('Xabar yuborish'),
      hint: t('Hamma userlarga: ilova va bot'),
      Icon: BellIcon,
      bg: 'linear-gradient(150deg, #ff6b8b 0%, #e8364f 100%)',
      onClick: () => push('broadcast'),
    });
  }
  if (support) {
    menu.push({
      label: t("Admin bilan bog'lanish"),
      hint: `@${support}`,
      Icon: ChatIcon,
      bg: 'var(--grad-purple)',
      onClick: () => openLink(`https://t.me/${support}`),
    });
  }

  return (
    <main className="page">
      <div className="profile-head">
        <ThemeSwitch />
        <Avatar user={boot.user} large />
        <h1>{boot.user.fullName}</h1>
        {authed ? (
          <div className="profile-phone">
            <span>{boot.account.phone}</span>
            {boot.account.verified && (
              <span className="profile-phone__ok" title={t('Telegram orqali tasdiqlangan')}>
                <ShieldCheck /> {t('Tasdiqlangan')}
              </span>
            )}
          </div>
        ) : (
          boot.user.username && <p>@{boot.user.username}</p>
        )}
      </div>

      {!authed && <GuestCard />}

      {authed && (
        <>
          <section className="wallet">
            <div className="wallet__label">{t('Balansingiz')}</div>
            <div className="wallet__amount">{money(boot.balance)}</div>
            <div className="wallet__row">
              <span className="wallet__label">{stats ? t('Jami sarflangan: {sum}', { sum: money(Math.max(stats.spent, 0)) }) : ' '}</span>
              <button className="btn btn--sm pressable" onClick={() => topup()}>
                <PlusIcon size={16} /> {t("To'ldirish")}
              </button>
            </div>
          </section>

          <div className="stats">
            {STAT_KINDS.map(([kind, label]) => (
              <div key={kind} className="stat">
                <b>{stats ? (stats.byKind[kind] ?? 0) : '–'}</b>
                <span>{t(label)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Til — har doim (mehmon ham) */}
      <div className="menu">
        <button className="menu__item pressable" onClick={() => { haptic('light'); openSheet('language'); }}>
          <div className="menu__icon" style={{ background: 'var(--grad-blue)' }}>
            <TranslateIcon size={21} />
          </div>
          <span>
            {t("Tilni o'zgartirish")}
            <br />
            <small>O'zbekcha · Русский · English</small>
          </span>
          <span className="menu__value">
            <Flag lang={lang} width={22} className="lang-flag lang-flag--sm" />
            <span>{currentLang?.code.toUpperCase()}</span>
          </span>
          <ChevronRight size={20} />
        </button>
      </div>

      <div className="menu">
        {menu.map(({ label, hint, Icon, bg, onClick }) => (
          <button key={label} className="menu__item pressable" onClick={onClick}>
            <div className="menu__icon" style={{ background: bg }}>
              <Icon size={20} />
            </div>
            <span>
              {label}
              <br />
              <small>{hint}</small>
            </span>
            <ChevronRight size={20} />
          </button>
        ))}
      </div>

      {authed && (
        <>
          <div className="menu">
            <button className="menu__item pressable" onClick={() => openAuth({ view: 'change' })}>
              <div className="menu__icon" style={{ background: 'var(--grad-purple)' }}>
                <KeyIcon size={20} />
              </div>
              <span>
                {t("Parolni o'zgartirish")}
                <br />
                <small>{t('Login')}: {boot.account.phone}</small>
              </span>
              <ChevronRight size={20} />
            </button>
          </div>
          <button className="logout-btn pressable" onClick={logout}>
            <LogoutIcon size={20} /> {t('Hisobdan chiqish')}
          </button>
        </>
      )}
    </main>
  );
}
