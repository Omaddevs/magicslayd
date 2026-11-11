import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { useApp } from '../app/AppContext.jsx';
import { api, apiUpload } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { prepareImage } from '../lib/media.js';
import { confirmDialog, haptic, openLink } from '../lib/telegram.js';
import { ChevronLeft, ChevronRight, CloseIcon, ImageIcon, PlusIcon, SendIcon, TrashIcon } from './Icons.jsx';
import { Sheet } from './ui.jsx';

// ===================== Umumiy =====================
// Story turlari: doira rangi, belgisi va nomi. Server: routes/news.js → STORY_KINDS
export const STORY_KINDS = {
  yangilanish: { label: 'Yangilanish', from: '#4f8cff', to: '#2f55d4' },
  blog: { label: 'Blog', from: '#6d7cff', to: '#4338ca' },
  aksiya: { label: 'Aksiyalar', from: '#ff8a5b', to: '#e8364f' },
  qollanma: { label: "Qo'llanma", from: '#8b7bff', to: '#5b3de6' },
  yangilik: { label: 'Yangilik', from: '#a855f7', to: '#6d28d9' },
};

// Tugma bosilganda ochiladigan ilova bo'limlari. Server: routes/news.js → APP_LINKS
export const APP_TARGETS = [
  ['pres', 'Presentatsiya yaratish'],
  ['referat', 'Referat yaratish'],
  ['kurs', 'Kurs ishi yaratish'],
  ['mustaqil', 'Mustaqil ish yaratish'],
  ['diploma', 'Diplom ishi'],
  ['dissertation', 'Dissertatsiya'],
  ['ai', 'AI yordamchi'],
  ['templates', 'Shablonlar'],
  ['materials', 'Ommabop materiallar'],
  ['topup', "Hisobni to'ldirish"],
];

/** Story / reklama tugmasi: «app:pres» — ilova bo'limi, https://… — tashqi havola. */
export function useOpenTarget() {
  const { push, setTab, topup } = useApp();
  return useCallback(
    (link) => {
      if (!link) return;
      haptic('light');
      if (!link.startsWith('app:')) return openLink(link);
      const target = link.slice(4);
      if (['pres', 'referat', 'kurs', 'mustaqil'].includes(target)) push('order', { kind: target });
      else if (target === 'templates') setTab('templates');
      else if (target === 'topup') topup();
      else push(target);
    },
    [push, setTab, topup],
  );
}

const SEEN_KEY = 'seenStories';
function readSeen() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'));
  } catch {
    return new Set();
  }
}
function writeSeen(set) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...set].slice(-200)));
  } catch {
    // maxfiy rejim — ko'rilganlar eslab qolinmaydi, muhim emas
  }
}

