import { getLang, t } from './i18n.js';

export const money = (amount) => `${Math.round(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} ${t("so'm")}`;

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '🙂';
}

const MONTHS = {
  uz: ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
  ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};

/** «2026-11-02 14:05» → «2-noy, 14:05» / «2 ноя, 14:05» / «2 Nov, 14:05» */
export function shortDate(value = '') {
  const [date, time] = value.split(' ');
  const [, month, day] = (date ?? '').split('-').map(Number);
  if (!month) return value;
  const lang = getLang();
  const name = (MONTHS[lang] ?? MONTHS.uz)[month - 1];
  return `${day}${lang === 'uz' ? '-' : ' '}${name}${time ? `, ${time}` : ''}`;
}

/** Bot tillari va dizayn nomlari emoji bilan keladi: «🇺🇿 O'zbekcha» → ["🇺🇿", "O'zbekcha"] */
export function splitEmoji(label = '') {
  const space = label.indexOf(' ');
  return space > 0 ? [label.slice(0, space), label.slice(space + 1)] : ['', label];
}
