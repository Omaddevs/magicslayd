// Maqola: turlari, narxi, muharrir modeli (bloklar ↔ HTML) va yuklab olish.
// Bloklar modeli bot bilan bir xil (prezentatsiya_bot/articles/model.py): h, p, ul, ol, table, img.
import { api } from './api.js';
import { pollOrder } from './editing.js';
import { t } from './i18n.js';
import { haptic, saveFile } from './telegram.js';

export const ARTICLE_TYPES = [
  { key: 'general', icon: '📝', title: 'Oddiy maqola', about: 'Sodda va ravon til: kirish, asosiy qism, xulosa — mavzuga mos sarlavhalar bilan' },
  { key: 'scientific', icon: '🔬', title: 'Ilmiy maqola', about: "Annotatsiya, kalit so'zlar, metodologiya, natijalar, muhokama va haqiqiy manbalar" },
  { key: 'analytical', icon: '📊', title: 'Tahliliy maqola', about: 'Muammo, sabab va oqibatlar, dalillar, qarashlarni taqqoslash va yechimlar' },
  { key: 'journalistic', icon: '📰', title: 'Publitsistik maqola', about: "Dolzarb mavzu, qiziqarli sarlavha, ta'sirchan uslub va hayotiy misollar" },
  { key: 'review', icon: '📚', title: 'Sharh maqolasi', about: "Tadqiqotlarni umumlashtirish va taqqoslash, bo'shliqlarni ko'rsatish, manbalar" },
];
export const TYPE_BY_KEY = Object.fromEntries(ARTICLE_TYPES.map((x) => [x.key, x]));
export const SIZE_NAMES = { short: 'Qisqa', medium: "O'rta", long: 'Kengaytirilgan' };
export const STYLE_NAMES = { auto: 'Avtomatik', academic: 'Ilmiy', simple: 'Sodda' };

export const articlePrice = (words, cfg) => Math.max(cfg.price_min, Math.ceil(words / 100) * cfg.price_per_100);
export const targetWords = ([low, high]) => Math.round((low + high) / 2);

// ===================================================================================================
// Bloklar → muharrir HTML
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function runsHtml(runs) {
  return (runs || []).map((r) => {
    let h = esc(r.text).replace(/\n/g, '<br>');
    const style = [r.color && `color:${r.color}`, r.size && `font-size:${r.size}pt`].filter(Boolean).join(';');
    if (style) h = `<span style="${style}">${h}</span>`;
    if (r.b) h = `<b>${h}</b>`;
    if (r.i) h = `<i>${h}</i>`;
    if (r.u) h = `<u>${h}</u>`;
    if (r.link) h = `<a href="${esc(r.link)}" target="_blank" rel="noopener noreferrer">${h}</a>`;
    return h;
  }).join('') || '<br>';
}

export function figureHtml(block, mediaUrl) {
  return `<figure class="art-fig art-fig--${block.align}" contenteditable="false" data-src="${esc(block.src)}" data-width="${block.width}" data-align="${block.align}">`
    + `<img src="${esc(mediaUrl(block.src))}" alt="" style="width:${block.width}%">`
    + `<figcaption>${esc(block.caption || '')}</figcaption></figure>`;
}

export function blocksToHtml(blocks, mediaUrl) {
  return blocks.map((b) => {
    if (b.t === 'h') return `<h${b.level} style="text-align:${b.align}">${runsHtml(b.runs)}</h${b.level}>`;
    if (b.t === 'p') return `<p style="text-align:${b.align}">${runsHtml(b.runs)}</p>`;
    if (b.t === 'ul' || b.t === 'ol') return `<${b.t}>${b.items.map((i) => `<li>${runsHtml(i)}</li>`).join('')}</${b.t}>`;
    if (b.t === 'table') {
      const rows = b.rows.map((row, r) => `<tr>${row.map((cell) => {
        const tag = b.head && r === 0 ? 'th' : 'td';
        return `<${tag}>${runsHtml(cell)}</${tag}>`;
      }).join('')}</tr>`).join('');
      return `<table class="art-table"><tbody>${rows}</tbody></table>`;
    }
    if (b.t === 'img') return figureHtml(b, mediaUrl);
    return '';
  }).join('') || '<p><br></p>';
}

