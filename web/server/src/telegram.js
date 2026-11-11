import { BOT_TOKEN } from './config.js';

export class TelegramError extends Error {
  constructor(code, description) {
    super(description);
    this.code = code;
  }
}

/** Bot API chaqiruvi (bot bilan bir xil token — fayllar va xabarlar shu bot nomidan ketadi). */
export async function tg(method, body) {
  const response = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  const data = await response.json();
  if (!data.ok) throw new TelegramError(data.error_code, data.description);
  return data.result;
}

/** Faylni yuklab yuboradi (diskdagi yangi versiya uchun). Yuborilgan hujjatning file_id sini qaytaradi. */
export async function tgSendFile(chatId, data, name, caption) {
  const form = new FormData();
  form.append('chat_id', String(chatId));
  form.append('caption', caption);
  form.append('parse_mode', 'HTML');
  form.append('document', new Blob([data]), name);
  const response = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendDocument`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(120_000),
  });
  const result = await response.json();
  if (!result.ok) throw new TelegramError(result.error_code, result.description);
  return result.result.document.file_id;
}

/** Telegram xatosini foydalanuvchiga tushunarli matnga aylantiradi. */
export function telegramReason(error) {
  if (error instanceof TelegramError && error.code === 403) {
    return "Bot sizga xabar yubora olmayapti. Botga kirib /start bosing.";
  }
  if (error instanceof TelegramError && error.code === 413) {
    return "Fayl 50 MB dan katta — Telegram orqali yuborib bo'lmaydi. «Yuklab olish» dan foydalaning.";
  }
  if (error instanceof TelegramError && /file|wrong/i.test(error.message)) {
    return "Bu faylni yuborib bo'lmadi. Iltimos, yangisini buyurtma qiling.";
  }
  return "Telegram bilan bog'lanishda xato. Birozdan so'ng urinib ko'ring.";
}

export const escapeHtml = (text) =>
  String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
