// Adminlar va huquqlar — bot bilan bir xil qoida (bot/admins.py): bot egasi (.env → ADMIN_ID) barcha huquqlarga ega;
// u qo'shgan qo'shimcha adminlar («admins» jadvali) — faqat ega bergan huquqlar bilan (perms, NULL — DEFAULT_PERMS).
// Qo'shish / o'chirish / huquq berishni bot bajaradi (web_orders → «admins»): adminga Telegram xabari va menyusi boradi.
import { ADMIN_ID } from './config.js';
import { all, one } from './db.js';

export const OWNER_ID = ADMIN_ID;
export const PERMS = ['payments', 'users', 'balance', 'broadcast', 'stats', 'free'];
const DEFAULT_PERMS = ['payments'];

const tableReady = () => Boolean(one("SELECT 1 AS n FROM sqlite_master WHERE type = 'table' AND name = 'admins'"));
const hasPermsColumn = () => all('PRAGMA table_info(admins)').some((c) => c.name === 'perms');

function parsePerms(value) {
  if (value === null || value === undefined) return [...DEFAULT_PERMS];
  const set = new Set(String(value).split(','));
  return PERMS.filter((p) => set.has(p));
}

export const isOwner = (userId) => Boolean(OWNER_ID) && userId === OWNER_ID;

function adminRow(userId) {
  if (!userId || !tableReady()) return null;
  return one(`SELECT user_id${hasPermsColumn() ? ', perms' : ''} FROM admins WHERE user_id = ?`, userId) ?? null;
}

export const isAdmin = (userId) => isOwner(userId) || Boolean(adminRow(userId));

/** Huquqlar ro'yxati: ega — hammasi, admin bo'lmasa — bo'sh. */
export function permsOf(userId) {
  if (isOwner(userId)) return [...PERMS];
  const row = adminRow(userId);
  return row ? parsePerms(row.perms) : [];
}

export const hasPerm = (userId, perm) => permsOf(userId).includes(perm);

/** Express: bo'lim faqat shu huquqi bor adminga ochiq. */
export const requirePerm = (perm) => (req, res, next) => (hasPerm(req.user?.id, perm)
  ? next()
  : res.status(403).json({ error: "Bu bo'lim uchun sizga ruxsat berilmagan. Bot egasidan so'rang.", code: 'NO_PERMISSION' }));

/** Qo'shimcha adminlar (egasiz): [{ userId, name, username, addedAt, perms }]. */
export function extraAdmins() {
  if (!tableReady()) return [];
  return all(
    `SELECT a.user_id AS userId, COALESCE(u.full_name, a.name) AS name, u.username, a.added_at AS addedAt${hasPermsColumn() ? ', a.perms' : ''} ` +
      'FROM admins a LEFT JOIN users u ON u.id = a.user_id WHERE a.user_id != ? ORDER BY a.added_at, a.user_id',
    OWNER_ID ?? 0,
  ).map((a) => ({ ...a, perms: parsePerms(a.perms) }));
}

/** Xabarnomalar uchun: ega + (perm berilsa — faqat shu huquqi bor) qo'shimcha adminlar. */
export const adminIds = (perm) => [
  ...(OWNER_ID ? [OWNER_ID] : []),
  ...extraAdmins().filter((a) => !perm || a.perms.includes(perm)).map((a) => a.userId),
];
