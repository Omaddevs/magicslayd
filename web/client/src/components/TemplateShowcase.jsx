import { useCallback, useEffect, useRef, useState } from 'react';

import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';
import SlidePreview from './SlidePreview.jsx';

// ===================== Sevimlilar (yurakcha) — shu qurilmada saqlanadi =====================
const FAV_KEY = 'favTemplates';
function readFav() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]'));
  } catch {
    return new Set();
  }
}

export function useFavorites() {
  const [fav, setFav] = useState(readFav);
  const toggle = useCallback((id) => {
    haptic('light');
    setFav((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify([...next]));
      } catch {
        // maxfiy rejim — sevimlilar faqat shu ochilishda turadi
      }
      return next;
    });
  }, []);
  return [fav, toggle];
}

const Heart = ({ on }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
    <path
      d="M12 20s-7.5-4.4-7.5-10.1A4.4 4.4 0 0 1 12 7.2a4.4 4.4 0 0 1 7.5 2.7C19.5 15.6 12 20 12 20z"
      fill={on ? '#ff4d6d' : 'none'}
      stroke={on ? '#ff4d6d' : '#fff'}
      strokeWidth="2"
      strokeLinejoin="round"
    />
  </svg>
);

// ===================== Hujjat turlari uchun rasmlar (referat, kurs ishi, mustaqil ish) =====================
function PaperArt() {
  return (
    <svg viewBox="0 0 140 90" className="rec__svg" aria-hidden="true">
      <g transform="rotate(-12 70 50)">
        <rect x="34" y="14" width="64" height="80" rx="6" fill="#dbe7ff" />
        <rect x="42" y="8" width="64" height="80" rx="6" fill="#fff" />
        <rect x="50" y="20" width="34" height="5" rx="2.5" fill="#3b82f6" />
        {[32, 39, 46, 53, 60, 67].map((y) => <rect key={y} x="50" y={y} width={y % 14 ? 46 : 36} height="3" rx="1.5" fill="#b8c9ee" />)}
      </g>
      <rect x="92" y="52" width="30" height="34" rx="4" fill="#1d4ed8" opacity="0.85" transform="rotate(8 107 69)" />
    </svg>
  );
}

function BooksArt() {
  return (
    <svg viewBox="0 0 140 90" className="rec__svg" aria-hidden="true">
      <rect x="40" y="62" width="76" height="13" rx="3" fill="#0e7490" />
      <rect x="44" y="49" width="70" height="13" rx="3" fill="#f8fafc" />
      <rect x="44" y="49" width="8" height="13" fill="#38bdf8" />
      <rect x="38" y="36" width="74" height="13" rx="3" fill="#155e75" />
      <rect x="46" y="23" width="62" height="13" rx="3" fill="#e0f2fe" />
      <rect x="46" y="23" width="7" height="13" fill="#0ea5e9" />
      <rect x="40" y="75" width="80" height="6" rx="3" fill="#083344" opacity="0.5" />
    </svg>
  );
}

function ChecklistArt() {
  return (
    <svg viewBox="0 0 140 90" className="rec__svg" aria-hidden="true">
      <rect x="40" y="6" width="62" height="82" rx="7" fill="#fff" transform="rotate(6 71 47)" />
      {[24, 40, 56].map((y) => (
        <g key={y} transform="rotate(6 71 47)">
          <rect x="50" y={y} width="10" height="10" rx="3" fill="#22c55e" />
          <path d={`m52 ${y + 5} 2.5 2.5 4-5`} stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" />
          <rect x="65" y={y + 3} width="28" height="4" rx="2" fill="#c7d2fe" />
        </g>
      ))}
    </svg>
  );
}

export const DOC_TYPES = {
  referat: { title: 'Referat', sub: '(ilmiy uslub)', color: 'blue', Art: PaperArt },
  kurs: { title: 'Kurs ishi', sub: '(namuna)', color: 'sky', Art: BooksArt },
  mustaqil: { title: 'Mustaqil ish', sub: '(topshiriq)', color: 'green', Art: ChecklistArt },
};

const plain = (name) => String(name || '').replace(/^[^\p{L}\p{N}]+/u, '');

