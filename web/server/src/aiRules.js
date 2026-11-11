// AI yordamchi: kiruvchi ma'lumotni tozalash, tekshirish va limitlar — sof funksiyalar (testlanadi).
// Qoidalar botdagi assistant/service.py bilan bir xil; chegaralar bot yuborgan sozlamadan (web_config.ai) olinadi.

export const LIMIT_TEXT = "Bugungi bepul limitingiz tugadi. Ertaga qayta urinib ko'ring.";
export const RATE_TEXT = "Juda tez so'rov yuboryapsiz. Bir daqiqadan so'ng qayta urinib ko'ring.";

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

/** HTML teglari, boshqaruv belgilari va <> olib tashlanadi, bo'shliqlar bittaga (prompt va sahifa uchun xavfsiz). */
export function cleanText(value) {
  return String(value ?? '')
    .replace(/&(#\d+|#x[\da-f]+|[a-z]+);/gi, (entity, code) => {
      if (code[0] === '#') {
        const n = code[1].toLowerCase() === 'x' ? parseInt(code.slice(2), 16) : Number(code.slice(1));
        return Number.isFinite(n) && n > 0 && n < 0x110000 ? String.fromCodePoint(n) : ' ';
      }
      return ENTITIES[code.toLowerCase()] ?? entity;
    })
    .replace(/<[^>]*>/g, ' ')
    .replace(/\p{C}/gu, ' ')
    .replace(/[<>]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** {type, topic, subject, size, language} → { params } yoki { error, field }. */
export function validateAiRequest(body, rules) {
  const data = body ?? {};
  const type = rules.types[data.type] ? data.type : null;
  if (!type) return { error: 'Ish turini tanlang.', field: 'type' };
  const topic = cleanText(data.topic);
  if (topic.length < rules.topic_min) {
    return { error: `Mavzu kamida ${rules.topic_min} ta belgidan iborat bo'lsin.`, field: 'topic' };
  }
  if (topic.length > rules.topic_max) return { error: `Mavzu ${rules.topic_max} belgidan oshmasin.`, field: 'topic' };
  const subject = cleanText(data.subject);
  if (subject.length > rules.subject_max) {
    return { error: `Fan nomi ${rules.subject_max} belgidan oshmasin.`, field: 'subject' };
  }
  const limits = rules.types[type];
  const size = data.size === undefined || data.size === '' ? limits.default : Number(data.size);
  if (!Number.isInteger(size) || size < limits.min || size > limits.max) {
    return { error: `${limits.label} hajmi ${limits.min}–${limits.max} ${limits.unit} oralig'ida bo'lsin.`, field: 'size' };
  }
  const language = data.language ?? 'uz';
  if (!rules.languages[language]) return { error: 'Tilni tanlang.', field: 'language' };
  return { params: { type, topic, subject, size, language } };
}

/** Limitlar: null — ruxsat, aks holda { status, code, error }. today — bugungi so'rovlar, recent — oxirgi 60 s. */
export function checkLimits(today, recent, rules) {
  if (recent >= rules.per_minute) return { status: 429, code: 'rate_limit', error: RATE_TEXT };
  if (today >= rules.daily_limit) return { status: 429, code: 'daily_limit', error: LIMIT_TEXT };
  return null;
}
