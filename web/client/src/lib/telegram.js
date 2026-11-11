// Telegram Mini App SDK (index.html dagi telegram-web-app.js). Brauzerda ochilsa — undefined
export const tg = window.Telegram?.WebApp;

export const insideTelegram = Boolean(tg?.initData);

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  // Sarlavha va fon ranglarini lib/theme.js qo'yadi (kunduzgi / tungi rejim)
  // Ro'yxatni pastga tortganda ilova yopilib qolmasin
  tg.disableVerticalSwipes?.();
}

export function haptic(kind = 'light') {
  const feedback = tg?.HapticFeedback;
  if (!feedback) return;
  if (kind === 'success' || kind === 'error' || kind === 'warning') feedback.notificationOccurred(kind);
  else if (kind === 'select') feedback.selectionChanged();
  else feedback.impactOccurred(kind);
}

/** Bot chatini ochadi (fayl yoki to'lov xabari o'sha yerga keladi). */
export function openBotChat(username) {
  if (tg && username) tg.openTelegramLink(`https://t.me/${username}`);
  else if (tg) tg.close();
  else if (username) window.open(`https://t.me/${username}`, '_blank');
}

export function openLink(url) {
  if (tg && url.startsWith('https://t.me/')) tg.openTelegramLink(url);
  else if (tg) tg.openLink(url);
  else window.open(url, '_blank');
}

/** Faylni qurilmaga yuklab oladi. url — serverdagi imzolangan havola (/api/download/...). */
export function saveFile(url, fileName) {
  const absolute = new URL(url, window.location.origin).href;
  // Telegram 8.0+: o'zining yuklab olish oynasi (Mini App ichida oddiy havola ishlamaydi)
  if (tg?.downloadFile && tg.isVersionAtLeast?.('8.0')) {
    tg.downloadFile({ url: absolute, file_name: fileName });
    return;
  }
  if (tg) {
    tg.openLink(absolute); // eski Telegram — tashqi brauzerda ochiladi va yuklanadi
    return;
  }
  const link = document.createElement('a');
  link.href = absolute;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/** «Ha / Yo'q» savoli (Telegram ichida — Telegram oynasi). Promise<boolean>. */
export function confirmDialog(message) {
  if (tg?.showConfirm && tg.isVersionAtLeast?.('6.2')) {
    return new Promise((resolve) => tg.showConfirm(message, (ok) => resolve(Boolean(ok))));
  }
  return Promise.resolve(window.confirm(message));
}

/** Saqlanmagan o'zgarish bo'lsa — ilovani yopishda Telegram so'raydi. */
export function setClosingConfirmation(on) {
  if (!tg?.isVersionAtLeast?.('6.2')) return;
  if (on) tg.enableClosingConfirmation();
  else tg.disableClosingConfirmation();
}

/** Telegram «orqaga» tugmasi. */
export function setBackButton(handler) {
  const button = tg?.BackButton;
  if (!button) return () => {};
  if (!handler) {
    button.hide();
    return () => {};
  }
  button.onClick(handler);
  button.show();
  return () => button.offClick(handler);
}