// ===================== «Tavsiya etilgan shablonlar» — gorizontal karusel =====================
/** items: [{ id, type: 'theme' | 'doc', key, theme?, title, sub, color }] */
export function RecommendedCarousel({ items, fav, onFav, onPick }) {
  const track = useRef(null);
  const [page, setPage] = useState({ index: 0, count: 1 });

  useEffect(() => {
    const el = track.current;
    if (!el) return undefined;
    const measure = () => {
      const count = Math.max(1, Math.ceil((el.scrollWidth - 2) / el.clientWidth));
      const max = Math.max(1, el.scrollWidth - el.clientWidth);
      setPage({ count, index: Math.round((el.scrollLeft / max) * (count - 1)) || 0 });
    };
    measure();
    el.addEventListener('scroll', measure, { passive: true });
    window.addEventListener('resize', measure);
    // Kompyuterda sichqoncha g'ildiragi gorizontal aylantiradi
    const onWheel = (e) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX) || el.scrollWidth <= el.clientWidth) return;
      const atStart = el.scrollLeft <= 0 && e.deltaY < 0;
      const atEnd = el.scrollLeft >= el.scrollWidth - el.clientWidth - 1 && e.deltaY > 0;
      if (atStart || atEnd) return; // chetda — sahifa o'zi aylanadi
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('scroll', measure);
      window.removeEventListener('resize', measure);
      el.removeEventListener('wheel', onWheel);
    };
  }, [items.length]);

  const goPage = (i) => {
    const el = track.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    el.scrollTo({ left: (max * i) / Math.max(1, page.count - 1), behavior: 'smooth' });
  };

  return (
    <div className="rec">
      <div className="rec__track" ref={track}>
        {items.map((item) => {
          const doc = item.type === 'doc' ? DOC_TYPES[item.key] : null;
          return (
            <div key={item.id} className={`rec__card rec__card--${item.color}`}>
              <button className="rec__open pressable" onClick={() => onPick(item)} aria-label={`${t(item.title)} ${t(item.sub)}`}>
                <span className="rec__text">
                  <b>{t(item.title)}</b>
                  <span>{t(item.sub)}</span>
                </span>
                <span className="rec__visual">
                  {doc ? <doc.Art /> : <span className="rec__slide"><SlidePreview theme={item.theme} /></span>}
                </span>
              </button>
              <button
                className={`rec__fav ${fav.has(item.id) ? 'rec__fav--on' : ''}`}
                onClick={() => onFav(item.id)}
                aria-label={fav.has(item.id) ? t('Sevimlilardan olib tashlash') : t("Sevimlilarga qo'shish")}
                aria-pressed={fav.has(item.id)}
              >
                <Heart on={fav.has(item.id)} />
              </button>
            </div>
          );
        })}
      </div>
      {page.count > 1 && (
        <div className="rec__dots">
          {Array.from({ length: page.count }, (_, i) => (
            <button key={i} className={`rec__dot ${i === page.index ? 'rec__dot--on' : ''}`} onClick={() => goPage(i)} aria-label={`${i + 1}-sahifa`} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Shablonlar ro'yxatidan tavsiya kartochkalari: maketli shablonlar va hujjat turlari aralash. */
export function buildRecommended(themes) {
  const styled = themes.filter((item) => item.theme.style);
  const docs = Object.keys(DOC_TYPES).map((key) => ({
    id: `doc:${key}`, type: 'doc', key, title: DOC_TYPES[key].title, sub: DOC_TYPES[key].sub, color: DOC_TYPES[key].color,
  }));
  const palette = ['purple', 'violet', 'amber', 'rose'];
  const pres = styled.map((item, i) => ({
    id: `theme:${item.key}`, type: 'theme', key: item.key, theme: item.theme,
    title: plain(item.theme.name), sub: 'Presentatsiya', color: palette[i % palette.length],
  }));
  // Taqdimot · hujjat · taqdimot · hujjat … — rasmdagidek aralash
  const out = [];
  for (let i = 0; i < Math.max(pres.length, docs.length); i += 1) {
    if (pres[i]) out.push(pres[i]);
    if (docs[i]) out.push(docs[i]);
  }
  return out;
}