// ===================================================================================================
// Muharrir DOM → bloklar (faqat ma'lum teglar olinadi — begona HTML saqlanmaydi)
const FONT_SIZES = { 1: 8, 2: 10, 3: 12, 4: 14, 5: 18, 6: 24, 7: 32 };
const ALIGNS = ['left', 'center', 'right', 'justify'];

function hexColor(value) {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(v)) return v;
  if (/^#[0-9a-f]{3}$/.test(v)) return `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}`;
  const m = v.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (m) return `#${[m[1], m[2], m[3]].map((n) => Number(n).toString(16).padStart(2, '0')).join('')}`;
  return null;
}

function alignOf(el, fallback) {
  const a = (el.style?.textAlign || el.getAttribute?.('align') || '').toLowerCase();
  if (a === 'start') return 'left';
  if (a === 'end') return 'right';
  return ALIGNS.includes(a) ? a : fallback;
}

const sameMarks = (a, b) => ['b', 'i', 'u', 'color', 'size', 'link'].every((k) => (a[k] ?? null) === (b[k] ?? null));

function inline(node, marks = {}, out = []) {
  for (const child of node.childNodes) {
    if (child.nodeType === 3) {
      const text = child.nodeValue.replace(/ /g, ' ').replace(/[​]/g, '');
      if (text) out.push({ text, ...marks });
      continue;
    }
    if (child.nodeType !== 1) continue;
    const tag = child.tagName;
    if (tag === 'BR') {
      out.push({ text: '\n', ...marks });
      continue;
    }
    if (tag === 'FIGURE' || tag === 'TABLE' || tag === 'IMG') continue;
    const m = { ...marks };
    if (tag === 'B' || tag === 'STRONG') m.b = 1;
    if (tag === 'I' || tag === 'EM') m.i = 1;
    if (tag === 'U') m.u = 1;
    if (tag === 'A' && /^(https?:\/\/|mailto:)/i.test(child.getAttribute('href') || '')) m.link = child.getAttribute('href');
    if (tag === 'FONT') {
      const c = hexColor(child.getAttribute('color'));
      if (c) m.color = c;
      const s = FONT_SIZES[Number(child.getAttribute('size'))];
      if (s) m.size = s;
    }
    const st = child.style;
    if (st) {
      const c = hexColor(st.color);
      if (c) m.color = c;
      if (st.fontSize) {
        const n = parseFloat(st.fontSize);
        if (n) m.size = Math.round(st.fontSize.endsWith('px') ? n * 0.75 : n);
      }
      if (st.fontWeight === 'bold' || Number(st.fontWeight) >= 600) m.b = 1;
      if (st.fontStyle === 'italic') m.i = 1;
      if ((st.textDecorationLine || st.textDecoration || '').includes('underline')) m.u = 1;
    }
    inline(child, m, out);
  }
  return out;
}

function cleanRuns(raw) {
  const runs = [];
  for (const r of raw) {
    if (r.size && (r.size < 8 || r.size > 40 || r.size === 12)) delete r.size; // 12 pt — asosiy o'lcham
    if (r.color === '#000000' || r.color === '#141414') delete r.color;
    const last = runs.at(-1);
    if (last && sameMarks(last, r)) last.text += r.text;
    else runs.push({ ...r });
  }
  // Boshidagi va oxiridagi qator ko'chishlari olib tashlanadi
  while (runs.length && !runs[0].text.trim()) runs.shift();
  while (runs.length && !runs.at(-1).text.trim()) runs.pop();
  if (runs.length) {
    runs[0].text = runs[0].text.replace(/^\s+/, '');
    runs.at(-1).text = runs.at(-1).text.replace(/\s+$/, '');
  }
  return runs.filter((r) => r.text);
}

const runsOf = (el) => cleanRuns(inline(el));

