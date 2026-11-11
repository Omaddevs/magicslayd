// Bildirishnomalar: turlar, vaqt va sana guruhlari. Server: routes/notifications.js → NOTIFY_KINDS
import { getLang, t } from './i18n.js';

export const NOTIFY_KINDS = {
  yangilik: { label: 'Yangilik', icon: '📣', tone: 'purple' },
  aksiya: { label: 'Aksiya', icon: '🎁', tone: 'orange' },
  yangilanish: { label: 'Yangilanish', icon: '🚀', tone: 'blue' },
  muhim: { label: 'Muhim', icon: '⚠️', tone: 'red' },
};
export const kindOf = (kind) => NOTIFY_KINDS[kind] ?? NOTIFY_KINDS.yangilik;

/** «2026-11-05 14:05» (server vaqti) → Date */
export const parseTime = (value) => new Date(String(value || '').replace(' ', 'T'));

const dayStart = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();

/** Ro'yxatdagi qisqa vaqt: hozirgina · 5 daq oldin · 3 soat oldin · kecha · 2-noy */
export function timeAgo(value) {
  const date = parseTime(value);
  if (Number.isNaN(date.getTime())) return '';
  const s = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (s < 60) return t('hozirgina');
  if (s < 3600) return t('{n} daqiqa oldin', { n: Math.round(s / 60) });
  const days = Math.round((dayStart(new Date()) - dayStart(date)) / 86400000);
  if (days === 0) return t('{n} soat oldin', { n: Math.round(s / 3600) });
  if (days === 1) return t('kecha');
  return fullDate(value, false);
}

const MONTHS = {
  uz: ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'],
  ru: ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
};

/** To'liq sana: «5-noyabr, 14:05» / «5 ноября, 14:05» / «November 5, 14:05» (yil boshqa bo'lsa — yil bilan) */
export function fullDate(value, withTime = true) {
  const date = parseTime(value);
  if (Number.isNaN(date.getTime())) return value || '';
  const lang = getLang();
  const month = (MONTHS[lang] ?? MONTHS.uz)[date.getMonth()];
  const year = date.getFullYear() !== new Date().getFullYear() ? ` ${date.getFullYear()}` : '';
  const time = withTime ? `, ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}` : '';
  if (lang === 'en') return `${month} ${date.getDate()}${year}${time}`;
  if (lang === 'ru') return `${date.getDate()} ${month}${year}${time}`;
  return `${date.getDate()}-${month}${year}${time}`;
}

/** Ro'yxat guruhlari: Bugun · Kecha · Shu hafta · Avvalroq */
export function dayGroup(value) {
  const date = parseTime(value);
  const days = Math.round((dayStart(new Date()) - dayStart(date)) / 86400000);
  if (days <= 0) return 'Bugun';
  if (days === 1) return 'Kecha';
  if (days < 7) return 'Shu hafta';
  return 'Avvalroq';
}

/** Qo'ng'iroqcha belgisidagi raqam: 1…99, keyin «99+» */
export const badgeText = (n) => (n > 99 ? '99+' : String(n));
