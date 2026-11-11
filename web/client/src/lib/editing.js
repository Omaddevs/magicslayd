import { api } from './api.js';
import { t } from './i18n.js';

const POLL_MS = 1500;

/** Bot vazifasi (edit / import) tugashini kutadi. Xato bo'lsa — Error(sababi). */
export async function pollOrder(orderId) {
  for (;;) {
    const order = await api(`/orders/${orderId}`);
    if (order.status === 'done') return true;
    if (order.status === 'failed') throw new Error(t(order.error || "Bajarib bo'lmadi. Qayta urinib ko'ring."));
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

// Eski iOS (15.4 gacha) da structuredClone yo'q — kontent oddiy JSON bo'lgani uchun shu yetadi
export const clone = (value) => (window.structuredClone ? window.structuredClone(value) : JSON.parse(JSON.stringify(value)));
