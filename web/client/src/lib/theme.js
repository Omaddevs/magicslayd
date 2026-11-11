// Kunduzgi / tungi rejim. Tanlov qurilmada (localStorage) va Telegram bulutida saqlanadi —
// telefonda tanlangan rejim kompyuterdagi Telegram'da ham ochiladi.
import { useSyncExternalStore } from 'react';

import { tg } from './telegram.js';

const KEY = 'slayd-theme';
const COLORS = {
  light: { bg: '#F6F5FB', bar: '#FFFFFF' },
  dark: { bg: '#0F0E1A', bar: '#1B1929' },
};
const listeners = new Set();
let current = 'light';

function readLocal() {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'dark' || value === 'light' ? value : null;
  } catch {
    return null;
  }
}

function apply(theme, animate) {
  current = theme;
  const root = document.documentElement;
  if (animate) {
    root.classList.add('theme-switching');
    setTimeout(() => root.classList.remove('theme-switching'), 400);
  }
  root.dataset.theme = theme;
  const { bg, bar } = COLORS[theme];
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', bg);
  // Telegram sarlavhasi va pastki qismi ham ilova rangida bo'lsin
  tg?.setHeaderColor?.(bg);
  tg?.setBackgroundColor?.(bg);
  tg?.setBottomBarColor?.(bar);
  listeners.forEach((listener) => listener());
}

/** Ilova ochilishida: saqlangan tanlov, bo'lmasa — Telegram'ning o'z rejimi. */
export function initTheme() {
  apply(readLocal() ?? (tg?.colorScheme === 'dark' ? 'dark' : 'light'), false);
  // Boshqa qurilmada tanlangan bo'lsa — bulutdagisi ustun
  if (tg?.CloudStorage && tg.isVersionAtLeast?.('6.9')) {
    tg.CloudStorage.getItem(KEY, (error, value) => {
      if (!error && (value === 'dark' || value === 'light') && value !== current) {
        apply(value, true);
        try { localStorage.setItem(KEY, value); } catch { /* saqlab bo'lmasa ham ishlayveradi */ }
      }
    });
  }
}

export function setTheme(theme) {
  if (theme === current) return;
  apply(theme, true);
  try { localStorage.setItem(KEY, theme); } catch { /* saqlab bo'lmasa ham ishlayveradi */ }
  if (tg?.CloudStorage && tg.isVersionAtLeast?.('6.9')) tg.CloudStorage.setItem(KEY, theme, () => {});
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  return useSyncExternalStore(subscribe, () => current);
}