// ===================== Story belgilari =====================
const KindGlyph = ({ kind }) => {
  const common = { width: 26, height: 26, viewBox: '0 0 24 24', fill: 'none', stroke: '#fff', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
  switch (kind) {
    case 'yangilanish':
      return <svg {...common}><path d="M5 19V13M10 19V9M15 19v-4M20 19V5" strokeWidth="2.6" /></svg>;
    case 'blog':
      return <svg {...common}><rect x="3.5" y="4" width="17" height="16" rx="3" /><path d="M7.5 9h9M7.5 12.5h9M7.5 16h5" /></svg>;
    case 'aksiya':
      return <svg {...common}><rect x="4" y="9" width="16" height="11" rx="2" /><path d="M3 9h18M12 9v11M12 9c-1.5-3.5-5.5-4-5.5-1.5S12 9 12 9zm0 0c1.5-3.5 5.5-4 5.5-1.5S12 9 12 9z" /></svg>;
    case 'qollanma':
      return <svg {...common}><path d="M12 6.5c-2-1.6-5-2-8-1.5v13c3-.5 6-.1 8 1.5 2-1.6 5-2 8-1.5V5c-3-.5-6-.1-8 1.5zM12 6.5v13" /></svg>;
    default:
      return <svg {...common}><path d="M4 10v4h3l6 4V6L7 10zM16.5 9a4 4 0 0 1 0 6M19 6.5a7.5 7.5 0 0 1 0 11" /></svg>;
  }
};

function StoryBubble({ kind, image }) {
  const meta = STORY_KINDS[kind] || STORY_KINDS.yangilik;
  return (
    <span className="story__bubble" style={{ '--from': meta.from, '--to': meta.to }}>
      {image ? <img src={image} alt="" loading="lazy" /> : <KindGlyph kind={kind} />}
    </span>
  );
}

// ===================== Yangiliklar qatori =====================
/** Story'lar turi bo'yicha guruhlanadi (Instagram'dagidek): bitta doira — bitta tur, ichida bir nechta yangilik. */
export function groupStories(stories) {
  const groups = [];
  const byKind = new Map();
  for (const story of stories) {
    if (!byKind.has(story.kind)) {
      const group = { kind: story.kind, items: [] };
      byKind.set(story.kind, group);
      groups.push(group);
    }
    byKind.get(story.kind).items.push(story);
  }
  // Har bir guruh ichida — eskisidan yangisiga (ketma-ket o'qiladi)
  groups.forEach((g) => g.items.reverse());
  return groups;
}

export function Stories({ stories, isAdmin, onAdd, onOpen, seen }) {
  const groups = useMemo(() => groupStories(stories), [stories]);
  if (!groups.length && !isAdmin) return null;
  return (
    <div className="stories" role="list">
      {isAdmin && (
        <button className="story story--add pressable" onClick={onAdd} role="listitem">
          <span className="story__ring story__ring--add">
            <span className="story__bubble story__bubble--add"><PlusIcon size={26} /></span>
          </span>
          <span className="story__name">{t("Qo'shish")}</span>
        </button>
      )}
      {groups.map((group, index) => {
        const unseen = group.items.some((s) => !seen.has(s.id));
        const cover = group.items[group.items.length - 1];
        return (
          <button key={group.kind} className="story pressable" onClick={() => onOpen(index)} role="listitem">
            <span className={`story__ring ${unseen ? '' : 'story__ring--seen'}`}>
              <StoryBubble kind={group.kind} image={cover.image} />
            </span>
            <span className="story__name">{t(STORY_KINDS[group.kind]?.label || t("Yangilik"))}</span>
          </button>
        );
      })}
      {!groups.length && <span className="stories__empty">{t("Birinchi yangilikni qo'shing — hamma foydalanuvchilar ko'radi")}</span>}
    </div>
  );
}

// ===================== Story ko'rish oynasi =====================
const durationOf = (story) =>
  Math.min(15000, 6000 + ((story.title?.length || 0) + (story.text?.length || 0) + (story.points || []).join('').length) * 30);

const DEFAULT_BADGE = {
  yangilanish: '🚀 Yangi yangilanish!',
  blog: '📝 Yangi maqola',
  aksiya: '🎁 Aksiya!',
  qollanma: "📘 Qo'llanma",
  yangilik: '📣 Yangilik',
};

/** Qisqa vaqt: 15s, 5 daq, 3 soat, 2 kun */
function shortAgo(value) {
  const date = new Date(String(value || '').replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return '';
  const s = Math.max(1, Math.round((Date.now() - date.getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return t('{n} daq', { n: Math.round(s / 60) });
  if (s < 86400) return t('{n} soat', { n: Math.round(s / 3600) });
  return t('{n} kun', { n: Math.round(s / 86400) });
}

/** Sarlavhadagi *so'zlar* rangli (gradient) bo'ladi: «Endi *AI bilan* yarating» */
function Headline({ text }) {
  const parts = String(text || '').split(/\*([^*]+)\*/g);
  return parts.map((part, i) => (i % 2 ? <span key={i} className="sv-grad">{part}</span> : part));
}

function BrandBubble() {
  return (
    <span className="sv-brand" aria-hidden="true">
      <svg viewBox="0 0 32 32" width="22" height="22">
        <path d="M16 19.5 3.5 13.2 16 7l12.5 6.2z" fill="#fff" />
        <path d="m3.5 17.4 12.5 6.3 12.5-6.3-3.3-1.7-9.2 4.6-9.2-4.6z" fill="#fff" opacity="0.75" />
        <path d="m3.5 21.6 12.5 6.3 12.5-6.3-3.3-1.7-9.2 4.6-9.2-4.6z" fill="#fff" opacity="0.5" />
      </svg>
    </span>
  );
}

/** Rasm yuklanmagan story uchun illyustratsiya: noutbuk, «AI» va suzib yuruvchi belgilar */
function StoryArt({ kind }) {
  if (kind === 'aksiya') {
    return (
      <svg viewBox="0 0 300 200" className="sv-art" aria-hidden="true">
        <defs>
          <linearGradient id="svGift" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ff9a6b" /><stop offset="1" stopColor="#e8364f" /></linearGradient>
          <linearGradient id="svRibbon" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fde68a" /><stop offset="1" stopColor="#f59e0b" /></linearGradient>
        </defs>
        <g className="ad__float">
          <rect x="95" y="80" width="110" height="90" rx="12" fill="url(#svGift)" />
          <rect x="85" y="62" width="130" height="30" rx="10" fill="#ff7a59" />
          <rect x="142" y="62" width="16" height="108" fill="url(#svRibbon)" />
          <path d="M150 62c-14-30-48-30-40-8 6 14 40 8 40 8zm0 0c14-30 48-30 40-8-6 14-40 8-40 8z" fill="url(#svRibbon)" />
        </g>
        <g className="ad__float ad__float--late">
          <circle cx="60" cy="70" r="24" fill="#fff" opacity="0.18" />
          <text x="60" y="78" textAnchor="middle" fontSize="22" fontWeight="900" fill="#fff">%</text>
        </g>
        <path d="M250 40c1 7 4 10 11 11-7 1-10 4-11 11-1-7-4-10-11-11 7-1 10-4 11-11z" fill="#fff" opacity="0.8" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 300 210" className="sv-art" aria-hidden="true">
      <defs>
        <linearGradient id="svScreen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2c1f78" /><stop offset="1" stopColor="#120c38" /></linearGradient>
        <linearGradient id="svSlide" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8f7bff" /><stop offset="1" stopColor="#4f35d8" /></linearGradient>
        <linearGradient id="svBase" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e4e1fb" /><stop offset="1" stopColor="#9d97c9" /></linearGradient>
        <linearGradient id="svAi" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#a5f3fc" /><stop offset="0.45" stopColor="#7c5cff" /><stop offset="1" stopColor="#4c1dd6" /></linearGradient>
        <linearGradient id="svChip" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#c4b5fd" /><stop offset="1" stopColor="#7c5cff" /></linearGradient>
      </defs>
      <g transform="translate(62 38) skewY(-8)">
        <rect x="0" y="0" width="196" height="122" rx="10" fill="#0d0a26" />
        <rect x="7" y="7" width="182" height="108" rx="6" fill="url(#svScreen)" />
        {[16, 40, 64, 88].map((y) => <rect key={y} x="14" y={y} width="34" height="20" rx="3" fill="#6d5af0" opacity={y === 16 ? 1 : 0.6} />)}
        <rect x="56" y="16" width="126" height="92" rx="5" fill="url(#svSlide)" />
        <text x="68" y="44" fontSize="13" fontWeight="800" fill="#fff" fontStyle="italic">{t("Presentatsiya")}</text>
        <rect x="68" y="54" width="70" height="4" rx="2" fill="#fff" opacity="0.55" />
        <rect x="68" y="63" width="54" height="4" rx="2" fill="#fff" opacity="0.55" />
        <rect x="-16" y="122" width="228" height="12" rx="6" fill="url(#svBase)" />
      </g>
      <g className="ad__float">
        <rect x="214" y="122" width="70" height="70" rx="20" fill="url(#svAi)" />
        <rect x="218" y="125" width="62" height="28" rx="14" fill="#fff" opacity="0.25" />
        <text x="249" y="168" textAnchor="middle" fontSize="28" fontWeight="900" fill="#fff">{t("AI")}</text>
      </g>
      <g className="ad__float ad__float--late">
        <rect x="22" y="60" width="50" height="50" rx="14" fill="url(#svChip)" opacity="0.95" />
        <rect x="34" y="74" width="26" height="22" rx="3" fill="none" stroke="#fff" strokeWidth="3" />
        <path d="M39 82h16M39 88h10" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      </g>
      <g className="ad__float">
        <rect x="8" y="128" width="56" height="56" rx="16" fill="url(#svChip)" opacity="0.8" />
        <rect x="21" y="142" width="30" height="22" rx="4" fill="none" stroke="#fff" strokeWidth="3" />
        <path d="m32 148 8 5-8 5z" fill="#fff" />
      </g>
    </svg>
  );
}

const Heart = ({ on }) => (
  <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 20s-7.5-4.4-7.5-10.1A4.4 4.4 0 0 1 12 7.2a4.4 4.4 0 0 1 7.5 2.7C19.5 15.6 12 20 12 20z"
      fill={on ? '#ff4d6d' : 'none'} stroke={on ? '#ff4d6d' : '#fff'} strokeWidth="2" strokeLinejoin="round" />
  </svg>
);

/** «Batafsil» — admin qo'ygan reklama / yangilik sahifasi (rasm, to'liq matn, tugma) */
function StoryDetail({ story, onBack, onAction }) {
  const cover = story.detailImage || story.image;
  return (
    <div className="sv-detail" role="dialog" aria-label={story.title || t('Batafsil')}>
      <div className="sv-detail__scroll">
        {cover ? (
          <img className="sv-detail__cover" src={cover} alt="" />
        ) : (
          <div className="sv-detail__cover sv-detail__cover--art"><StoryArt kind={story.kind} /></div>
        )}
        <div className="sv-detail__body">
          <span className="sv-badge">{story.badge || t(DEFAULT_BADGE[story.kind] || DEFAULT_BADGE.yangilik)}</span>
          {story.title && <h2><Headline text={story.title} /></h2>}
          {story.text && <p className="sv-detail__lead">{story.text}</p>}
          {story.points?.length > 0 && (
            <ul className="sv-points">
              {story.points.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
          {story.details && <div className="sv-detail__text">{story.details}</div>}
        </div>
      </div>
      <button className="sv-detail__back" onClick={onBack} aria-label={t('Orqaga')}><ChevronLeft size={22} /></button>
      {story.link && (
        <div className="sv-detail__bar">
          <button className="sv-cta sv-cta--wide pressable" onClick={onAction}>
            {story.button && story.button !== 'Batafsil' ? story.button : t('Davom etish')} <ChevronRight size={18} />
          </button>
        </div>
      )}
    </div>
  );
}

export function StoryViewer({ stories, startGroup, isAdmin, onClose, onSeen, onDeleted }) {
  const { toast, authed, requireAuth } = useApp();
  // Mehmon like yoki javob yozmoqchi bo'lsa — story yopilib, kirish oynasi chiqadi
  const askLogin = (reason) => {
    onClose();
    requireAuth(null, reason);
  };
  const groups = useMemo(() => groupStories(stories), [stories]);
  const openTarget = useOpenTarget();
  const [pos, setPos] = useState(() => {
    const g = Math.min(startGroup, groups.length - 1);
    const seen = readSeen();
    const first = groups[g]?.items.findIndex((s) => !seen.has(s.id));
    return { g, i: first > 0 ? first : 0 };
  });
  const [progress, setProgress] = useState(0);
  const [held, setHeld] = useState(false);
  const [detail, setDetail] = useState(false);
  const [typing, setTyping] = useState(false);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);
  const [likes, setLikes] = useState({}); // story.id → { liked, likes } (bosilgandan keyin)
  const heldAt = useRef(0);
  const story = groups[pos.g]?.items[pos.i];
  const meta = STORY_KINDS[groups[pos.g]?.kind] || STORY_KINDS.yangilik;
  const paused = held || detail || typing || sending;
  const like = story ? likes[story.id] || { liked: story.liked, likes: story.likes } : null;

  const next = useCallback(() => {
    const { g, i } = pos;
    setProgress(0);
    setDetail(false);
    if (i + 1 < groups[g].items.length) setPos({ g, i: i + 1 });
    else if (g + 1 < groups.length) setPos({ g: g + 1, i: 0 });
    else onClose();
  }, [pos, groups, onClose]);

  const prev = useCallback(() => {
    const { g, i } = pos;
    setProgress(0);
    setDetail(false);
    if (i > 0) setPos({ g, i: i - 1 });
    else if (g > 0) setPos({ g: g - 1, i: groups[g - 1].items.length - 1 });
  }, [pos, groups]);

  useEffect(() => {
    if (progress >= 1) next();
  }, [progress, next]);

  useEffect(() => {
    if (story) onSeen(story.id);
  }, [story, onSeen]);

  useEffect(() => {
    if (!story || paused) return undefined;
    const total = durationOf(story);
    let last = performance.now();
    let frame;
    const tick = (now) => {
      const delta = now - last;
      last = now;
      setProgress((p) => Math.min(1, p + delta / total));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [story, paused]);

  useEffect(() => {
    const onKey = (e) => {
      if (typing) return;
      if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') prev();
      else if (e.key === 'Escape') (detail ? setDetail(false) : onClose());
    };
    window.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [next, prev, onClose, detail, typing]);

  if (!story) return null;

  const poster = Boolean(story.image && !story.title);
  const hasMore = Boolean(story.details || story.detailImage || story.link);

  const remove = async () => {
    setHeld(true);
    if (!(await confirmDialog(t("Bu yangilikni o'chirasizmi? Hamma foydalanuvchilardan o'chadi.")))) {
      setHeld(false);
      return;
    }
    try {
      await api(`/news/stories/${story.id}`, { method: 'DELETE' });
      haptic('success');
      onDeleted();
      onClose();
    } catch (e) {
      setHeld(false);
      toast(e.message, 'error');
    }
  };

  const more = () => {
    haptic('light');
    // Batafsil sahifa bo'lmasa — tugma to'g'ridan-to'g'ri havolaga olib boradi
    if (story.details || story.detailImage) setDetail(true);
    else {
      onClose();
      openTarget(story.link);
    }
  };

  const toggleLike = async () => {
    if (!authed) return askLogin(t('Yangilikni yoqtirish uchun hisobingizga kiring'));
    haptic('light');
    const optimistic = { liked: !like.liked, likes: like.likes + (like.liked ? -1 : 1) };
    setLikes((m) => ({ ...m, [story.id]: optimistic }));
    try {
      const result = await api(`/news/stories/${story.id}/like`, { method: 'POST' });
      setLikes((m) => ({ ...m, [story.id]: result }));
    } catch {
      setLikes((m) => ({ ...m, [story.id]: like }));
    }
  };

  const send = async (e) => {
    e.preventDefault();
    const text = reply.trim();
    if (!text || sending) return;
    if (!authed) {
      askLogin(t('Xabar yozish uchun hisobingizga kiring'));
      return;
    }
    setSending(true);
    try {
      await api(`/news/stories/${story.id}/reply`, { method: 'POST', body: { text } });
      haptic('success');
      setReply('');
      document.activeElement?.blur?.();
      toast(t('Xabaringiz yuborildi') + ' ✅');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setSending(false);
    }
  };

  const holdStart = () => {
    heldAt.current = Date.now();
    setHeld(true);
  };
  const holdEnd = () => setHeld(false);
  const tap = (fn) => () => {
    if (Date.now() - heldAt.current < 250) fn();
  };

  return createPortal(
    <div className="story-view" role="dialog" aria-modal="true" aria-label={story.title || t('Yangilik')}>
      <div className={`story-view__frame sv ${poster ? 'sv--poster' : ''}`} style={{ '--from': meta.from, '--to': meta.to }}>
        {poster && <img className="story-view__image" src={story.image} alt="" />}
        {poster && <div className="story-view__shade" />}

        <div className="story-view__top">
          <div className="story-view__bars">
            {groups[pos.g].items.map((s, k) => (
              <span key={s.id} className="story-view__bar">
                <span style={{ transform: `scaleX(${k < pos.i ? 1 : k === pos.i ? progress : 0})` }} />
              </span>
            ))}
          </div>
          <div className="story-view__head">
            <BrandBubble />
            <span className="sv-who">
              <b>MagicSlayd</b>
              <span>{shortAgo(story.createdAt)}</span>
            </span>
            {isAdmin && (
              <button className="story-view__icon" onClick={remove} aria-label={t("O'chirish")}><TrashIcon size={20} /></button>
            )}
            <button className="story-view__icon" onClick={onClose} aria-label={t('Yopish')}><CloseIcon size={22} /></button>
          </div>
        </div>

        {/* Bosish zonalari: chap — oldingi, o'ng — keyingi; bosib turish — pauza */}
        <button className="story-view__zone story-view__zone--prev" aria-label={t('Oldingi')} onClick={tap(prev)}
          onPointerDown={holdStart} onPointerUp={holdEnd} onPointerLeave={holdEnd} onContextMenu={(e) => e.preventDefault()} />
        <button className="story-view__zone story-view__zone--next" aria-label={t('Keyingi')} onClick={tap(next)}
          onPointerDown={holdStart} onPointerUp={holdEnd} onPointerLeave={holdEnd} onContextMenu={(e) => e.preventDefault()} />

        {!poster && (
          <div className="sv-content">
            <span className="sv-badge">{story.badge || t(DEFAULT_BADGE[story.kind] || DEFAULT_BADGE.yangilik)}</span>
            <h2 className="sv-title"><Headline text={story.title} /></h2>
            {story.text && <p className="sv-text">{story.text}</p>}
            {story.points?.length > 0 && (
              <ul className="sv-points">
                {story.points.map((p) => <li key={p}>{p}</li>)}
              </ul>
            )}
            <div className="sv-visual">
              {story.image ? <img className="sv-photo" src={story.image} alt="" /> : <StoryArt kind={story.kind} />}
            </div>
          </div>
        )}

        {hasMore && (
          <div className="sv-more">
            <button className="sv-cta pressable" onClick={more}>
              {t('Batafsil')} <ChevronRight size={18} />
            </button>
          </div>
        )}

        <form className="sv-reply" onSubmit={send}>
          <input
            className="sv-reply__input"
            value={reply}
            maxLength={1000}
            onChange={(e) => setReply(e.target.value)}
            onFocus={() => setTyping(true)}
            onBlur={() => setTyping(false)}
            placeholder={t('Xabar yuborish...')}
            enterKeyHint="send"
          />
          <button type="button" className={`sv-reply__btn ${like.liked ? 'sv-reply__btn--liked' : ''}`} onClick={toggleLike}
            aria-label={like.liked ? t('Yoqdi (bekor qilish)') : t('Yoqdi')} aria-pressed={like.liked}>
            <Heart on={like.liked} />
            {isAdmin && like.likes > 0 && <span className="sv-reply__count">{like.likes}</span>}
          </button>
          <button type="submit" className="sv-reply__btn" disabled={!reply.trim() || sending} aria-label={t('Yuborish')}>
            <SendIcon size={22} />
          </button>
        </form>

        {detail && (
          <StoryDetail
            story={story}
            onBack={() => setDetail(false)}
            onAction={() => { onClose(); openTarget(story.link); }}
          />
        )}
      </div>
    </div>,
    document.body,
  );
}

// ===================== Reklama banneri =====================
const ADS_BUILTIN = [
  {
    id: 'b1', builtin: true, color: 'purple', art: 'laptop', link: 'app:pres', button: "Hozir sinab ko'ring",
    title: 'AI bilan taqdimotni bir daqiqada yarating!',
    text: 'Mavzuni yozing — slaydlar, rasmlar va dizayn tayyor.',
  },
  {
    id: 'b2', builtin: true, color: 'blue', art: 'cap', link: 'app:diploma', button: 'Boshlash',
    title: 'Diplom ishi — rejadan tayyor faylgacha',
    text: "Haqiqiy manbalar, avtomatik mundarija va OTM talablari.",
  },
  {
    id: 'b3', builtin: true, color: 'orange', art: 'docs', link: 'app:referat', button: 'Yaratish',
    title: 'Referat va mustaqil ish bir necha daqiqada',
    text: 'Tayyor DOCX fayl to\'g\'ridan-to\'g\'ri Telegram chatga keladi.',
  },
];

function LaptopArt() {
  return (
    <svg viewBox="0 0 170 130" className="ad__art-svg" aria-hidden="true">
      <defs>
        <linearGradient id="adScreen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b2a8f" />
          <stop offset="1" stopColor="#1b1446" />
        </linearGradient>
        <linearGradient id="adSlide" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8f7bff" />
          <stop offset="1" stopColor="#5b3de6" />
        </linearGradient>
        <linearGradient id="adBase" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#d9d5f5" />
          <stop offset="1" stopColor="#9d97c9" />
        </linearGradient>
        <linearGradient id="adChip" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7dd3fc" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
      </defs>
      <g transform="translate(28 30) skewY(-6)">
        <rect x="0" y="0" width="118" height="74" rx="7" fill="#0f0b2e" />
        <rect x="5" y="5" width="108" height="64" rx="4" fill="url(#adScreen)" />
        <rect x="12" y="12" width="94" height="50" rx="4" fill="url(#adSlide)" opacity="0.95" />
        <rect x="18" y="19" width="40" height="5" rx="2.5" fill="#fff" />
        <rect x="18" y="28" width="54" height="3" rx="1.5" fill="#fff" opacity="0.6" />
        <rect x="18" y="34" width="46" height="3" rx="1.5" fill="#fff" opacity="0.6" />
        <path d="M66 54l12-14 9 9 7-6 8 11z" fill="#fff" opacity="0.35" />
        <rect x="-10" y="74" width="138" height="8" rx="4" fill="url(#adBase)" />
      </g>
      <g className="ad__float">
        <rect x="8" y="18" width="34" height="30" rx="9" fill="url(#adChip)" />
        <text x="25" y="38" textAnchor="middle" fontSize="13" fontWeight="900" fill="#fff" fontFamily="inherit">{t("AI")}</text>
      </g>
      <g className="ad__float ad__float--late">
        <rect x="136" y="6" width="28" height="28" rx="8" fill="#a78bfa" />
        <rect x="143" y="13" width="14" height="14" rx="3" fill="none" stroke="#fff" strokeWidth="2.2" />
        <path d="M146 20h8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </g>
    </svg>
  );
}

function CapArt() {
  return (
    <svg viewBox="0 0 170 130" className="ad__art-svg" aria-hidden="true">
      <defs>
        <linearGradient id="adPaper" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#dbe4ff" />
        </linearGradient>
        <linearGradient id="adCap" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b3f8f" />
          <stop offset="1" stopColor="#151845" />
        </linearGradient>
      </defs>
      <g transform="rotate(-8 85 75)">
        <rect x="52" y="30" width="78" height="96" rx="8" fill="url(#adPaper)" />
        <rect x="62" y="44" width="44" height="6" rx="3" fill="#4f6bf5" />
        {[58, 66, 74, 82, 90, 98].map((y) => <rect key={y} x="62" y={y} width={y % 16 ? 56 : 44} height="3.5" rx="1.75" fill="#9fb0e8" />)}
      </g>
      <g className="ad__float">
        <path d="M34 40 70 24l36 16-36 16z" fill="url(#adCap)" />
        <path d="M48 47v13c0 5 10 9 22 9s22-4 22-9V47l-22 9z" fill="#262a6b" />
        <path d="M103 41v18" stroke="#fbbf24" strokeWidth="3" strokeLinecap="round" />
        <circle cx="103" cy="61" r="4" fill="#fbbf24" />
      </g>
    </svg>
  );
}

function DocsArt() {
  return (
    <svg viewBox="0 0 170 130" className="ad__art-svg" aria-hidden="true">
      <rect x="70" y="18" width="70" height="92" rx="8" fill="#fff" opacity="0.55" transform="rotate(10 105 64)" />
      <rect x="44" y="22" width="74" height="96" rx="8" fill="#fff" />
      <rect x="54" y="34" width="38" height="6" rx="3" fill="#f97316" />
      {[48, 56, 64, 72, 80, 88, 96].map((y) => <rect key={y} x="54" y={y} width={y % 16 ? 54 : 40} height="3.5" rx="1.75" fill="#f3c7a8" />)}
      <g className="ad__float">
        <circle cx="128" cy="96" r="18" fill="#22c55e" />
        <path d="m120 96 6 6 10-12" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}

const ARTS = { laptop: LaptopArt, cap: CapArt, docs: DocsArt };

function AdSlide({ ad, isAdmin, onDelete }) {
  const openTarget = useOpenTarget();
  const Art = ARTS[ad.art];
  // Ichki bannerlar — ilova tilida; admin qo'shgan reklama — admin yozgan matnda
  const tr = (text) => (ad.builtin ? t(text) : text);
  const imageOnly = ad.image && !ad.title;
  const click = () => openTarget(ad.link);
  return (
    <div className={`ad ad--${ad.color || 'purple'} ${imageOnly ? 'ad--image' : ''}`}>
      {imageOnly ? (
        <button className="ad__full" onClick={click} disabled={!ad.link} aria-label={t('Reklama')}>
          <img src={ad.image} alt="" loading="lazy" />
        </button>
      ) : (
        <>
          <div className="ad__text">
            <h3>{tr(ad.title)}</h3>
            {ad.text && <p>{tr(ad.text)}</p>}
            {ad.link && (
              <button className="ad__cta pressable" onClick={click}>
                {ad.button ? tr(ad.button) : t('Batafsil')} <ChevronRight size={16} />
              </button>
            )}
          </div>
          <div className="ad__art">
            {ad.image ? <img className="ad__img" src={ad.image} alt="" loading="lazy" /> : Art ? <Art /> : null}
          </div>
        </>
      )}
      {isAdmin && !ad.builtin && (
        <button className="ad__delete" onClick={() => onDelete(ad)} aria-label={t("Reklamani o'chirish")}>
          <TrashIcon size={16} />
        </button>
      )}
    </div>
  );
}

export function AdCarousel({ ads, isAdmin, onAdd, onChanged }) {
  const { toast } = useApp();
  const slides = useMemo(() => [...ADS_BUILTIN, ...ads], [ads]);
  const track = useRef(null);
  const [index, setIndex] = useState(0);
  const pausedUntil = useRef(0);

  const go = useCallback((i) => {
    const el = track.current;
    if (!el) return;
    const n = slides.length;
    const target = ((i % n) + n) % n;
    el.scrollTo({ left: target * el.clientWidth, behavior: 'smooth' });
  }, [slides.length]);

  // Joriy slaydni aylantirishdan aniqlash (barmoq bilan surilganda ham)
  useEffect(() => {
    const el = track.current;
    if (!el) return undefined;
    const onScroll = () => setIndex(Math.round(el.scrollLeft / Math.max(1, el.clientWidth)));
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  // Avtomatik almashish: 5 soniyada; user tegsa — 8 soniya to'xtaydi
  useEffect(() => {
    if (slides.length < 2) return undefined;
    const timer = setInterval(() => {
      if (Date.now() < pausedUntil.current || document.hidden) return;
      go(index + 1);
    }, 5000);
    return () => clearInterval(timer);
  }, [index, slides.length, go]);

  const hold = () => {
    pausedUntil.current = Date.now() + 8000;
  };

  const remove = async (ad) => {
    hold();
    if (!(await confirmDialog(t("Bu reklamani o'chirasizmi?")))) return;
    try {
      await api(`/news/ads/${ad.id}`, { method: 'DELETE' });
      haptic('success');
      toast(t("Reklama o'chirildi"));
      onChanged();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  return (
    <section className="ads" onPointerDown={hold} onMouseEnter={hold} onMouseMove={hold} aria-roledescription="carousel">
      <div className="ads__track" ref={track}>
        {slides.map((ad) => (
          <AdSlide key={ad.id} ad={ad} isAdmin={isAdmin} onDelete={remove} />
        ))}
      </div>
      {slides.length > 1 && (
        <>
          <button className="ads__arrow ads__arrow--prev" onClick={() => { hold(); go(index - 1); }} aria-label={t('Oldingi')}>
            <ChevronLeft size={18} />
          </button>
          <button className="ads__arrow ads__arrow--next" onClick={() => { hold(); go(index + 1); }} aria-label={t('Keyingi')}>
            <ChevronRight size={18} />
          </button>
          <div className="ads__dots">
            {slides.map((ad, i) => (
              <button key={ad.id} className={`ads__dot ${i === index ? 'ads__dot--on' : ''}`} onClick={() => { hold(); go(i); }}
                aria-label={`${i + 1}-reklama`} />
            ))}
          </div>
        </>
      )}
      {isAdmin && (
        <button className="ads__add pressable" onClick={onAdd} aria-label={t("Reklama qo'shish")}>
          <PlusIcon size={16} /> {t("Reklama")}
        </button>
      )}
    </section>
  );
}

// ===================== Admin formalari =====================
export function ImagePicker({ value, onChange, hint }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const pick = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const blob = await prepareImage(file);
      const result = await apiUpload('/news/media', blob);
      onChange(result);
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };
  return (
    <label className={`news-image ${value ? 'news-image--set' : ''}`}>
      {value ? <img src={value.url} alt="" /> : <ImageIcon size={28} />}
      <span>{busy ? t('Yuklanmoqda…') : value ? t('Rasmni almashtirish') : hint}</span>
      <input type="file" accept="image/*" hidden disabled={busy} onChange={(e) => pick(e.target.files?.[0])} />
      {value && (
        <button type="button" className="news-image__clear" onClick={(e) => { e.preventDefault(); onChange(null); }} aria-label={t('Rasmni olib tashlash')}>
          <CloseIcon size={14} />
        </button>
      )}
    </label>
  );
}

export function LinkPicker({ link, setLink, button, setButton }) {
  const mode = !link ? 'none' : link.startsWith('app:') ? 'app' : 'url';
  return (
    <>
      <span className="field-label">{t('Tugma')}</span>
      <select
        className="field"
        value={mode === 'app' ? link : mode}
        onChange={(e) => {
          const v = e.target.value;
          setLink(v === 'none' ? '' : v === 'url' ? 'https://' : v);
        }}
      >
        <option value="none">{t('Tugmasiz')}</option>
        {APP_TARGETS.map(([key, label]) => <option key={key} value={`app:${key}`}>{t('Ilovada')}: {t(label)}</option>)}
        <option value="url">{t('Tashqi havola (https://…)')}</option>
      </select>
      {mode === 'url' && (
        <input className="field mt-8" value={link} onChange={(e) => setLink(e.target.value)} placeholder={t('https://t.me/kanal yoki sayt')} inputMode="url" />
      )}
      {mode !== 'none' && (
        <input className="field mt-8" value={button} maxLength={30} onChange={(e) => setButton(e.target.value)} placeholder={t('Tugma matni, masalan: Batafsil')} />
      )}
    </>
  );
}

export function StorySheet({ close, onSaved }) {
  const { toast } = useApp();
  const [kind, setKind] = useState('yangilanish');
  const [badge, setBadge] = useState('');
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [points, setPoints] = useState(['', '', '']);
  const [image, setImage] = useState(null);
  const [details, setDetails] = useState('');
  const [detailImage, setDetailImage] = useState(null);
  const [link, setLink] = useState('');
  const [button, setButton] = useState('');
  const [busy, setBusy] = useState(false);

  const setPoint = (i, value) => setPoints((list) => list.map((p, k) => (k === i ? value : p)));

  const save = async () => {
    setBusy(true);
    try {
      await api('/news/stories', {
        method: 'POST',
        body: { kind, badge, title, text, points, image: image?.name, details, detailImage: detailImage?.name, link, button },
      });
      haptic('success');
      toast(t("Yangilik joylandi — hamma foydalanuvchilar ko'radi ✅"));
      onSaved?.();
      close();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title={t("Yangilik qo'shish")} onClose={close}>
      <span className="field-label">{t("Turi")}</span>
      <div className="news-kinds">
        {Object.entries(STORY_KINDS).map(([key, meta]) => (
          <button key={key} className={`news-kind ${kind === key ? 'news-kind--on' : ''}`} onClick={() => setKind(key)}>
            <StoryBubble kind={key} />
            <span>{meta.label}</span>
          </button>
        ))}
      </div>
      <div className="news-group">
        <b>{t("1. Story ekrani")}</b>
        <span className="field-label">{t("Yorliq")}</span>
        <input className="field" value={badge} maxLength={30} onChange={(e) => setBadge(e.target.value)} placeholder={DEFAULT_BADGE[kind]} />
        <span className="field-label">{t("Sarlavha — rangli bo'lishi kerak so'zni *yulduzcha* ichiga oling")}</span>
        <input className="field" value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} placeholder={t("Endi hujjatlaringizni *AI bilan* yarating!")} />
        {title.includes('*') && <div className="news-headline"><Headline text={title} /></div>}
        <span className="field-label">{t("Qisqa matn (ixtiyoriy)")}</span>
        <input className="field" value={text} maxLength={300} onChange={(e) => setText(e.target.value)} placeholder={t("Bir-ikki gap")} />
        <span className="field-label">{t("✓ Bandlar (ixtiyoriy)")}</span>
        {points.map((p, i) => (
          <input key={i} className={`field ${i ? 'mt-8' : ''}`} value={p} maxLength={60} onChange={(e) => setPoint(i, e.target.value)}
            placeholder={['Mavzuga mos tayyor reja', 'Zamonaviy dizayn', 'Tez va sifatli natija'][i]} />
        ))}
        <span className="field-label">{t("Rasm (ixtiyoriy)")}</span>
        <ImagePicker value={image} onChange={setImage} hint={t("Rasm tanlash — bo'lmasa chiroyli illyustratsiya chiqadi")} />
        <p className="card__hint mt-8">{t("Sarlavhasiz faqat rasm yuklasangiz — tayyor afisha sifatida butun ekranda chiqadi.")}</p>
      </div>

      <div className="news-group">
        <b>{t("2. «Batafsil» sahifasi — reklamangiz")}</b>
        <p className="card__hint">{t("User «Batafsil» ni bosganda ochiladi. Bo'sh qoldirsangiz, tugma to'g'ridan-to'g'ri havolaga olib boradi.")}</p>
        <span className="field-label">{t("To'liq matn")}</span>
        <textarea className="field" rows={6} value={details} maxLength={4000} onChange={(e) => setDetails(e.target.value)}
          placeholder={t("Reklama, aksiya shartlari, yangilik tafsilotlari…")} />
        <span className="field-label">{t("Sahifa rasmi (ixtiyoriy)")}</span>
        <ImagePicker value={detailImage} onChange={setDetailImage} hint={t("Rasm tanlash")} />
        <LinkPicker link={link} setLink={setLink} button={button} setButton={setButton} />
      </div>
      <button className="btn btn--primary mt-16" disabled={busy || (!title.trim() && !image)} onClick={save}>
        {busy ? t("Joylanmoqda…") : t("Joylash")}
      </button>
    </Sheet>
  );
}

const AD_COLORS = [
  ['purple', 'Binafsha'], ['blue', "Ko'k"], ['orange', 'Olovrang'], ['green', 'Yashil'], ['pink', 'Pushti'], ['dark', "To'q"],
];

export function AdSheet({ close, onSaved }) {
  const { toast } = useApp();
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [image, setImage] = useState(null);
  const [link, setLink] = useState('');
  const [button, setButton] = useState('');
  const [color, setColor] = useState('purple');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await api('/news/ads', { method: 'POST', body: { title, text, image: image?.name, link, button, color } });
      haptic('success');
      toast(t("Reklama joylandi ✅"));
      onSaved?.();
      close();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const preview = { id: 'preview', title, text, image: image?.url, link: link || (button ? 'app:pres' : ''), button, color };

  return (
    <Sheet title={t("Reklama qo'shish")} onClose={close}>
      <div className="ads ads--preview">
        <div className="ads__track">
          <AdSlide ad={title || image ? preview : { ...preview, title: t('Reklama sarlavhasi') }} isAdmin={false} onDelete={() => {}} />
        </div>
      </div>
      <p className="card__hint mt-8">{t("Faqat rasm yuklasangiz (sarlavhasiz) — rasm bannerni to'liq egallaydi. Eng yaxshi o'lcham: 1200×560.")}</p>
      <span className="field-label">{t("Sarlavha")}</span>
      <input className="field" value={title} maxLength={70} onChange={(e) => setTitle(e.target.value)} placeholder={t("Masalan: 30% chegirma faqat bugun!")} />
      <span className="field-label">{t("Qisqa matn")}</span>
      <input className="field" value={text} maxLength={140} onChange={(e) => setText(e.target.value)} placeholder={t("Ixtiyoriy")} />
      <span className="field-label">{t("Rang")}</span>
      <div className="news-colors">
        {AD_COLORS.map(([key, label]) => (
          <button key={key} className={`news-color ad--${key} ${color === key ? 'news-color--on' : ''}`} onClick={() => setColor(key)} aria-label={label} title={label} />
        ))}
      </div>
      <span className="field-label">{t("Rasm (ixtiyoriy)")}</span>
      <ImagePicker value={image} onChange={setImage} hint={t("Rasm tanlash")} />
      <LinkPicker link={link} setLink={setLink} button={button} setButton={setButton} />
      <button className="btn btn--primary mt-16" disabled={busy || (!title.trim() && !image)} onClick={save}>
        {busy ? t("Joylanmoqda…") : t("Joylash")}
      </button>
    </Sheet>
  );
}

// ===================== Ko'rilganlar holati (Home uchun) =====================
export function useSeenStories() {
  const [seen, setSeen] = useState(readSeen);
  const markSeen = useCallback((id) => {
    setSeen((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      writeSeen(next);
      return next;
    });
  }, []);
  return [seen, markSeen];
}