export function htmlToBlocks(root) {
  const blocks = [];
  const walk = (parent) => {
    for (const el of parent.childNodes) {
      if (el.nodeType === 3) {
        const text = el.nodeValue.trim();
        if (text) blocks.push({ t: 'p', align: 'justify', runs: [{ text }] });
        continue;
      }
      if (el.nodeType !== 1) continue;
      const tag = el.tagName;
      if (/^H[1-6]$/.test(tag)) {
        const runs = runsOf(el);
        if (runs.length) blocks.push({ t: 'h', level: Math.min(3, Number(tag[1])), align: alignOf(el, 'left'), runs });
      } else if (tag === 'UL' || tag === 'OL') {
        const items = [...el.children].filter((li) => li.tagName === 'LI').map(runsOf).filter((r) => r.length);
        if (items.length) blocks.push({ t: tag.toLowerCase(), items });
      } else if (tag === 'TABLE') {
        const rows = [...el.querySelectorAll('tr')].map((tr) => [...tr.children].filter((c) => /^T[DH]$/.test(c.tagName)).map(runsOf));
        const filtered = rows.filter((r) => r.length);
        if (filtered.length) {
          const head = Boolean(el.querySelector('tr')?.querySelector('th'));
          blocks.push({ t: 'table', head, rows: filtered });
        }
      } else if (tag === 'FIGURE' && el.dataset.src) {
        blocks.push({
          t: 'img', src: el.dataset.src, width: Number(el.dataset.width) || 80,
          align: el.dataset.align || 'center', caption: el.querySelector('figcaption')?.textContent.trim() || '',
        });
      } else if (tag === 'DIV' || tag === 'SECTION' || tag === 'BLOCKQUOTE' || tag === 'ARTICLE') {
        // Ichida blok elementlar bo'lsa — ular alohida, aks holda bitta xatboshi
        if ([...el.children].some((c) => /^(P|H[1-6]|UL|OL|TABLE|FIGURE|DIV)$/.test(c.tagName))) walk(el);
        else {
          const runs = runsOf(el);
          if (runs.length) blocks.push({ t: 'p', align: alignOf(el, 'justify'), runs });
        }
      } else if (tag !== 'BR') {
        const runs = runsOf(el);
        if (runs.length) blocks.push({ t: 'p', align: alignOf(el, 'justify'), runs });
      }
    }
  };
  walk(root);
  return blocks;
}

/** Matn hajmi (adabiyotlar va jadvallarsiz — bot bilan bir xil hisob). */
export function wordCount(blocks) {
  const plain = (runs) => runs.map((r) => r.text).join('');
  let total = 0;
  let prev = null;
  for (const b of blocks) {
    if (b.t === 'h' || b.t === 'p') total += plain(b.runs).split(/\s+/).filter(Boolean).length;
    else if ((b.t === 'ul' || b.t === 'ol') && !(prev?.t === 'h' && REF_TITLES.has(plain(prev.runs)))) {
      total += b.items.reduce((s, i) => s + plain(i).split(/\s+/).filter(Boolean).length, 0);
    }
    prev = b;
  }
  return total;
}
const REF_TITLES = new Set(['Foydalanilgan adabiyotlar', 'Список литературы', 'References']);

// ===================================================================================================
// Yuklab olish va chatga yuborish — doim JORIY (oxirgi saqlangan) versiyadan
async function ensureExport(id, fmt) {
  const result = await api(`/articles/${id}/export`, { method: 'POST', body: { fmt } });
  if (result.orderId) await pollOrder(result.orderId);
}

export async function downloadArticle(id, fmt) {
  haptic('medium');
  await ensureExport(id, fmt);
  const { url, fileName } = await api(`/articles/${id}/link`, { method: 'POST', body: { fmt } });
  saveFile(url, fileName);
  return fileName;
}

export async function sendArticle(id, fmt) {
  await ensureExport(id, fmt);
  await api(`/articles/${id}/send`, { method: 'POST', body: { fmt } });
}

export const typeTitle = (key) => t(TYPE_BY_KEY[key]?.title ?? 'Maqola');
