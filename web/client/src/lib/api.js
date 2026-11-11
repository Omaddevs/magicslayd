import { t } from './i18n.js';
import { getSession } from './session.js';
import { tg } from './telegram.js';

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

/** Telegram initData + (kirgan bo'lsa) sessiya tokeni. */
function authHeaders() {
  const headers = { Authorization: `tma ${tg?.initData ?? ''}` };
  const session = getSession();
  if (session) headers['X-Session'] = session;
  return headers;
}

/** Hisob talab qilinadigan amal mehmon tomonidan bosildi — ilova kirish oynasini ochadi (AppContext tinglaydi). */
function check(response, data, fallback) {
  if (response.ok) return data;
  if (response.status === 401 && data.code === 'AUTH_REQUIRED') {
    window.dispatchEvent(new CustomEvent('slayd:auth-required'));
  }
  // Server xabarlari o'zbekcha — lug'atda bo'lsa tanlangan tilga o'giriladi
  throw new ApiError(t(data.error || fallback), response.status, data);
}

/** Himoyalangan faylni (masalan, admin uchun chek) blob URL sifatida oladi — <img> sarlavha yubora olmaydi. */
export async function apiBlob(path) {
  let response;
  try {
    response = await fetch(`/api${path}`, { headers: authHeaders() });
  } catch {
    throw new ApiError(t('Internet aloqasini tekshiring.'), 0, {});
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(t(data.error || "Faylni yuklab bo'lmadi."), response.status, data);
  }
  const blob = await response.blob();
  return { url: URL.createObjectURL(blob), type: blob.type };
}

/** Faylni (rasm, video) xom holda yuklaydi. */
export async function apiUpload(path, blob, headers = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': blob.type || 'application/octet-stream',
        ...authHeaders(),
        ...headers,
      },
      body: blob,
    });
  } catch {
    throw new ApiError(t('Internet aloqasini tekshiring.'), 0, {});
  }
  const data = await response.json().catch(() => ({}));
  return check(response, data, 'Faylni yuklab bo\'lmadi.');
}

/** Server API'si. Har bir so'rov Telegram initData (va sessiya) bilan imzolanadi — server uni tekshiradi. */
export async function api(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(t('Internet aloqasini tekshiring.'), 0, {});
  }
  const data = await response.json().catch(() => ({}));
  return check(response, data, 'Xato yuz berdi.');
}
