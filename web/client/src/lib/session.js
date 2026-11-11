// Kirish sessiyasi tokeni. Brauzer xotirasida + Telegram CloudStorage'da (bir qurilmada kirsangiz,
// Telegram'ning boshqa qurilmalarida ham kirgan bo'lasiz; Telegram webview xotirani tozalab yuborsa ham yo'qolmaydi)
import { tg } from './telegram.js';

const KEY = 'slayd_session';
let memory = '';

const cloud = () => (tg?.CloudStorage && tg.isVersionAtLeast?.('6.9') ? tg.CloudStorage : null);

export function getSession() {
  if (memory) return memory;
  try {
    memory = localStorage.getItem(KEY) || '';
  } catch {
    /* xotira yopiq — faqat shu ochilishda */
  }
  return memory;
}

export function setSession(token) {
  memory = token || '';
  try {
    if (memory) localStorage.setItem(KEY, memory);
    else localStorage.removeItem(KEY);
  } catch {
    /* e'tiborsiz */
  }
  try {
    const storage = cloud();
    if (storage) memory ? storage.setItem(KEY, memory) : storage.removeItem(KEY);
  } catch {
    /* e'tiborsiz */
  }
}

/** Ilova ochilganda: brauzer xotirasida token yo'q bo'lsa — Telegram CloudStorage'dan tiklaydi. */
export function restoreSession() {
  if (getSession()) return Promise.resolve();
  const storage = cloud();
  if (!storage) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, 1200); // eski klientlarda javob kelmasligi mumkin
    try {
      storage.getItem(KEY, (error, value) => {
        clearTimeout(timer);
        if (!error && value) {
          memory = value;
          try {
            localStorage.setItem(KEY, value);
          } catch {
            /* e'tiborsiz */
          }
        }
        resolve();
      });
    } catch {
      clearTimeout(timer);
      resolve();
    }
  });
}
