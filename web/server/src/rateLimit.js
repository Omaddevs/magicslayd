// Oddiy cheklov: bitta user daqiqasiga ko'pi bilan LIMIT ta o'zgartiruvchi so'rov (POST/PUT) yuboradi.
// Bot orqali xabar yuborish (topup, send) va fayl yuklashni spamdan himoya qiladi
const WINDOW_MS = 60_000;
const LIMIT = 40;
const hits = new Map(); // user_id → so'rov vaqtlari

export function rateLimit(req, res, next) {
  if (req.method === 'GET') return next();
  const now = Date.now();
  const recent = (hits.get(req.user.id) ?? []).filter((time) => now - time < WINDOW_MS);
  if (recent.length >= LIMIT) {
    return res.status(429).json({ error: "Juda ko'p so'rov. Bir daqiqadan so'ng urinib ko'ring." });
  }
  recent.push(now);
  hits.set(req.user.id, recent);
  next();
}

// Xotira to'lib ketmasligi uchun eski yozuvlar tozalanadi
setInterval(() => {
  const now = Date.now();
  for (const [user, times] of hits) if (times.every((time) => now - time >= WINDOW_MS)) hits.delete(user);
}, WINDOW_MS).unref();
