// Ro'yxatdan o'tish / kirish / parolni tiklash.
// AuthFlow — umumiy forma; AuthSheet — ilova ichida pastdan chiqadigan oyna; AuthScreen — oddiy brauzer uchun to'liq sahifa
import { useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { api } from '../lib/api.js';
import { LANGS, setLang, t, useLang } from '../lib/i18n.js';
import { setSession } from '../lib/session.js';
import { haptic, openLink, tg } from '../lib/telegram.js';
import Flag from './Flag.jsx';

// ===== Ikonkalar (24×24, currentColor) =====
function Svg({ size = 20, children, strokeWidth = 2 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}
const PhoneIcon = (p) => (
  <Svg {...p}>
    <rect x="6.5" y="2.5" width="11" height="19" rx="2.8" />
    <path d="M10.5 18.5h3" />
  </Svg>
);
const LockIcon = (p) => (
  <Svg {...p}>
    <rect x="4.5" y="10.5" width="15" height="10.5" rx="3" />
    <path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7" />
    <path d="M12 14.8v2" />
  </Svg>
);
const EyeIcon = (p) => (
  <Svg {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);
const EyeOffIcon = (p) => (
  <Svg {...p}>
    <path d="M10.6 5.6A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16.5 16.5 0 0 1-2.4 3.2M6.4 6.9C3.9 8.6 2.5 12 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.6-1.3" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    <path d="m3 3 18 18" />
  </Svg>
);
const BackIcon = (p) => (
  <Svg {...p} strokeWidth={2.4}>
    <path d="M15 18l-6-6 6-6" />
  </Svg>
);
const CloseIcon = (p) => (
  <Svg {...p} strokeWidth={2.4}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
const CheckIcon = (p) => (
  <Svg {...p} strokeWidth={3}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
);
const ShieldIcon = (p) => (
  <Svg {...p}>
    <path d="M12 2.8 4.5 5.6v5.8c0 4.7 3.2 8.3 7.5 9.8 4.3-1.5 7.5-5.1 7.5-9.8V5.6z" />
    <path d="m8.8 12 2.2 2.2 4.3-4.4" />
  </Svg>
);
const KeyIcon = (p) => (
  <Svg {...p}>
    <circle cx="8" cy="15" r="4.5" />
    <path d="m11.2 11.8 8.3-8.3M16.5 6.5l2.5 2.5M14 9l2 2" />
  </Svg>
);
const UserPlusIcon = (p) => (
  <Svg {...p}>
    <circle cx="10" cy="8" r="4" />
    <path d="M2.8 20.5a7.2 7.2 0 0 1 12.4-5" />
    <path d="M18.5 14.5v6M15.5 17.5h6" />
  </Svg>
);
const TelegramIcon = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path fill="currentColor" d="M21.4 4.3 18.3 19c-.2 1-.9 1.3-1.7.8l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.8 8.8-7.9c.4-.3-.1-.5-.6-.2L6.2 13 1.5 11.5c-1-.3-1-1 .2-1.5L20.1 3c.9-.3 1.6.2 1.3 1.3z" />
  </svg>
);

// ===== Yordamchilar =====
const digitsOf = (text) => String(text ?? '').replace(/\D/g, '');

/** Kiritilgan raqamdan 9 ta mahalliy raqam: «+998 90 123 45 67» ham, «901234567» ham ishlaydi. */
function localDigits(text) {
  const d = digitsOf(text);
  return (d.length > 9 && d.startsWith('998') ? d.slice(3) : d).slice(0, 9);
}

/** 901234567 → «90 123 45 67» */
function formatLocal(d) {
  return [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(' ');
}

const hasLetter = (pw) => /\p{L}/u.test(pw);
const hasDigit = (pw) => /\d/.test(pw);

function passwordProblem(pw) {
  if (pw.length < 6) return t("Parol kamida 6 belgidan iborat bo'lsin.");
  if (pw.length > 64) return t('Parol 64 belgidan oshmasin.');
  if (!hasLetter(pw) || !hasDigit(pw)) return t("Parolda kamida bitta harf va bitta raqam bo'lsin.");
  return null;
}

function strengthOf(pw) {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 6) score += 1;
  if (pw.length >= 10) score += 1;
  if (hasLetter(pw) && hasDigit(pw)) score += 1;
  if (/[^\p{L}\d]/u.test(pw) || (/\p{Lu}/u.test(pw) && /\p{Ll}/u.test(pw))) score += 1;
  return Math.max(1, score);
}
const STRENGTH = ['', 'Juda oddiy', "O'rtacha", 'Yaxshi', 'Kuchli'];

function useCountdown() {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (left <= 0) return undefined;
    const timer = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(timer);
  }, [left]);
  return [left, setLeft];
}

const canShareContact = () => Boolean(tg?.requestContact && tg.isVersionAtLeast?.('6.9'));

// ===== Maydonlar =====
function FieldError({ text }) {
  if (!text) return null;
  return (
    <div className="auth-error" role="alert">
      {text}
    </div>
  );
}

function PhoneField({ value, onChange, error, autoFocus, action }) {
  const complete = value.length === 9;
  return (
    <div className="auth-field">
      <label className="auth-label" htmlFor="auth-phone">{t('Telefon raqam')}</label>
      <div className={`auth-input ${error ? 'auth-input--error' : ''}`}>
        <span className="auth-input__icon"><PhoneIcon /></span>
        <span className="auth-input__prefix">+998</span>
        <input
          id="auth-phone"
          type="tel"
          inputMode="numeric"
          autoComplete="tel-national"
          placeholder="90 123 45 67"
          value={formatLocal(value)}
          onChange={(e) => onChange(localDigits(e.target.value))}
          autoFocus={autoFocus}
        />
        {complete && !error && <span className="auth-input__ok"><CheckIcon size={14} /></span>}
      </div>
      <FieldError text={error} />
      {action}
    </div>
  );
}

function PasswordField({ id, label, value, onChange, error, autoComplete, autoFocus, rules, placeholder }) {
  const [visible, setVisible] = useState(false);
  const strength = strengthOf(value);
  return (
    <div className="auth-field">
      <label className="auth-label" htmlFor={id}>{label}</label>
      <div className={`auth-input ${error ? 'auth-input--error' : ''}`}>
        <span className="auth-input__icon"><LockIcon /></span>
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          placeholder={placeholder ?? '••••••'}
          value={value}
          maxLength={64}
          onChange={(e) => onChange(e.target.value)}
          autoFocus={autoFocus}
        />
        <button
          type="button"
          className="auth-input__eye"
          onClick={() => {
            haptic('select');
            setVisible((v) => !v);
          }}
          aria-label={visible ? t('Parolni yashirish') : t("Parolni ko'rsatish")}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
      <FieldError text={error} />
      {rules && (
        <div className="auth-rules">
          {value && (
            <div className={`strength strength--${strength}`}>
              <div className="strength__bars">
                {[1, 2, 3, 4].map((n) => <span key={n} className={n <= strength ? 'on' : ''} />)}
              </div>
              <span className="strength__label">{t(STRENGTH[strength])}</span>
            </div>
          )}
          <div className="auth-checks">
            <span className={value.length >= 6 ? 'ok' : ''}><CheckIcon size={12} /> {t('Kamida 6 belgi')}</span>
            <span className={hasLetter(value) && hasDigit(value) ? 'ok' : ''}><CheckIcon size={12} /> {t('Harf va raqam')}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** 6 xonali kod: bitta haqiqiy input (paste, SMS/klaviatura avtoto'ldirish ishlaydi) + 6 ta katakcha. */
function OtpInput({ value, onChange, error, disabled }) {
  const ref = useRef(null);
  useEffect(() => {
    const timer = setTimeout(() => ref.current?.focus(), 250);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className={`otp ${error ? 'otp--error' : ''}`} onClick={() => ref.current?.focus()}>
      <input
        ref={ref}
        className="otp__input"
        value={value}
        onChange={(e) => onChange(digitsOf(e.target.value).slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        aria-label={t('Tasdiqlash kodi')}
        disabled={disabled}
      />
      {Array.from({ length: 6 }, (_, i) => (
        <span
          key={i}
          className={`otp__box ${value[i] ? 'otp__box--filled' : ''} ${i === Math.min(value.length, 5) ? 'otp__box--current' : ''}`}
        >
          {value[i] ?? ''}
        </span>
      ))}
    </div>
  );
}

function Spinner() {
  return <span className="auth-spinner" aria-hidden="true" />;
}

const HEAD = {
  login: { Icon: LockIcon, title: 'Hisobga kirish', sub: 'Telefon raqamingiz va parolingizni kiriting' },
  register: { Icon: UserPlusIcon, title: 'Hisob yaratish', sub: 'Loyihalar, balans va saqlanganlar — har doim siz bilan' },
  forgot: {
    Icon: KeyIcon,
    title: 'Parolni tiklash',
    sub: "Ro'yxatdan o'tgan raqamingizni kiriting — Telegram orqali tasdiqlash kodi yuboramiz",
  },
  code: { Icon: ShieldIcon, title: 'Tasdiqlash kodi', sub: '' },
  newpass: { Icon: LockIcon, title: 'Yangi parol', sub: "Yangi parol o'ylab toping va uni eslab qoling" },
  change: { Icon: KeyIcon, title: "Parolni o'zgartirish", sub: 'Xavfsizlik uchun avval joriy parolingizni kiriting' },
};

const BACK = { forgot: 'login', code: 'forgot', newpass: 'forgot' };

/**
 * Umumiy forma.
 * - initialView: 'login' | 'register' | 'forgot' | 'change'
 * - canRegister: shu yerda ro'yxatdan o'tish mumkinmi (Telegram ichida). Yo'q bo'lsa — «bot orqali» kartasi
 * - onAuthed(token, text): muvaffaqiyatli kirilganda (Promise)
 */
export function AuthFlow({ initialView = 'login', reason, phoneHint = '', bot, canRegister, onAuthed }) {
  const [view, setView] = useState(initialView);
  const [phone, setPhone] = useState(phoneHint);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [current, setCurrent] = useState('');
  const [code, setCode] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [sent, setSent] = useState(null); // { masked, bot }
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [doneText, setDoneText] = useState('');
  const [resendIn, setResendIn] = useCountdown();
  const botName = sent?.bot || bot;

  const go = (next) => {
    haptic('select');
    setErrors({});
    setPassword('');
    setConfirm('');
    setCurrent('');
    setView(next);
  };

  const invalid = (next) => {
    haptic('error');
    setErrors(next);
    return null;
  };

  async function call(path, body) {
    setBusy(true);
    setErrors({});
    try {
      return await api(path, { method: 'POST', body });
    } catch (error) {
      haptic('error');
      setErrors({ [error.data?.field || 'form']: error.message, code: error.data?.code });
      if (error.data?.retryIn) setResendIn(error.data.retryIn);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function finish(result, text) {
    setDoneText(text);
    setView('done');
    haptic('success');
    try {
      await onAuthed(result.token, text);
    } catch (error) {
      setView('login');
      setErrors({ form: error.message || t("Kirib bo'lmadi. Qayta urinib ko'ring.") });
    }
  }

  // ===== Amallar =====
  async function login() {
    if (phone.length !== 9) return invalid({ phone: t("Telefon raqamni to'liq kiriting.") });
    if (!password) return invalid({ password: t('Parolni kiriting.') });
    const result = await call('/auth/login', { phone: `998${phone}`, password });
    if (result) await finish(result, t('Xush kelibsiz!'));
  }

  async function register() {
    const problem = passwordProblem(password);
    if (phone.length !== 9) return invalid({ phone: t("Telefon raqamni to'liq kiriting.") });
    if (problem) return invalid({ password: problem });
    if (password !== confirm) return invalid({ confirm: t('Parollar bir xil emas.') });
    const result = await call('/auth/register', { phone: `998${phone}`, password });
    if (result) await finish(result, t("Ro'yxatdan o'tdingiz!"));
  }

  async function requestCode(again = false) {
    if (phone.length !== 9) return invalid({ phone: t("Telefon raqamni to'liq kiriting.") });
    const result = await call('/auth/reset/request', { phone: `998${phone}` });
    if (!result) return null;
    setSent(result);
    setResendIn(result.retryIn);
    setCode('');
    if (again) {
      haptic('success');
      setErrors({ info: t('Yangi kod yuborildi') + ' ✉️' });
    } else go('code');
    return result;
  }

  async function verifyCode(value = code) {
    if (value.length !== 6) return invalid({ code: t('6 xonali kodni kiriting.') });
    const result = await call('/auth/reset/verify', { phone: `998${phone}`, code: value });
    if (!result) {
      setCode('');
      return null;
    }
    setResetToken(result.resetToken);
    go('newpass');
    return result;
  }

  async function saveNewPassword() {
    const problem = passwordProblem(password);
    if (problem) return invalid({ password: problem });
    if (password !== confirm) return invalid({ confirm: t('Parollar bir xil emas.') });
    const result = await call('/auth/reset/confirm', { resetToken, password });
    if (result) await finish(result, t('Parol yangilandi!'));
    return result;
  }

  async function changePassword() {
    if (!current) return invalid({ current: t('Joriy parolni kiriting.') });
    const problem = passwordProblem(password);
    if (problem) return invalid({ password: problem });
    if (password === current) return invalid({ password: t('Yangi parol joriy paroldan farq qilsin.') });
    if (password !== confirm) return invalid({ confirm: t('Parollar bir xil emas.') });
    const result = await call('/auth/password', { current, password });
    if (result) await finish(result, t("Parol o'zgartirildi!"));
    return result;
  }

  const submit = (e) => {
    e.preventDefault();
    if (busy) return;
    ({ login, register, forgot: () => requestCode(), code: () => verifyCode(), newpass: saveNewPassword, change: changePassword })[view]?.();
  };

  const onCode = (value) => {
    setCode(value);
    if (errors.code) setErrors({});
    if (value.length === 6 && !busy) verifyCode(value);
  };

  const shareContact = () => {
    haptic('light');
    tg.requestContact((shared, response) => {
      if (!shared) return;
      const number = response?.responseUnsafe?.contact?.phone_number;
      if (!number) return;
      const d = digitsOf(number);
      if (!d.startsWith('998') || d.length !== 12) {
        setErrors({ phone: t("Hozircha faqat O'zbekiston (+998) raqamlari qabul qilinadi.") });
        return;
      }
      setPhone(d.slice(3));
      setErrors({});
      haptic('success');
    });
  };

  const openBotRegister = () => {
    if (botName) openLink(`https://t.me/${botName}?start=royxat`);
  };

  // ===== Muvaffaqiyat =====
  if (view === 'done') {
    return (
      <div className="auth auth--done">
        <div className="auth-success">
          <span className="auth-success__ring" />
          <span className="auth-success__icon"><CheckIcon size={42} /></span>
        </div>
        <h2 className="auth-title">{doneText}</h2>
        <p className="auth-sub">{t('Hisobingiz tayyor. Davom ettirilmoqda…')}</p>
      </div>
    );
  }

  const head = HEAD[view];
  const tabs = view === 'login' || view === 'register';
  const switchTo = (next) => (
    <button type="button" className="auth-link auth-link--inline" onClick={() => go(next)}>
      {next === 'login' ? t("Kirishga o'tish") : t("Ro'yxatdan o'tish")} →
    </button>
  );
  const phoneAction =
    errors.code === 'NO_ACCOUNT' && view === 'login' ? switchTo('register')
      : (errors.code === 'ALREADY_REGISTERED' || errors.code === 'PHONE_TAKEN') ? switchTo('login') : null;

  const codeSub = sent ? (
    <>
      {t("6 xonali kod {phone} raqamiga bog'langan Telegram chatga yuborildi", { phone: sent.masked })}
      {botName ? <> · <b>@{botName}</b></> : null}
    </>
  ) : '';

  return (
    <form className="auth" onSubmit={submit} noValidate>
      {BACK[view] && (
        <button type="button" className="auth-back pressable" onClick={() => go(BACK[view])} aria-label={t('Orqaga')}>
          <BackIcon />
        </button>
      )}

      <div className="auth-hero" key={view}>
        <div className="auth-hero__icon">
          <head.Icon size={30} />
        </div>
        <h2 className="auth-title">{t(head.title)}</h2>
        <p className="auth-sub">{view === 'code' ? codeSub : t(head.sub)}</p>
      </div>

      {reason && tabs && (
        <div className="auth-reason">
          <LockIcon size={16} />
          <span>{reason}</span>
        </div>
      )}

      {tabs && (
        <div className="segment auth-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={view === 'login'} className={view === 'login' ? 'segment--active' : ''}
            onClick={() => view !== 'login' && go('login')}>
            {t('Kirish')}
          </button>
          <button type="button" role="tab" aria-selected={view === 'register'} className={view === 'register' ? 'segment--active' : ''}
            onClick={() => view !== 'register' && go('register')}>
            {t("Ro'yxatdan o'tish")}
          </button>
        </div>
      )}

      <div className="auth-body" key={`body-${view}`}>
        {errors.form && <div className="note note--error auth-note">{errors.form}</div>}
        {errors.info && <div className="note note--info auth-note">{errors.info}</div>}

        {/* ===== Kirish ===== */}
        {view === 'login' && (
          <>
            <PhoneField value={phone} onChange={setPhone} error={errors.phone} autoFocus={!phone} action={phoneAction} />
            <PasswordField id="auth-password" label={t('Parol')} value={password} onChange={setPassword} error={errors.password}
              autoComplete="current-password" autoFocus={Boolean(phone)} />
            <div className="auth-row">
              <button type="button" className="auth-link" onClick={() => go('forgot')}>{t('Parolni unutdingizmi?')}</button>
            </div>
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy}>
              {busy ? <Spinner /> : t('Kirish')}
            </button>
          </>
        )}

        {/* ===== Ro'yxatdan o'tish ===== */}
        {view === 'register' && canRegister && (
          <>
            {canShareContact() && (
              <button type="button" className="auth-contact pressable" onClick={shareContact}>
                <span className="auth-contact__icon"><TelegramIcon size={18} /></span>
                <span>
                  <b>{t('Telegram raqamimni olish')}</b>
                  <small>{t("Bir bosishda to'ldiriladi va tasdiqlanadi")}</small>
                </span>
              </button>
            )}
            <PhoneField value={phone} onChange={setPhone} error={errors.phone} action={phoneAction} />
            <PasswordField id="auth-new" label={t("Parol o'ylab toping")} value={password} onChange={setPassword} error={errors.password}
              autoComplete="new-password" rules />
            <PasswordField id="auth-confirm" label={t('Parolni takrorlang')} value={confirm} onChange={setConfirm}
              error={errors.confirm || (confirm && password !== confirm && confirm.length >= password.length ? t('Parollar bir xil emas.') : '')}
              autoComplete="new-password" />
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy}>
              {busy ? <Spinner /> : t("Ro'yxatdan o'tish")}
            </button>
            {botName && (
              <>
                <div className="auth-divider"><span>{t('yoki')}</span></div>
                <button type="button" className="btn btn--white auth-alt" onClick={openBotRegister}>
                  <TelegramIcon size={18} /> {t("Bot orqali ro'yxatdan o'tish")}
                </button>
              </>
            )}
          </>
        )}

        {view === 'register' && !canRegister && (
          <div className="auth-bot">
            <div className="auth-bot__icon"><TelegramIcon size={28} /></div>
            <b>{t("Ro'yxatdan o'tish — Telegram orqali")}</b>
            <p>
              {t("Botga kiring, «📱 Raqamni yuborish» tugmasini bosing va parol o'ylab toping. So'ng shu yerda raqam va parol bilan kirasiz.")}
            </p>
            <ol className="auth-steps">
              <li><span>1</span> {t('Botni oching')}</li>
              <li><span>2</span> {t('Raqamingizni ulashing')}</li>
              <li><span>3</span> {t("Parol o'ylab toping")}</li>
            </ol>
            {botName && (
              <button type="button" className="btn btn--primary auth-submit" onClick={openBotRegister}>
                <TelegramIcon size={18} /> {t("Botda ro'yxatdan o'tish")}
              </button>
            )}
          </div>
        )}

        {/* ===== Parolni tiklash: raqam ===== */}
        {view === 'forgot' && (
          <>
            <PhoneField value={phone} onChange={setPhone} error={errors.phone} autoFocus action={
              errors.code === 'NO_ACCOUNT' ? switchTo('register') : null
            } />
            <div className="auth-tip">
              <TelegramIcon size={16} />
              <span>{t("Kod SMS emas — hisobingiz bog'langan Telegram chatga bot orqali keladi.")}</span>
            </div>
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy}>
              {busy ? <Spinner /> : t('Kod yuborish')}
            </button>
          </>
        )}

        {/* ===== Parolni tiklash: kod ===== */}
        {view === 'code' && (
          <>
            <OtpInput value={code} onChange={onCode} error={errors.code} disabled={busy} />
            <FieldError text={errors.code} />
            {botName && (
              <button type="button" className="auth-open-bot pressable" onClick={() => openLink(`https://t.me/${botName}`)}>
                <TelegramIcon size={16} /> {t("Kodni ko'rish uchun botni ochish")}
              </button>
            )}
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy || code.length !== 6}>
              {busy ? <Spinner /> : t('Tasdiqlash')}
            </button>
            <div className="auth-resend">
              {resendIn > 0 ? (
                <span>{t('Yangi kod')}: <b>0:{String(resendIn).padStart(2, '0')}</b></span>
              ) : (
                <button type="button" className="auth-link" onClick={() => requestCode(true)} disabled={busy}>
                  {t('Kodni qayta yuborish')}
                </button>
              )}
            </div>
          </>
        )}

        {/* ===== Parolni tiklash: yangi parol ===== */}
        {view === 'newpass' && (
          <>
            <PasswordField id="auth-new" label={t('Yangi parol')} value={password} onChange={setPassword} error={errors.password}
              autoComplete="new-password" autoFocus rules />
            <PasswordField id="auth-confirm" label={t('Yangi parolni takrorlang')} value={confirm} onChange={setConfirm}
              error={errors.confirm} autoComplete="new-password" />
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy}>
              {busy ? <Spinner /> : t('Saqlash va kirish')}
            </button>
          </>
        )}

        {/* ===== Parolni o'zgartirish (profil) ===== */}
        {view === 'change' && (
          <>
            <PasswordField id="auth-current" label={t('Joriy parol')} value={current} onChange={setCurrent} error={errors.current}
              autoComplete="current-password" autoFocus />
            <PasswordField id="auth-new" label={t('Yangi parol')} value={password} onChange={setPassword} error={errors.password}
              autoComplete="new-password" rules />
            <PasswordField id="auth-confirm" label={t('Yangi parolni takrorlang')} value={confirm} onChange={setConfirm}
              error={errors.confirm} autoComplete="new-password" />
            <div className="auth-row">
              <button type="button" className="auth-link" onClick={() => go('forgot')}>{t('Joriy parolni unutdingizmi?')}</button>
            </div>
            <button type="submit" className="btn btn--primary auth-submit" disabled={busy}>
              {busy ? <Spinner /> : t('Parolni yangilash')}
            </button>
          </>
        )}
      </div>

      <p className="auth-secure">
        <ShieldIcon size={14} /> {t('Parolingiz shifrlangan holda saqlanadi')}
      </p>
    </form>
  );
}

// ===== Ilova ichida: pastdan chiqadigan oyna =====
export function AuthSheet({ close, reason, then, view }) {
  const { boot, signIn, toast } = useApp();
  const hint = boot.authHint;
  const canRegister = Boolean(hint); // server Telegram user'ini taniydi
  const initialView = view || (canRegister && !hint.registered ? 'register' : 'login');
  const phoneHint = boot.account?.digits || hint?.digits || '';

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  const onAuthed = async (token, text) => {
    const started = Date.now();
    await signIn(token);
    // Muvaffaqiyat animatsiyasi ko'rinib ulgursin
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, 1100 - (Date.now() - started))));
    close();
    toast(`${text} ✅`);
    then?.();
  };

  return (
    <>
      <div className="sheet-backdrop sheet-backdrop--auth" onClick={close} />
      <div className="sheet sheet--auth" role="dialog" aria-modal="true" aria-label={t('Hisobga kirish')}>
        <div className="sheet__handle" />
        <button type="button" className="auth-close pressable" onClick={close} aria-label={t('Yopish')}>
          <CloseIcon size={18} />
        </button>
        <AuthFlow
          initialView={initialView}
          reason={reason}
          phoneHint={phoneHint}
          bot={boot.settings.bot_username}
          canRegister={canRegister}
          onAuthed={onAuthed}
        />
      </div>
    </>
  );
}

// ===== Oddiy brauzer (Telegram'siz): to'liq sahifa =====
export function AuthScreen({ onSignedIn }) {
  const [bot, setBot] = useState('');
  const lang = useLang();
  useEffect(() => {
    fetch('/api/auth/config')
      .then((response) => response.json())
      .then((data) => setBot(data.bot || ''))
      .catch(() => {});
  }, []);

  return (
    <div className="auth-page">
      <div className="auth-page__bg" aria-hidden="true">
        <span className="auth-page__blob auth-page__blob--a" />
        <span className="auth-page__blob auth-page__blob--b" />
      </div>
      <div className="auth-page__langs" role="radiogroup" aria-label={t('Tilni tanlang')}>
        {LANGS.map(({ code }) => (
          <button
            key={code}
            role="radio"
            aria-checked={lang === code}
            className={`auth-page__lang ${lang === code ? 'auth-page__lang--on' : ''}`}
            onClick={() => setLang(code)}
          >
            <Flag lang={code} width={20} className="lang-flag lang-flag--sm" />
            {code.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="auth-page__brand">
        <img src="/logo.png" alt="" width="56" height="56" />
        <span>Magic<b>Slayd</b></span>
      </div>
      <div className="auth-page__card">
        <AuthFlow
          initialView="login"
          bot={bot}
          canRegister={false}
          onAuthed={async (token) => {
            setSession(token);
            await new Promise((resolve) => setTimeout(resolve, 900));
            await onSignedIn();
          }}
        />
      </div>
      <p className="auth-page__foot">{t("Taqdimot, referat, kurs va diplom ishlari — sun'iy intellekt yordamida bir necha daqiqada")}</p>
    </div>
  );
}
