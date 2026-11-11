import { useLayoutEffect, useRef, useState } from 'react';

// Slaydni bot yasaydigan PPTX ga (prezentatsiya_bot/presentation/builder.py va styles.py) imkon qadar o'xshatib chizadi.
// O'lchamlar builder.py dagi dyuymlar × 100: slayd 1333 × 750 «virtual piksel», so'ng ekranga moslab kichraytiriladi.
// Shrift: punkt × 100 / 72 (34 pt → 47 px)
const W = 1333;
const H = 750;
const MARGIN = 80;
const IMG_X = 800;
const COVER_IMG_X = 770;
const INK = '#141414';
const pt = (size) => (size * 100) / 72;

const LABELS = {
  uz: { badge: 'TAQDIMOT', plan: 'Reja', contents: 'Mundarija', conclusion: 'Xulosa', thanks: "E'tiboringiz uchun rahmat!", author: 'Muallif' },
  ru: { badge: 'ПРЕЗЕНТАЦИЯ', plan: 'План', contents: 'Содержание', conclusion: 'Заключение', thanks: 'Спасибо за внимание!', author: 'Автор' },
  en: { badge: 'PRESENTATION', plan: 'Outline', contents: 'Contents', conclusion: 'Conclusion', thanks: 'Thank you for your attention!', author: 'Author' },
};

const SANS = "'Segoe UI', 'Nunito', system-ui, sans-serif";
const SERIF = "Georgia, 'Times New Roman', serif";
const FONTS = {
  title: "'Segoe UI Black', 'Nunito', system-ui, sans-serif",
  heading: "'Segoe UI Semibold', 'Nunito', system-ui, sans-serif",
  body: SANS,
  quote: SERIF,
};

function rgba(hex, alpha = 1) {
  const n = parseInt(hex, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

// Yirtiq qog'oz qirrasi (Tarix shabloni)
const TORN = 'polygon(0% 3%, 6% 0%, 13% 2%, 21% 0%, 30% 3%, 38% 0%, 47% 2%, 56% 0%, 64% 3%, 73% 0%, 81% 2%, 90% 0%, 100% 3%, 98% 15%, 100% 30%, 98% 46%, 100% 62%, 98% 78%, 100% 97%, 91% 100%, 82% 97%, 73% 100%, 63% 98%, 54% 100%, 45% 97%, 35% 100%, 26% 98%, 17% 100%, 8% 97%, 0% 100%, 2% 82%, 0% 66%, 2% 50%, 0% 34%, 2% 18%)';

// ===== Tabiat shablonlari: o'lchamlar, shriftlar va bezaklar (bot: styles.py → NatureDeck, art.leaf) =====
const NATURE_BOXES = {
  panel: [795, 45, 493, 660], circle: [805, 130, 470, 470], framed: [805, 80, 450, 590], rounded: [810, 80, 445, 590],
  arch: [820, 75, 430, 600], gold: [805, 85, 450, 580], plain: [790, 60, 490, 630],
  slant: [780, 60, 500, 630], snip: [805, 80, 460, 590],
};
const SPORT = ['slash', 'corner', 'cross', 'arc', 'shard', 'glow', 'line'];

/** Biznes bezagi: o'ng yuqori burchakda diagonal bloklar (bot: NatureDeck.shards). */
function Shards({ t, scale = 1 }) {
  const blocks = [[0, 220, t.accent2, 0.9], [95, 160, t.accent, 1], [185, 110, t.accent2, 0.55]];
  return blocks.map(([dx, w, color, a]) => (
    <div key={dx} style={{ position: 'absolute', left: W - 330 * scale + dx * scale, top: -20, width: w * scale, height: 150 * scale, background: rgba(color, a), clipPath: 'polygon(50% 0, 100% 0, 50% 100%, 0 100%)' }} />
  ));
}
const CLIP = {
  slant: 'polygon(20% 0, 100% 0, 80% 100%, 0 100%)',
  snip: 'polygon(16% 0, 84% 0, 100% 12%, 100% 88%, 84% 100%, 16% 100%, 0 88%, 0 12%)',
};

/** /// — qiya qalin chiziqlar (sport). */
function Slashes({ x, y, color }) {
  return [0, 1, 2].map((i) => (
    <div key={i} style={{ position: 'absolute', left: x + i * 26, top: y, width: 32, height: 36, background: `#${color}`, clipPath: 'polygon(55% 0, 100% 0, 45% 100%, 0 100%)' }} />
  ));
}

function Plus({ x, y, size, color }) {
  return (
    <svg viewBox="0 0 10 10" aria-hidden="true" style={{ position: 'absolute', left: x, top: y, width: size, height: size }}>
      <path d="M3.8 0h2.4v3.8H10v2.4H6.2V10H3.8V6.2H0V3.8h3.8z" fill={`#${color}`} />
    </svg>
  );
}

function Ring({ x, y, d, color }) {
  return <div style={{ position: 'absolute', left: x, top: y, width: d, height: d, borderRadius: '50%', border: `${d * 0.13}px solid #${color}`, boxSizing: 'border-box' }} />;
}

/** Sport bezaklari (kontent slaydlari va muqova uchun). */
function SportDecor({ L, t, free, cover, areaW }) {
  const decor = L.look.decor;
  if (decor === 'shard') return cover ? <Shards t={t} /> : free ? <Shards t={t} scale={0.75} /> : null;
  if (decor === 'glow') {
    const left = cover ? -260 : free ? W - 400 : -260;
    const top = cover ? H - 260 : -260;
    return <div style={{ position: 'absolute', left, top, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${rgba(t.accent, 0.5)}, transparent 65%)` }} />;
  }
  if (decor === 'slash') {
    return (
      <>
        {L.look.glow && <div style={{ position: 'absolute', left: cover ? -260 : free ? W - 420 : -240, top: cover ? H - 260 : -260, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${rgba(t.accent, 0.5)}, transparent 65%)` }} />}
        <Slashes x={cover || free ? W - 175 : MARGIN + areaW - 95} y={cover ? 50 : 42} color={t.accent} />
      </>
    );
  }
  if (decor === 'corner') {
    return (
      <>
        <div style={{ position: 'absolute', left: 0, top: H - 115, width: 115, height: 115, background: `#${t.accent}`, clipPath: 'polygon(0 0, 0 100%, 100% 100%)' }} />
        {free && !cover && <div style={{ position: 'absolute', left: W - 160, top: 0, width: 160, height: 160, background: `#${t.accent}`, clipPath: 'polygon(0 0, 100% 0, 100% 100%)' }} />}
      </>
    );
  }
  if (decor === 'cross') {
    return (
      <>
        <Rect x={0} y={0} w={9} h={H} color={t.accent} />
        {(free || cover) && <Plus x={W - 130} y={50} size={32} color={t.accent} />}
        {free && !cover && <Plus x={W - 75} y={110} size={20} color={t.accent} />}
      </>
    );
  }
  if (decor === 'arc') {
    return (
      <>
        <Ring x={W - (cover ? 160 : 130)} y={cover ? -160 : -130} d={cover ? 320 : 260} color={t.accent} />
        {free && !cover && <Ring x={-90} y={H - 90} d={180} color={t.accent} />}
      </>
    );
  }
  return null;
}
const FADE_X = 640; // media "fade": rasm shu nuqtadan o'ngda (bot: NatureDeck.FADE_X = 6.4)
const TONE = { sepia: 'sepia(0.85) contrast(1.05) brightness(0.97)', mono: 'grayscale(1) contrast(1.08)' };
const ORNATE = ['ornament', 'stars', 'frame'];

/** Bezakli chiziq: ingichka chiziq va o'rtasida romb. */
function Ornament({ x, y, w, color }) {
  return (
    <>
      <Rect x={x} y={y} w={w} h={1.5} color={color} />
      <Diamond x={x + w / 2 - 7} y={y - 6} d={14} color={color} />
    </>
  );
}

function Star4({ x, y, size, color }) {
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true" style={{ position: 'absolute', left: x, top: y, width: size, height: size }}>
      <path d="M50 0 L62 38 L100 50 L62 62 L50 100 L38 62 L0 50 L38 38 Z" fill={`#${color}`} />
    </svg>
  );
}

function Stars({ x, y, color, n = 3, size = 16 }) {
  return Array.from({ length: n }, (_, i) => <Star4 key={i} x={x + i * (size + 10)} y={y} size={size} color={color} />);
}

function PalaceFrame({ t }) {
  return (
    <>
      <Rect x={22} y={22} w={W - 44} h={H - 44} style={{ border: `1.5px solid #${t.accent}`, boxSizing: 'border-box' }} />
      <Rect x={32} y={32} w={W - 64} h={H - 64} style={{ border: `0.75px solid #${t.accent2}`, boxSizing: 'border-box' }} />
      {[[22, 22], [W - 22, 22], [22, H - 22], [W - 22, H - 22]].map(([cx, cy]) => <Diamond key={`${cx}-${cy}`} x={cx - 10} y={cy - 10} d={20} color={t.accent} />)}
    </>
  );
}

function fontOf(name, fallback) {
  if (!name) return fallback;
  if (name === 'Georgia') return SERIF;
  if (name === 'Arial Black') return "'Arial Black', 'Nunito', system-ui, sans-serif";
  if (name === 'Segoe UI Black') return FONTS.title;
  if (name === 'Segoe UI Semibold') return FONTS.heading;
  return SANS;
}

/** Barg (tomirlari bilan). angle — bot art.leaf dagi kabi soat strelkasiga qarshi gradus. */
function Leaf({ x, y, size, color, alpha = 1, angle = 0, veins = true }) {
  const vein = parseInt(color.slice(0, 2), 16) + parseInt(color.slice(2, 4), 16) + parseInt(color.slice(4, 6), 16) < 600
    ? `rgba(255,255,255,${0.28 * alpha})` : `rgba(0,0,0,${0.18 * alpha})`;
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true"
      style={{ position: 'absolute', left: x, top: y, width: size, height: size, transform: `rotate(${-angle}deg)`, overflow: 'visible' }}>
      <path d="M50 11 C80 30 80 64 50 86 C20 64 20 30 50 11 Z" fill={rgba(color, alpha)} />
      <path d="M50 86 L50 95" stroke={rgba(color, alpha)} strokeWidth="2" strokeLinecap="round" />
      {veins && (
        <g stroke={vein} strokeWidth="1.2" strokeLinecap="round" fill="none">
          <path d="M50 86 L50 18" />
          {[72, 62, 52, 42, 32].map((vy, i) => (
            <path key={vy} d={`M50 ${vy} L${36 + i * 1.5} ${vy - 9} M50 ${vy} L${64 - i * 1.5} ${vy - 9}`} />
          ))}
        </g>
      )}
    </svg>
  );
}

/** Ko'p qirrali quyosh (PowerPoint STAR_24_POINT ga o'xshash). */
function Sun({ x, y, size, color, rotate = 0, points = 24 }) {
  const pts = Array.from({ length: points * 2 }, (_, i) => {
    const r = i % 2 === 0 ? 50 : 38;
    const a = (Math.PI * i) / points;
    return `${50 + r * Math.cos(a)},${50 + r * Math.sin(a)}`;
  }).join(' ');
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true" style={{ position: 'absolute', left: x, top: y, width: size, height: size, transform: `rotate(${rotate}deg)` }}>
      <polygon points={pts} fill={`#${color}`} />
    </svg>
  );
}

function Peak({ x, w, h, color, alpha }) {
  return <div style={{ position: 'absolute', left: x, top: H - h, width: w, height: h, background: rgba(color, alpha), clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />;
}

/** Tabiat shabloni: kartadagi belgi / xulosa nuqtasi (barg, yulduzcha yoki chiziq). */
function NatureMark({ L, t, i, x, y, h }) {
  const color = L.alt(i);
  if (L.look.decor === 'leaf' || L.look.decor === 'leaves') return <Leaf x={x + 6} y={y + h / 2 - 13} size={26} color={color} angle={-35} veins={false} />;
  if (L.look.decor === 'sun') return <Sun x={x + 10} y={y + h / 2 - 10} size={20} color={color} points={12} />;
  if (L.look.decor === 'ornament' || L.look.decor === 'frame') return <Diamond x={x + 11} y={y + h / 2 - 7} d={14} color={t.accent} />;
  if (L.look.decor === 'stars') return <Star4 x={x + 9} y={y + h / 2 - 9} size={18} color={t.accent} />;
  return <Rect x={x} y={y + 12} w={8} h={h - 24} color={color} radius={4} />;
}

/** Shablon ko'rinishi: shriftlar, karta va rasm uslubi (bot styles.py dagi klasslarga mos). */
function lookOf(t) {
  const style = t.style ?? 'classic';
  const ink = `#${t.card_text ?? t.text}`;
  const inkMuted = `#${t.card_muted ?? t.muted}`;
  const onAccent = `#${t.on_accent ?? (t.dark ? t.bg : 'FFFFFF')}`;
  const alt = (i) => (i % 2 ? t.accent2 : t.accent);
  const base = { style, ink, inkMuted, onAccent, alt, fonts: FONTS, imgBox: null, textW: IMG_X - 50 - MARGIN };

  if (style === 'corporate') {
    return {
      ...base,
      imgBox: [825, 75, 435, 600],
      textW: 700,
      card: (i, radius) => ({ borderRadius: Math.min(radius, 12), background: '#fff', border: `1.5px solid ${i % 2 ? '#C9E8D5' : `#${t.accent}`}` }),
    };
  }
  if (style === 'doodle') {
    return {
      ...base,
      fonts: { ...FONTS, title: "'Arial Black', 'Nunito', system-ui, sans-serif" },
      imgBox: [840, 115, 420, 520],
      textW: 710,
      card: (i) => ({ borderRadius: 0, background: '#fff', border: `2px solid ${INK}`, boxShadow: `8px 8px 0 #${alt(i)}`, overflow: 'visible' }),
    };
  }
  if (style === 'vintage') {
    return {
      ...base,
      fonts: { title: SERIF, heading: SERIF, body: SERIF, quote: SERIF },
      imgBox: [815, 85, 445, 560],
      textW: 690,
      card: () => ({ borderRadius: 0, background: `radial-gradient(ellipse at 50% 50%, #${t.card} 60%, #c9b28c 100%)`, clipPath: TORN }),
    };
  }
  if (style === 'baroque') {
    return {
      ...base,
      fonts: { title: SERIF, heading: SERIF, body: SANS, quote: SERIF },
      textW: 650,
      card: (i, radius) => ({ borderRadius: Math.min(radius, 5), background: rgba(t.card, 0.62), border: `1px solid #${alt(i)}` }),
    };
  }
  if (['nature', 'heritage', 'sport', 'office', 'edu', 'tech', 'art', 'med', 'law'].includes(style)) {
    // Ko'rinishi sozlanadigan shablonlar (bot: styles.py → NatureDeck; tabiat — nature, tarix — heritage).
    // look — media, decor, card, upper, italic, tone, texture, tag, cover, band, title_color
    const look = t.look ?? {};
    const media = look.media ?? 'panel';
    const box = NATURE_BOXES[media] ?? null;
    const f = t.fonts ?? {};
    const card = look.card ?? 'solid';
    return {
      ...base,
      style: 'nature',
      look,
      media,
      tone: TONE[look.tone] ?? 'none',
      italic: look.italic ? 'italic ' : '',
      fonts: { title: fontOf(f.title, FONTS.title), heading: fontOf(f.heading, FONTS.heading), body: fontOf(f.body, SANS), quote: fontOf(f.quote, SERIF) },
      imgBox: box,
      textW: box ? box[0] - 50 - MARGIN : media === 'fade' ? FADE_X - 40 - MARGIN : 640,
      card: (i, radius) => {
        const r = Math.min(radius, 12);
        if (card === 'outline') return { borderRadius: r, background: `#${t.card}`, border: `1.5px solid #${alt(i)}`, boxSizing: 'border-box' };
        if (card === 'glass') return { borderRadius: r, background: rgba(t.card, 0.72), border: `1px solid #${t.accent2}`, boxSizing: 'border-box' };
        if (card === 'frame') return { borderRadius: 0, background: rgba(t.card, 0.45), border: `1px solid #${t.accent}`, boxSizing: 'border-box' };
        return { borderRadius: r, background: `#${t.card}` };
      },
    };
  }
  return { ...base, card: (i, radius, alpha = 0.85) => ({ borderRadius: radius, background: rgba(t.card, alpha) }) };
}

/** Joylashtirilgan blok. clip — sig'magan matn kesiladi (PPTX da shrift kichrayadi). */
function Box({ x, y, w, h, style, children, center, align = 'left' }) {
  return (
    <div
      style={{
        position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden',
        display: 'flex', flexDirection: 'column', justifyContent: center ? 'center' : 'flex-start',
        textAlign: align, ...style,
      }}
    >
      {children}
    </div>
  );
}

function Circle({ x, y, d, color, alpha = 1, style }) {
  return <div style={{ position: 'absolute', left: x, top: y, width: d, height: d, borderRadius: '50%', background: rgba(color, alpha), ...style }} />;
}

function Rect({ x, y, w, h, color, alpha = 1, radius = 0, style }) {
  return <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, borderRadius: radius, background: color ? rgba(color, alpha) : 'transparent', ...style }} />;
}

function Diamond({ x, y, d, color }) {
  return <div style={{ position: 'absolute', left: x, top: y, width: d, height: d, background: `#${color}`, transform: 'rotate(45deg)' }} />;
}

/** Kartaning chap chetidagi belgi (klassik — rangli chiziq, shablonlarda — nuqta yoki romb). */
function Stripe({ L, t, i, h }) {
  if (L.style === 'corporate') return <Circle x={12} y={h / 2 - 7} d={14} color={t.accent} />;
  if (L.style === 'doodle') return <Circle x={12} y={h / 2 - 8} d={16} color={L.alt(i)} style={{ border: `1px solid ${INK}` }} />;
  if (L.style === 'vintage') return <Diamond x={13} y={h / 2 - 7} d={14} color={t.accent2} />;
  if (L.style === 'baroque') return <Diamond x={13} y={h / 2 - 6} d={12} color={t.accent} />;
  if (L.style === 'nature') return <NatureMark L={L} t={t} i={i} x={0} y={0} h={h} />;
  return <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 10, borderRadius: 5, background: `#${L.alt(i)}` }} />;
}

function VideoBlock({ x, y, w, h, t }) {
  const vw = w - 50;
  return (
    <>
      <Rect x={x} y={y} w={w} h={h} color={t.card} />
      <div
        style={{
          position: 'absolute', left: x + 25, top: y + (h - (vw * 9) / 16) / 2, width: vw, height: (vw * 9) / 16,
          background: `linear-gradient(90deg, #${t.accent}, #${t.accent2})`, display: 'grid', placeItems: 'center',
        }}
      >
        <div style={{ width: vw / 4, height: vw / 4, borderRadius: '50%', background: '#fff', display: 'grid', placeItems: 'center' }}>
          <div style={{ marginLeft: vw / 40, borderStyle: 'solid', borderWidth: `${vw / 16}px 0 ${vw / 16}px ${vw / 10}px`, borderColor: `transparent transparent transparent #${t.accent}` }} />
        </div>
      </div>
    </>
  );
}

const imgStyle = (x, y, w, h, extra) => ({ position: 'absolute', left: x, top: y, width: w, height: h, objectFit: 'cover', ...extra });

/** Kontent slaydidagi rasm yoki video — shablon uslubida. */
function Media({ L, t, image, video, index }) {
  if (L.style === 'nature') {
    if (L.media === 'full' || L.media === 'fade') {
      if (video) return <VideoBlock x={760} y={75} w={500} h={600} t={t} />;
      if (L.media === 'fade') {
        return (
          <>
            <img src={image} alt="" style={imgStyle(FADE_X, 0, W - FADE_X, H, { filter: L.tone })} />
            <div style={{ position: 'absolute', left: FADE_X - 2, top: 0, width: 300, height: H, background: `linear-gradient(90deg, #${t.bg}, ${rgba(t.bg, 0.55)} 30%, ${rgba(t.bg, 0.12)} 65%, transparent)` }} />
          </>
        );
      }
      return (
        <>
          <img src={image} alt="" style={imgStyle(0, 0, W, H, { filter: L.tone })} />
          <Fade t={t} share={0.62} />
        </>
      );
    }
    const [x, y, w, h] = L.imgBox;
    const radius = { panel: Math.min(w, h) * 0.06, rounded: Math.min(w, h) * 0.07, circle: '50%', arch: `${w / 2}px ${w / 2}px 0 0` }[L.media] ?? 0;
    const border = { rounded: `4px solid #${t.accent}`, arch: `1.5px solid #${t.accent}`, gold: `2px solid #${t.accent}` }[L.media];
    return (
      <>
        {L.media === 'circle' && (L.look.no_sun ? (
          <Circle x={x - 18} y={y - 18} d={w + 36} color="000000" alpha={0} style={{ border: `3px solid #${t.accent}`, boxSizing: 'border-box' }} />
        ) : (
          <>
            <Sun x={x - 55} y={y - 65} size={230} color={t.accent} rotate={8} />
            <Circle x={x + 22} y={y + 22} d={w} color="000000" alpha={0} style={{ border: `2.5px solid #${t.accent}`, boxSizing: 'border-box' }} />
          </>
        ))}
        {L.media === 'framed' && <Rect x={x - 25} y={y + 25} w={w} h={h} color={t.accent} alpha={0.85} />}
        {L.media === 'gold' && <Rect x={x - 15} y={y - 15} w={w + 30} h={h + 30} style={{ border: `1px solid #${t.accent}`, boxSizing: 'border-box' }} />}
        {L.media === 'snip' && <div style={{ position: 'absolute', left: x - 2, top: y - 2, width: w + 4, height: h + 4, background: `#${t.accent}`, clipPath: CLIP.snip }} />}
        {video ? <VideoBlock x={x} y={y} w={w} h={h} t={t} /> : (
          <img src={image} alt="" style={imgStyle(x, y, w, h, {
            borderRadius: radius, filter: L.tone, clipPath: CLIP[L.media] ?? 'none',
            ...(border ? { border, boxSizing: 'border-box' } : {}),
          })} />
        )}
      </>
    );
  }
  if (L.style === 'baroque') {
    if (video) return <VideoBlock x={760} y={75} w={500} h={600} t={t} />;
    return (
      <>
        <img src={image} alt="" style={imgStyle(0, 0, W, H)} />
        <Fade t={t} share={0.62} />
      </>
    );
  }
  if (L.imgBox) {
    const [x, y, w, h] = L.imgBox;
    if (L.style === 'corporate') {
      return (
        <>
          <Rect x={x + 25} y={y + 25} w={w} h={h} color={t.accent} alpha={0.18} radius={34} />
          {video ? <VideoBlock x={x} y={y} w={w} h={h} t={t} /> : <img src={image} alt="" style={imgStyle(x, y, w, h, { borderRadius: 34 })} />}
        </>
      );
    }
    if (L.style === 'doodle') {
      return (
        <>
          <Rect x={x + 12} y={y + 12} w={w} h={h} color={L.alt(index)} />
          {video ? <VideoBlock x={x} y={y} w={w} h={h} t={t} /> : <img src={image} alt="" style={imgStyle(x, y, w, h, { border: `3px solid ${INK}`, boxSizing: 'border-box' })} />}
          {Array.from({ length: 7 }, (_, i) => (
            <Rect key={i} x={x + 30 + (i * (w - 60)) / 6 - 5} y={y - 22} w={10} h={42} color="141414" radius={5} />
          ))}
        </>
      );
    }
    // vintage — eski foto: sepiya, krem hoshiya, biroz qiyshiq
    if (video) return <VideoBlock x={x} y={y} w={w} h={h} t={t} />;
    return (
      <div style={{ position: 'absolute', left: x + 12, top: y + 12, width: w - 24, height: h - 24, padding: 16, background: '#F0E4CC', boxShadow: '6px 10px 16px rgba(0,0,0,0.6)', transform: `rotate(${index % 2 ? 2 : -2}deg)`, boxSizing: 'border-box' }}>
        <img src={image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'sepia(0.9) contrast(1.05)', display: 'block' }} />
      </div>
    );
  }
  if (video) return <VideoBlock x={IMG_X} y={0} w={W - IMG_X} h={H} t={t} />;
  return (
    <>
      <img src={image} alt="" style={imgStyle(IMG_X, 0, W - IMG_X, H)} />
      <Rect x={IMG_X} y={0} w={8} h={H} color={t.accent} />
    </>
  );
}

function Fade({ t, share, color }) {
  const c = color ?? t.bg;
  const solid = share * 55;
  const end = share * 125;
  return <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(90deg, ${rgba(c, 0.93)} ${solid}%, ${rgba(c, 0.5)} ${(solid + end) / 2}%, transparent ${end}%)` }} />;
}

// ===== Doodle bezaklari =====
const DOODLES = {
  sparkle: <path d="M20 2 C21 15 25 19 38 20 C25 21 21 25 20 38 C19 25 15 21 2 20 C15 19 19 15 20 2 Z" fill="none" stroke={INK} strokeWidth="1.6" strokeLinejoin="round" />,
  spiral: <path d="M20 20 m0 -2 a2 2 0 1 1 -2 2 a4 4 0 1 1 4 4 a6 6 0 1 1 -6 -6 a8 8 0 1 1 8 8 a10 10 0 1 1 -10 -10 a12 12 0 1 1 12 12" fill="none" stroke={INK} strokeWidth="1.5" strokeLinecap="round" />,
  star: <path d="M20 3 L24 15 L37 15 L27 23 L31 36 L20 28 L9 36 L13 23 L3 15 L16 15 Z" fill={INK} />,
  squiggle: <path d="M2 22 C8 14 12 14 16 21 S24 28 30 21 S40 14 44 21" fill="none" stroke={INK} strokeWidth="1.5" strokeLinecap="round" />,
};
const DOODLE_KINDS = ['sparkle', 'squiggle', 'spiral', 'star'];

function Doodle({ kind, x, y, size }) {
  return (
    <svg viewBox="0 0 40 40" style={{ position: 'absolute', left: x, top: y, width: size, height: size }} aria-hidden="true">
      {DOODLES[kind]}
    </svg>
  );
}

// ===== Umumiy qismlar =====
function Footer({ L, t, index, total, title, right, color, left = MARGIN }) {
  return (
    <>
      <Box x={right - 160} y={H - 55} w={160} h={30} align="right"
        style={{ font: `600 ${pt(11)}px ${L.fonts.heading}`, color: color ?? `#${t.muted}` }}>
        {String(index).padStart(2, '0')} / {String(total).padStart(2, '0')}
      </Box>
      <Box x={left} y={H - 55} w={right - left - 200} h={30}
        style={{ font: `${pt(11)}px ${L.fonts.body}`, color: color ?? `#${t.muted}`, whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
        {title}
      </Box>
    </>
  );
}

function Frame({ L, t }) {
  if (L.style === 'corporate') return <Rect x={22} y={22} w={W - 44} h={H - 44} radius={22} style={{ border: '1px solid #D2CFEC' }} />;
  if (L.style === 'vintage') {
    return (
      <>
        <Rect x={25} y={25} w={W - 50} h={H - 50} style={{ border: `1px solid #${t.accent}` }} />
        <Rect x={33} y={33} w={W - 66} h={H - 66} style={{ border: `1px solid #${t.accent2}` }} />
      </>
    );
  }
  if (L.style === 'baroque') return <Rect x={30} y={30} w={W - 60} h={H - 60} style={{ border: `1px solid #${t.accent}` }} />;
  return null;
}

function CornerBadge({ t }) {
  return (
    <div style={{ position: 'absolute', left: W - 95, top: 42, width: 48, height: 48, borderRadius: '50%', border: `1.5px solid #${t.accent}`, display: 'grid', placeItems: 'center', color: `#${t.accent}`, font: `600 ${pt(16)}px ${SANS}` }}>
      ↗
    </div>
  );
}

function Decorations({ L, t, index, total, title, hasMedia }) {
  const right = hasMedia ? MARGIN + (L.imgBox || L.style === 'baroque' || L.style === 'nature' ? L.textW : IMG_X - 50 - MARGIN) + 10 : W - MARGIN;
  if (L.style === 'nature') {
    const decor = L.look.decor;
    const areaW = hasMedia ? L.textW : W - 2 * MARGIN;
    return (
      <>
        {decor === 'leaf' && (
          <>
            <Rect x={0} y={0} w={W} h={9} color={t.accent} />
            <Leaf x={hasMedia ? MARGIN + areaW - 30 : W - 95} y={30} size={50} color={t.accent} angle={-35} />
          </>
        )}
        {decor === 'sun' && !hasMedia && <Sun x={W - 125} y={-105} size={230} color={t.accent} rotate={12} />}
        {decor === 'gold' && <Rect x={MARGIN} y={38} w={90} h={2.5} color={t.accent} />}
        {decor === 'peak' && !hasMedia && (
          <>
            <Peak x={W - 620} w={500} h={240} color={t.accent} alpha={0.07} />
            <Peak x={W - 400} w={460} h={310} color={t.accent} alpha={0.1} />
            <Peak x={W - 220} w={340} h={190} color={t.accent} alpha={0.08} />
          </>
        )}
        {decor === 'leaves' && (hasMedia ? (
          <Leaf x={-100} y={H - 170} size={260} color={t.accent2} alpha={0.18} angle={-140} veins={false} />
        ) : (
          <>
            <Leaf x={W - 260} y={-90} size={340} color={t.accent2} alpha={0.22} angle={35} />
            <Leaf x={-120} y={H - 200} size={300} color={t.accent} alpha={0.16} angle={-140} />
          </>
        ))}
        {decor === 'ornament' && (
          <>
            <Ornament x={MARGIN} y={36} w={areaW} color={t.accent} />
            <Rect x={MARGIN} y={H - 72} w={areaW} h={1.2} color={t.accent} />
          </>
        )}
        {decor === 'stars' && (
          <>
            <Stars x={MARGIN} y={30} color={t.accent} />
            {!hasMedia && <Stars x={W - MARGIN - 62} y={30} color={t.accent} />}
          </>
        )}
        {decor === 'frame' && <PalaceFrame t={t} />}
        <SportDecor L={L} t={t} free={!hasMedia} areaW={areaW} />
        <Footer L={L} t={t} index={index} total={total} title={title} right={right} left={decor === 'corner' || decor === 'arc' ? 135 : undefined} />
      </>
    );
  }
  if (L.style === 'corporate') {
    return (
      <>
        {!hasMedia && <CornerBadge t={t} />}
        <Footer L={L} t={t} index={index} total={total} title={title} right={right} />
      </>
    );
  }
  if (L.style === 'doodle') {
    const a = DOODLE_KINDS[index % DOODLE_KINDS.length];
    const b = DOODLE_KINDS[(index + 2) % DOODLE_KINDS.length];
    return (
      <>
        {hasMedia ? <Doodle kind={a} x={755} y={635} size={75} /> : (
          <>
            <Doodle kind={a} x={W - 135} y={35} size={85} />
            <Doodle kind={b} x={W - 240} y={H - 115} size={100} />
          </>
        )}
        <div style={{ position: 'absolute', left: MARGIN - 10, top: H - 72, width: 50, height: 50, borderRadius: '50%', background: '#fff', border: `1.5px solid ${INK}`, display: 'grid', placeItems: 'center', font: `900 ${pt(11)}px ${L.fonts.title}`, color: INK }}>
          {String(index).padStart(2, '0')}
        </div>
      </>
    );
  }
  if (L.style === 'vintage' || L.style === 'baroque') {
    return (
      <>
        <Frame L={L} t={t} />
        <Footer L={L} t={t} index={index} total={total} title={title} right={right} />
      </>
    );
  }
  const flip = index % 2 === 0;
  const cx = flip ? -160 : W - 260;
  return (
    <>
      {hasMedia ? (
        <Circle x={-120} y={H - 160} d={260} color={t.accent2} alpha={0.08} />
      ) : (
        <>
          <Circle x={cx} y={-180} d={420} color={t.accent} alpha={0.1} />
          <Circle x={cx + (flip ? 190 : -90)} y={-60} d={160} color={t.accent2} alpha={0.14} />
          <Circle x={flip ? W - 140 : -60} y={H - 120} d={200} color={t.accent2} alpha={0.08} />
        </>
      )}
      <Rect x={0} y={H - 8} w={W} h={8} color={t.muted} alpha={0.18} />
      <Rect x={0} y={H - 8} w={(W * index) / total} h={8} color={t.accent} />
      <Footer L={L} t={t} index={index} total={total} title={title} right={right} />
    </>
  );
}

const titleSize = (title, big, small) => pt(title.length > 45 ? small : big);

/** Lenta-sarlavha (Daftar): rangli to'rtburchak, qora kontur va soya. */
function Banner({ x, y, text, color, maxW, size, h = 95, fonts }) {
  const w = Math.min(maxW, 80 + text.length * size * 0.95);
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, background: `#${color}`, border: `3px solid ${INK}`, boxShadow: `9px 9px 0 ${INK}`, boxSizing: 'border-box', display: 'grid', placeItems: 'center', padding: '0 20px', overflow: 'hidden', textAlign: 'center', font: `900 ${pt(text.length > 30 ? size * 0.7 : size)}px/1.1 ${fonts.title}`, color: INK }}>
      {text}
    </div>
  );
}

function Heading({ L, t, title, tag, areaW, hasMedia }) {
  const parts = [];
  const cut = (value, n) => (value.length <= n ? value : `${value.slice(0, n - 1)}…`);
  if (L.style === 'nature') {
    let y = 60;
    if (tag) {
      const label = cut(tag, 60);
      if (L.look.tag === 'block') {
        const width = Math.min(areaW, 50 + label.length * 8.5);
        parts.push(
          <Rect key="tag" x={MARGIN} y={y} w={width} h={36} color={t.accent} />,
          <Box key="tagtext" x={MARGIN + 18} y={y + 6} w={width - 30} h={26} style={{ font: `700 ${pt(10.5)}px ${L.fonts.heading}`, color: L.onAccent, whiteSpace: 'nowrap', textTransform: 'uppercase' }}>{label}</Box>,
        );
      } else if (L.look.decor === 'leaves' || L.look.tag === 'pill') {
        const width = Math.min(areaW, 50 + label.length * 8);
        parts.push(
          <Rect key="tag" x={MARGIN} y={y} w={width} h={38} color={t.accent} radius={19} />,
          <Box key="tagtext" x={MARGIN + 20} y={y + 7} w={width - 30} h={26} style={{ font: `700 ${pt(11)}px ${L.fonts.heading}`, color: L.onAccent, whiteSpace: 'nowrap' }}>{label}</Box>,
        );
      } else {
        parts.push(
          <Rect key="tagline" x={MARGIN} y={y + 14} w={35} h={3} color={t.accent} />,
          <Box key="tagtext" x={MARGIN + 50} y={y} w={areaW - 50} h={30} style={{ font: `700 ${pt(10.5)}px ${L.fonts.heading}`, color: `#${t.accent}`, letterSpacing: '0.15em', whiteSpace: 'nowrap' }}>{label.toUpperCase()}</Box>,
        );
      }
      y += 50;
    }
    const upper = L.look.upper;
    parts.push(
      <Box key="title" x={MARGIN} y={y} w={hasMedia ? areaW : areaW - 90} h={100} center
        style={{ font: `${L.italic}${L.look.light_title ? 300 : upper || L.fonts.title === SERIF ? 400 : 900} ${titleSize(title, upper ? 31 : 36, 26)}px/1.1 ${L.fonts.title}`, color: `#${L.look.title_color === 'accent' ? t.accent : t.text}`, textTransform: upper ? 'uppercase' : 'none' }}>
        {title}
      </Box>,
      ORNATE.includes(L.look.decor)
        ? <Ornament key="bar" x={MARGIN} y={y + 110} w={140} color={t.accent} />
        : SPORT.includes(L.look.decor)
          ? <Rect key="bar" x={MARGIN} y={y + 107} w={100} h={10} color={t.accent} />
          : <Rect key="bar" x={MARGIN} y={y + 108} w={90} h={7} color={t.accent} radius={4} />,
    );
    return [parts, y + 138];
  }
  if (L.style === 'corporate') {
    let y = 60;
    if (tag) {
      const label = cut(tag, 60);
      const width = Math.min(areaW, 45 + label.length * 7.5);
      parts.push(
        <Rect key="tag" x={MARGIN} y={y} w={width} h={36} radius={18} style={{ border: `1px solid #${t.accent}` }} />,
        <Box key="tagtext" x={MARGIN + 18} y={y + 6} w={width - 30} h={26} style={{ font: `700 ${pt(11)}px ${L.fonts.heading}`, color: `#${t.accent}`, whiteSpace: 'nowrap' }}>{label}</Box>,
      );
      y += 55;
    }
    parts.push(
      <Box key="title" x={MARGIN} y={y} w={hasMedia ? areaW : areaW - 90} h={105} center
        style={{ font: `900 ${titleSize(title, 38, 28)}px/1.1 ${L.fonts.title}`, color: `#${t.accent}` }}>{title}</Box>,
    );
    return [parts, y + 130];
  }
  if (L.style === 'doodle') {
    let y = 50;
    if (tag) {
      const label = cut(tag, 55);
      const width = Math.min(areaW, 50 + label.length * 8.5);
      parts.push(
        <div key="tag" style={{ position: 'absolute', left: MARGIN, top: y, width, height: 38, borderRadius: 19, background: `#${t.accent2}`, border: `1.5px solid ${INK}`, boxShadow: `5px 5px 0 ${INK}`, boxSizing: 'border-box', padding: '6px 18px', font: `700 ${pt(11)}px ${L.fonts.heading}`, color: INK, whiteSpace: 'nowrap', overflow: 'hidden' }}>{label}</div>,
      );
      y += 62;
    }
    parts.push(<Banner key="title" x={MARGIN} y={y} text={title} color={t.accent} maxW={hasMedia ? areaW : areaW - 130} size={28} fonts={L.fonts} />);
    return [parts, y + 130];
  }
  if (L.style === 'vintage' || L.style === 'baroque') {
    const vintage = L.style === 'vintage';
    let y = vintage ? 55 : 65;
    if (tag) {
      parts.push(
        <Box key="tag" x={MARGIN} y={y} w={areaW} h={30} style={{ font: `${vintage ? 700 : 400} ${pt(vintage ? 11 : 10)}px ${L.fonts.heading}`, color: `#${t.accent}`, letterSpacing: vintage ? '0.15em' : '0.3em', whiteSpace: 'nowrap' }}>
          {cut(tag, 60).toUpperCase()}
        </Box>,
      );
      y += 42;
    }
    parts.push(
      <Box key="title" x={MARGIN} y={y} w={hasMedia ? areaW : areaW - 60} h={100} center
        style={{ font: `${vintage ? 700 : 400} ${titleSize(title, vintage ? 34 : 36, 26)}px/1.1 ${L.fonts.title}`, color: `#${t.text}`, textTransform: vintage ? 'uppercase' : 'none', letterSpacing: vintage ? '0.02em' : 0 }}>
        {title}
      </Box>,
    );
    if (vintage) {
      parts.push(<Rect key="r" x={MARGIN} y={y + 112} w={160} h={2} color={t.accent} />, <Diamond key="d" x={MARGIN + 71} y={y + 104} d={18} color={t.accent} />);
    } else {
      parts.push(<Rect key="r" x={MARGIN} y={y + 110} w={130} h={1.5} color={t.accent} />, <Diamond key="d" x={MARGIN + 136} y={y + 104} d={13} color={t.accent} />);
    }
    return [parts, y + 140];
  }
  let y = 55;
  if (tag) {
    const label = cut(tag, 60);
    const width = Math.min(areaW, 50 + label.length * 8);
    parts.push(
      <Rect key="tag" x={MARGIN} y={y} w={width} h={38} color={t.accent} alpha={0.16} radius={19} />,
      <Box key="tagtext" x={MARGIN + 20} y={y + 7} w={width - 30} h={26}
        style={{ font: `700 ${pt(11)}px ${FONTS.heading}`, color: `#${t.accent}`, whiteSpace: 'nowrap' }}>
        {label}
      </Box>,
    );
    y += 60;
  }
  const width = hasMedia ? areaW : areaW - 120;
  parts.push(
    <Box key="title" x={MARGIN} y={y} w={width} h={95} center
      style={{ font: `900 ${titleSize(title, 34, 26)}px/1.1 ${FONTS.title}`, color: `#${t.text}` }}>
      {title}
    </Box>,
    <Rect key="b1" x={MARGIN} y={y + 102} w={110} h={8} color={t.accent} radius={4} />,
    <Rect key="b2" x={MARGIN + 120} y={y + 102} w={35} h={8} color={t.accent2} radius={4} />,
  );
  return [parts, y + 135];
}

// ===== Kontent maketlari =====
function itemFont(count, hasMedia) {
  const base = count <= 3 ? 24 : count <= 4 ? 22 : 19;
  return hasMedia ? base - 2 : base;
}

function Bullets({ L, t, slide, x, y, w, h, hasMedia }) {
  const items = slide.items;
  const columns = items.length > 4 && !hasMedia ? 2 : 1;
  const size = itemFont(items.length / columns, hasMedia);
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, display: 'grid', gridTemplateColumns: `repeat(${columns}, 1fr)`, gridAutoRows: `minmax(0, ${Math.min(115, h / Math.ceil(items.length / columns))}px)`, gap: '16px 35px', alignContent: 'start' }}>
      {items.map((item, i) => (
        <div key={i} style={{ position: 'relative', overflow: 'hidden', padding: '10px 20px 10px 35px', display: 'flex', alignItems: 'center', ...L.card(i, 18, 0.8) }}>
          <Stripe L={L} t={t} i={i} h={Math.min(115, h / Math.ceil(items.length / columns))} />
          <div style={{ font: `${size}px/1.3 ${L.fonts.body}`, color: L.ink, overflow: 'hidden', maxHeight: '100%' }}>
            {item.heading && <b style={{ color: t.item_heading ? `#${t.item_heading}` : t.dark ? `#${t.accent}` : L.ink }}>{item.heading}: </b>}
            {item.text}
          </div>
        </div>
      ))}
    </div>
  );
}

function Cards({ L, t, slide, x, y, w, h }) {
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, display: 'flex', gap: 30 }}>
      {slide.items.map((item, i) => {
        const color = L.alt(i);
        return (
          <div key={i} style={{ position: 'relative', flex: 1, minWidth: 0, padding: '35px 30px 20px', overflow: 'hidden', ...L.card(i, 24) }}>
            <div style={{ position: 'absolute', left: 30, right: 30, top: 0, height: 9, borderRadius: 5, background: `#${color}` }} />
            <div style={{ width: 70, height: 70, borderRadius: '50%', background: `#${color}`, display: 'grid', placeItems: 'center', font: `900 ${pt(16)}px ${L.fonts.title}`, color: L.onAccent }}>
              {String(i + 1).padStart(2, '0')}
            </div>
            <div style={{ marginTop: 20, font: `700 ${pt(18)}px/1.2 ${L.fonts.heading}`, color: L.ink }}>{item.heading}</div>
            <div style={{ marginTop: 12, font: `${pt(14)}px/1.35 ${L.fonts.body}`, color: L.inkMuted }}>{item.text}</div>
          </div>
        );
      })}
    </div>
  );
}

function Stats({ L, t, slide, x, y, w, h }) {
  const cardH = Math.min(360, h);
  return (
    <div style={{ position: 'absolute', left: x, top: y + (h - cardH) / 2, width: w, height: cardH, display: 'flex', gap: 35 }}>
      {slide.items.map((item, i) => {
        const color = L.alt(i);
        return (
          <div key={i} style={{ flex: 1, minWidth: 0, padding: '40px 30px 20px', overflow: 'hidden', ...L.card(i, 28) }}>
            <div style={{ font: `900 ${pt(item.heading.length > 6 ? 36 : 54)}px/1.1 ${L.fonts.title}`, color: `#${t.stat_color ?? color}`, minHeight: 110, display: 'flex', alignItems: 'center' }}>
              {item.heading || '—'}
            </div>
            <div style={{ width: 80, height: 7, borderRadius: 4, background: `#${color}`, margin: '18px 0' }} />
            <div style={{ font: `${pt(15)}px/1.35 ${L.fonts.body}`, color: L.ink }}>{item.text}</div>
          </div>
        );
      })}
    </div>
  );
}

function Timeline({ L, t, slide, x, y, w, h }) {
  const items = slide.items;
  const step = w / items.length;
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: w, height: h }}>
      <Rect x={step / 2} y={52} w={step * (items.length - 1)} h={6} color={t.muted} alpha={0.5} radius={3} />
      {items.map((item, i) => {
        const color = L.alt(i);
        const cx = step * i + step / 2;
        return (
          <div key={i}>
            <Circle x={cx - 45} y={10} d={90} color={color} alpha={0.25} />
            <div style={{ position: 'absolute', left: cx - 32, top: 23, width: 64, height: 64, borderRadius: '50%', background: `#${color}`, display: 'grid', placeItems: 'center', font: `900 ${pt(18)}px ${L.fonts.title}`, color: L.onAccent }}>
              {i + 1}
            </div>
            <div style={{ position: 'absolute', left: cx - (step - 25) / 2, top: 130, width: step - 25, bottom: 0, padding: 20, textAlign: 'center', overflow: 'hidden', boxSizing: 'border-box', ...L.card(i, 20, 0.8) }}>
              <div style={{ font: `700 ${pt(16)}px/1.2 ${L.fonts.heading}`, color: L.ink }}>{item.heading}</div>
              <div style={{ marginTop: 10, font: `${pt(13)}px/1.35 ${L.fonts.body}`, color: L.inkMuted }}>{item.text}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Quote({ L, t, slide, x, y, w, h }) {
  const source = slide.items[0]?.heading || slide.items[0]?.text || '';
  return (
    <div style={{ position: 'absolute', left: x, top: y, width: w, height: h, overflow: 'hidden', ...L.card(0, 24, 0.7) }}>
      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 14, borderRadius: 7, background: `#${t.accent}` }} />
      <div style={{ position: 'absolute', left: 50, top: -40, font: `${pt(150)}px/1 ${L.fonts.quote}`, color: `#${t.accent2}` }}>“</div>
      <Box x={130} y={50} w={w - 240} h={h - 150} center
        style={{ font: `italic ${pt(slide.text.length > 120 ? 22 : 28)}px/1.3 ${L.fonts.quote}`, color: L.ink }}>
        {slide.text}
      </Box>
      {source && (
        <Box x={130} y={h - 85} w={w - 240} h={50} align="right" style={{ font: `600 ${pt(16)}px ${L.fonts.heading}`, color: `#${t.item_heading ?? t.accent}` }}>
          — {source}
        </Box>
      )}
    </div>
  );
}

const LAYOUTS = { bullets: Bullets, cards: Cards, stats: Stats, timeline: Timeline, quote: Quote };

// ===== Muqova =====
function coverFooter(author, labels) {
  return `${author ? `${labels.author}: ${author}   •   ` : ''}${new Date().getFullYear()}`;
}

function splitTitle(title) {
  const words = title.split(/\s+/).filter(Boolean);
  if (words.length < 2) return [title];
  let best = 1;
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i += 1) {
    const diff = Math.abs(words.slice(0, i).join(' ').length - words.slice(i).join(' ').length);
    if (diff < bestDiff) [best, bestDiff] = [i, diff];
  }
  return [words.slice(0, best).join(' '), words.slice(best).join(' ')];
}

function CoverCorporate({ L, t, content, author, labels, image }) {
  const titleW = image ? 660 : 950;
  return (
    <>
      {image ? (
        <>
          <Rect x={775} y={100} w={490} h={585} color={t.accent} radius={40} />
          <img src={image} alt="" style={imgStyle(745, 65, 490, 585, { borderRadius: 40 })} />
        </>
      ) : (
        [[520, 0.1], [340, 0.16], [160, 0.9]].map(([d, a]) => <Circle key={d} x={1000 - d / 2} y={375 - d / 2} d={d} color={t.accent} alpha={a} />)
      )}
      <CornerBadge t={t} />
      <div style={{ position: 'absolute', left: MARGIN, top: 105, width: 190, height: 40, borderRadius: 20, background: `#${t.accent}`, display: 'grid', placeItems: 'center', font: `700 ${pt(11)}px ${L.fonts.heading}`, color: '#fff', letterSpacing: '0.15em' }}>{labels.badge}</div>
      <Box x={MARGIN} y={170} w={titleW} h={300} center style={{ font: `900 ${titleSize(content.title, 58, 40)}px/1.06 ${L.fonts.title}`, color: `#${t.accent}` }}>{content.title}</Box>
      {content.subtitle && <Box x={MARGIN} y={485} w={titleW - 40} h={95} style={{ font: `${pt(18)}px/1.3 ${L.fonts.body}`, color: `#${t.muted}` }}>{content.subtitle}</Box>}
      <Rect x={MARGIN} y={620} w={titleW} h={1.5} color="C8C4E6" />
      <Box x={MARGIN} y={635} w={titleW} h={40} style={{ font: `600 ${pt(13)}px ${L.fonts.heading}`, color: `#${t.text}` }}>{coverFooter(author, labels)}</Box>
    </>
  );
}

function CoverDoodle({ L, t, content, author, labels, image, index }) {
  const [maxW, center] = image ? [700, MARGIN + 350] : [1050, W / 2];
  const lines = splitTitle(content.title);
  let y = 300 - 55 * lines.length;
  const badge = 230;
  return (
    <>
      {image && <Media L={L} t={t} image={image} index={index} />}
      <div style={{ position: 'absolute', left: center - badge / 2, top: y - 75, width: badge, height: 42, borderRadius: 21, background: `#${t.accent2}`, border: `1.5px solid ${INK}`, boxShadow: `5px 5px 0 ${INK}`, display: 'grid', placeItems: 'center', boxSizing: 'border-box', font: `700 ${pt(12)}px ${L.fonts.heading}`, color: INK, letterSpacing: '0.1em' }}>{labels.badge}</div>
      {lines.map((line, i) => {
        const w = Math.min(maxW, 90 + line.length * 40 * 0.95);
        const banner = <Banner key={i} x={center - w / 2 + (i ? 25 : -15)} y={y} text={line} color={L.alt(i)} maxW={maxW} size={40} h={120} fonts={L.fonts} />;
        y += 142;
        return banner;
      })}
      {content.subtitle && <Box x={center - maxW / 2} y={y + 5} w={maxW} h={80} align="center" style={{ font: `${pt(17)}px/1.3 ${L.fonts.body}`, color: `#${t.muted}` }}>{content.subtitle}</Box>}
      <Box x={center - maxW / 2} y={655} w={maxW} h={40} align="center" style={{ font: `600 ${pt(13)}px ${L.fonts.heading}`, color: INK }}>{coverFooter(author, labels)}</Box>
      <Doodle kind="sparkle" x={45} y={40} size={90} />
      <Doodle kind="spiral" x={50} y={570} size={100} />
      <Doodle kind="star" x={image ? 720 : W - 160} y={55} size={55} />
      <Doodle kind="squiggle" x={image ? 560 : W - 340} y={660} size={110} />
    </>
  );
}

function CoverVintage({ L, t, content, author, labels, image }) {
  const paperW = image ? 730 : 1000;
  const px = image ? 75 : (W - paperW) / 2;
  const innerX = px + 55;
  const innerW = paperW - 110;
  return (
    <>
      <Frame L={L} t={t} />
      <div style={{ position: 'absolute', left: px, top: 115, width: paperW, height: 520, ...L.card(0) }} />
      {image && (
        <div style={{ position: 'absolute', left: 812, top: 87, width: 446, height: 566, padding: 16, background: '#F0E4CC', boxShadow: '6px 10px 16px rgba(0,0,0,0.6)', transform: 'rotate(3deg)', boxSizing: 'border-box' }}>
          <img src={image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'sepia(0.9) contrast(1.05)', display: 'block' }} />
        </div>
      )}
      <Box x={innerX} y={160} w={innerW} h={35} align="center" style={{ font: `700 ${pt(12)}px ${L.fonts.heading}`, color: `#${t.item_heading}`, letterSpacing: '0.4em' }}>{labels.badge}</Box>
      <Box x={innerX} y={200} w={innerW} h={230} center align="center" style={{ font: `700 ${titleSize(content.title, 46, 34)}px/1.12 ${L.fonts.title}`, color: L.ink, textTransform: 'uppercase' }}>{content.title}</Box>
      <Rect x={innerX + innerW / 2 - 120} y={445} w={240} h={2} color={t.accent2} />
      <Diamond x={innerX + innerW / 2 - 9} y={437} d={18} color={t.accent2} />
      {content.subtitle && <Box x={innerX} y={465} w={innerW} h={75} align="center" style={{ font: `italic ${pt(16)}px/1.3 ${L.fonts.body}`, color: L.inkMuted }}>{content.subtitle}</Box>}
      <Box x={px} y={655} w={paperW} h={40} align="center" style={{ font: `600 ${pt(13)}px ${L.fonts.heading}`, color: `#${t.text}` }}>{coverFooter(author, labels)}</Box>
    </>
  );
}

function CoverBaroque({ L, t, content, author, labels, image }) {
  return (
    <>
      {image ? (
        <>
          <img src={image} alt="" style={imgStyle(0, 0, W, H)} />
          <Fade t={t} share={0.7} />
        </>
      ) : (
        [620, 460, 300].map((d) => <Circle key={d} x={960 - d / 2} y={375 - d / 2} d={d} color="000000" alpha={0} style={{ border: `1px solid #${t.accent}` }} />)
      )}
      <Frame L={L} t={t} />
      <Box x={MARGIN + 20} y={135} w={650} h={35} style={{ font: `${pt(12)}px ${L.fonts.heading}`, color: `#${t.accent}`, letterSpacing: '0.45em' }}>{labels.badge}</Box>
      <Box x={MARGIN + 20} y={180} w={700} h={270} style={{ justifyContent: 'flex-end', font: `${titleSize(content.title, 52, 40)}px/1.1 ${L.fonts.title}`, color: `#${t.text}` }}>{content.title}</Box>
      <Rect x={MARGIN + 20} y={470} w={220} h={1.5} color={t.accent} />
      <Diamond x={MARGIN + 246} y={464} d={13} color={t.accent} />
      {content.subtitle && <Box x={MARGIN + 20} y={495} w={650} h={95} style={{ font: `italic ${pt(18)}px/1.3 ${L.fonts.quote}`, color: `#${t.muted}` }}>{content.subtitle}</Box>}
      <Box x={MARGIN + 20} y={635} w={650} h={40} style={{ font: `${pt(13)}px ${L.fonts.heading}`, color: `#${t.accent}` }}>{coverFooter(author, labels)}</Box>
    </>
  );
}

function CoverNature({ L, t, content, author, labels, image: photo, index }) {
  const { decor, upper } = L.look;
  // cover: side — foto o'ngda, kontent slaydlaridagi shaklda (arka, oltin ramka, so'nuvchi); aks holda butun slayd
  const side = Boolean(photo) && L.look.cover === 'side';
  const image = side ? null : photo;
  const ink = image ? `#${L.look.cover_text ?? t.text}` : `#${t.text}`;
  const mark = L.look.cover_mark ?? (image && !t.dark ? t.accent2 : t.accent);
  const titleW = side ? (L.media === 'fade' ? FADE_X - MARGIN - 20 : 710) : 740;
  let art = null;
  if (side) {
    art = <Media L={L} t={t} image={photo} index={index} />;
  } else if (image) {
    art = (
      <>
        <img src={image} alt="" style={imgStyle(0, 0, W, H, { filter: L.tone })} />
        <Fade t={t} share={0.75} color={L.look.cover_fade ?? t.bg} />
      </>
    );
  } else if (ORNATE.includes(decor)) {
    art = (
      <>
        <Ornament x={840} y={375} w={360} color={t.accent} />
        <Stars x={985} y={290} color={t.accent} size={22} />
      </>
    );
  } else if (decor === 'leaf' || decor === 'leaves') {
    art = (
      <>
        <Leaf x={820} y={60} size={560} color={t.accent} alpha={0.9} angle={25} />
        <Leaf x={700} y={260} size={400} color={t.accent2} alpha={0.75} angle={-20} />
      </>
    );
  } else if (decor === 'sun') {
    art = <Sun x={830} y={130} size={480} color={t.accent} rotate={10} />;
  } else if (decor === 'peak') {
    art = (
      <>
        <Peak x={520} w={640} h={440} color={t.accent} alpha={0.35} />
        <Peak x={760} w={580} h={560} color={t.accent} alpha={0.6} />
        <Peak x={1000} w={400} h={360} color={t.accent} alpha={0.9} />
      </>
    );
  } else {
    art = [[560, 0.12], [380, 0.2], [200, 0.9]].map(([d, a]) => <Circle key={d} x={1000 - d / 2} y={375 - d / 2} d={d} color={t.accent} alpha={a} />);
  }
  return (
    <>
      {decor === 'frame' && <PalaceFrame t={t} />}
      {art}
      <SportDecor L={L} t={t} cover areaW={0} />
      <Rect x={MARGIN} y={142} w={50} h={4} color={mark} />
      <Box x={MARGIN + 65} y={128} w={600} h={35} style={{ font: `700 ${pt(13)}px ${L.fonts.heading}`, color: `#${mark}`, letterSpacing: '0.4em' }}>{labels.badge}</Box>
      <Box x={MARGIN} y={185} w={titleW} h={285}
        style={{ justifyContent: 'flex-end', font: `${L.italic}${L.look.light_title ? 300 : upper || L.fonts.title === SERIF ? 400 : 900} ${titleSize(content.title, upper ? 44 : 58, upper ? 34 : 42)}px/1.08 ${L.fonts.title}`, color: ink, textTransform: upper ? 'uppercase' : 'none' }}>
        {content.title}
      </Box>
      {ORNATE.includes(decor) ? <Ornament x={MARGIN} y={495} w={220} color={mark} />
        : SPORT.includes(decor) ? <Rect x={MARGIN} y={488} w={160} h={12} color={mark} />
          : <Rect x={MARGIN} y={490} w={150} h={9} color={mark} radius={5} />}
      {content.subtitle && <Box x={MARGIN} y={515} w={titleW - 40} h={90} style={{ font: `${pt(19)}px/1.3 ${L.fonts.body}`, color: image ? ink : `#${t.muted}` }}>{content.subtitle}</Box>}
      <Box x={MARGIN} y={650} w={titleW} h={40} style={{ font: `600 ${pt(13)}px ${L.fonts.heading}`, color: ink }}>{coverFooter(author, labels)}</Box>
    </>
  );
}

function Cover({ L, t, content, author, labels, media, index }) {
  const image = media(content.cover_image);
  const props = { L, t, content, author, labels, image, index };
  if (L.style === 'nature') return <CoverNature {...props} />;
  if (L.style === 'corporate') return <CoverCorporate {...props} />;
  if (L.style === 'doodle') return <CoverDoodle {...props} />;
  if (L.style === 'vintage') return <CoverVintage {...props} />;
  if (L.style === 'baroque') return <CoverBaroque {...props} />;
  const titleW = image ? COVER_IMG_X - MARGIN - 60 : 760;
  return (
    <>
      {image ? (
        <>
          <img src={image} alt="" style={imgStyle(COVER_IMG_X, 0, W - COVER_IMG_X, H)} />
          <Rect x={COVER_IMG_X} y={0} w={10} h={H} color={t.accent} />
          <Circle x={COVER_IMG_X - 35} y={550} d={70} color={t.accent2} />
        </>
      ) : (
        <>
          <Circle x={840} y={90} d={560} color={t.accent} alpha={0.12} />
          <Circle x={940} y={190} d={360} color={t.accent2} alpha={0.22} />
          <Circle x={1035} y={285} d={170} color={t.accent} alpha={0.85} />
          <Circle x={820} y={560} d={50} color={t.accent2} alpha={0.9} />
          <Circle x={1240} y={70} d={32} color={t.accent} alpha={0.9} />
        </>
      )}
      <Circle x={-120} y={540} d={300} color={t.accent2} alpha={0.08} />
      <Box x={MARGIN} y={125} w={600} h={40} style={{ font: `700 ${pt(14)}px ${FONTS.heading}`, color: `#${t.accent}`, letterSpacing: '0.3em' }}>
        {labels.badge}
      </Box>
      <Box x={MARGIN} y={180} w={titleW} h={260}
        style={{ justifyContent: 'flex-end', font: `900 ${pt(content.title.length > 40 ? 38 : 54)}px/1.08 ${FONTS.title}`, color: `#${t.text}` }}>
        {content.title}
      </Box>
      <Rect x={MARGIN} y={460} w={160} h={10} color={t.accent} radius={5} />
      <Rect x={MARGIN + 175} y={460} w={50} h={10} color={t.accent2} radius={5} />
      {content.subtitle && (
        <Box x={MARGIN} y={490} w={titleW - 40} h={100} style={{ font: `${pt(20)}px/1.3 ${FONTS.body}`, color: `#${t.muted}` }}>
          {content.subtitle}
        </Box>
      )}
      <Box x={MARGIN} y={645} w={titleW} h={40} style={{ font: `600 ${pt(14)}px ${FONTS.heading}`, color: `#${t.text}` }}>
        {coverFooter(author, labels)}
      </Box>
    </>
  );
}

function rowsLayout(count, top, maxRow, gap) {
  const columns = count <= (maxRow === 78 ? 6 : 5) ? 1 : 2;
  const perCol = Math.ceil(count / columns);
  const rowH = Math.min(maxRow, (H - 90 - top - (perCol - 1) * gap) / perCol);
  return { columns, perCol, rowH };
}

function Contents({ L, t, content, labels, total }) {
  const [heading, y] = Heading({ L, t, title: labels.contents, areaW: W - 2 * MARGIN });
  const rows = [[labels.plan, '03']];
  let start = 4;
  content.plans.forEach((plan, i) => {
    const end = start + plan.slides.length - 1;
    rows.push([`${i + 1}. ${plan.title}`, start === end ? String(start).padStart(2, '0') : `${String(start).padStart(2, '0')}–${String(end).padStart(2, '0')}`]);
    start = end + 1;
  });
  rows.push([labels.conclusion, String(total).padStart(2, '0')]);
  const { columns, perCol, rowH } = rowsLayout(rows.length, y, 78, 14);
  const colW = (W - 2 * MARGIN - (columns - 1) * 40) / columns;
  return (
    <>
      {heading}
      {rows.map(([title, pages], i) => {
        const col = Math.floor(i / perCol);
        const x = MARGIN + col * (colW + 40);
        const ry = y + (i % perCol) * (rowH + 14);
        return (
          <div key={i} style={{ position: 'absolute', left: x, top: ry, width: colW, height: rowH, overflow: 'hidden', boxSizing: 'border-box', ...L.card(i, 16) }}>
            <Stripe L={L} t={t} i={i} h={rowH} />
            <Box x={35} y={0} w={colW - 185} h={rowH} center style={{ font: `600 ${pt(rowH < 60 ? 13 : 16)}px/1.2 ${L.fonts.heading}`, color: L.ink }}>
              {title}
            </Box>
            <div style={{ position: 'absolute', right: 15, top: (rowH - 42) / 2, width: 125, height: 42, borderRadius: 21, background: `#${L.alt(i)}`, display: 'grid', placeItems: 'center', font: `700 ${pt(14)}px ${L.fonts.heading}`, color: L.onAccent }}>
              {pages}
            </div>
          </div>
        );
      })}
    </>
  );
}

function Plan({ L, t, content, labels }) {
  const [heading, y] = Heading({ L, t, title: labels.plan, areaW: W - 2 * MARGIN });
  const plans = content.plans;
  const { columns, perCol, rowH } = rowsLayout(plans.length, y, 95, 18);
  const colW = (W - 2 * MARGIN - (columns - 1) * 40) / columns;
  const d = rowH - 24;
  return (
    <>
      {heading}
      {plans.map((plan, i) => {
        const x = MARGIN + Math.floor(i / perCol) * (colW + 40);
        const ry = y + (i % perCol) * (rowH + 18);
        return (
          <div key={i} style={{ position: 'absolute', left: x, top: ry, width: colW, height: rowH, boxSizing: 'border-box', ...L.card(i, 18) }}>
            <div style={{ position: 'absolute', left: 14, top: 12, width: d, height: d, borderRadius: '50%', background: `#${L.alt(i)}`, display: 'grid', placeItems: 'center', font: `900 ${d * 0.42}px ${L.fonts.title}`, color: L.onAccent }}>
              {i + 1}
            </div>
            <Box x={d + 40} y={8} w={colW - d - 60} h={rowH - 16} center style={{ font: `600 ${pt(columns > 1 ? 15 : 19)}px/1.2 ${L.fonts.heading}`, color: L.ink }}>
              {plan.title}
            </Box>
          </div>
        );
      })}
    </>
  );
}

function Conclusion({ L, t, content, labels, areaW }) {
  const [heading, y] = Heading({ L, t, title: labels.conclusion, areaW, hasMedia: areaW < W - 2 * MARGIN });
  const points = content.conclusion.slice(0, 5);
  const bandH = 115;
  const rowH = Math.min(80, (H - 95 - bandH - 30 - y) / Math.max(1, points.length));
  const bandY = H - 95 - bandH;
  const marker = (i, ry) => {
    if (L.style === 'corporate') return <div style={{ position: 'absolute', left: MARGIN, top: ry + rowH / 2 - 17, width: 34, height: 34, borderRadius: '50%', background: `#${t.accent}`, display: 'grid', placeItems: 'center', color: '#fff', font: `700 ${pt(13)}px ${SANS}` }}>✓</div>;
    if (L.style === 'vintage') return <Diamond x={MARGIN} y={ry + rowH / 2 - 10} d={20} color={t.accent} />;
    if (L.style === 'baroque') return <Box x={MARGIN} y={ry} w={60} h={rowH - 5} center style={{ font: `${pt(18)}px ${L.fonts.title}`, color: `#${t.accent}` }}>{['I', 'II', 'III', 'IV', 'V'][i]}</Box>;
    if (L.style === 'nature') return <NatureMark L={L} t={t} i={i} x={MARGIN - 6} y={ry + rowH / 2 - 25} h={50} />;
    return <Circle x={MARGIN} y={ry + rowH / 2 - 13} d={26} color={L.alt(i)} />;
  };
  let band;
  if (L.style === 'nature') {
    const outline = L.look.band === 'outline';
    band = (
      <div style={{
        position: 'absolute', left: MARGIN, top: bandY + 5, width: areaW, height: bandH - 5, borderRadius: outline ? 0 : 14,
        background: outline ? 'transparent' : `#${t.accent}`, border: outline ? `1px solid #${t.accent}` : 'none',
        outline: outline ? `0.75px solid #${t.accent2}` : 'none', outlineOffset: -9,
        display: 'grid', placeItems: 'center', textAlign: 'center', padding: '0 30px', boxSizing: 'border-box',
        font: `${L.italic}${L.look.light_title ? 300 : L.look.upper || L.fonts.title === SERIF ? 400 : 900} ${pt(28)}px ${L.fonts.title}`,
        color: outline ? `#${t.accent}` : L.onAccent, textTransform: L.look.upper ? 'uppercase' : 'none',
      }}>
        {labels.thanks}
      </div>
    );
  } else if (L.style === 'corporate') {
    band = <div style={{ position: 'absolute', left: MARGIN, top: bandY, width: areaW, height: bandH, borderRadius: 28, background: `#${t.accent}`, display: 'grid', placeItems: 'center', font: `900 ${pt(30)}px ${L.fonts.title}`, color: '#fff' }}>{labels.thanks}</div>;
  } else if (L.style === 'doodle') {
    band = <Banner x={MARGIN + 100} y={bandY} text={labels.thanks} color={t.accent2} maxW={areaW - 260} size={26} h={105} fonts={L.fonts} />;
  } else if (L.style === 'vintage') {
    const bw = Math.min(areaW, 750);
    band = (
      <div style={{ position: 'absolute', left: MARGIN + (areaW - bw) / 2, top: bandY, width: bw, height: bandH - 5, display: 'grid', placeItems: 'center', ...L.card(0), font: `700 ${pt(26)}px ${L.fonts.title}`, color: L.ink, textTransform: 'uppercase' }}>
        {labels.thanks}
      </div>
    );
  } else if (L.style === 'baroque') {
    band = <Box x={MARGIN} y={bandY} w={areaW} h={bandH} center style={{ font: `italic ${pt(34)}px ${L.fonts.quote}`, color: `#${t.accent}` }}>{labels.thanks}</Box>;
  } else {
    band = (
      <div style={{ position: 'absolute', left: MARGIN, top: bandY, width: areaW, height: bandH, borderRadius: 34, background: `linear-gradient(90deg, #${t.accent}, #${t.accent2})`, display: 'grid', placeItems: 'center', font: `900 ${pt(28)}px ${FONTS.title}`, color: L.onAccent }}>
        ✨ {labels.thanks}
      </div>
    );
  }
  const offset = L.style === 'baroque' ? 65 : L.style === 'corporate' ? 55 : L.style === 'nature' ? 45 : 50;
  return (
    <>
      {heading}
      {points.map((point, i) => (
        <div key={i}>
          {marker(i, y + i * rowH)}
          <Box x={MARGIN + offset} y={y + i * rowH} w={areaW - offset} h={rowH - 5} center style={{ font: `${pt(rowH < 60 ? 14 : 17)}px/1.25 ${L.fonts.body}`, color: `#${t.text}` }}>
            {point}
          </Box>
        </div>
      ))}
      {band}
    </>
  );
}

/** Slayd foni (shablon uslubida). */
function background(L, t, angle) {
  if (L.style === 'corporate') return `#${t.bg}`;
  if (L.style === 'doodle') {
    return 'linear-gradient(#e5e5ef 2px, transparent 2px) 0 20px / 40px 40px, linear-gradient(90deg, #e5e5ef 2px, transparent 2px) 20px 0 / 40px 40px, #fbfbfd';
  }
  if (L.style === 'vintage') {
    return `radial-gradient(ellipse at 50% 45%, transparent 35%, rgba(8, 5, 3, 0.7) 100%), linear-gradient(135deg, #${t.bg}, #${t.bg2})`;
  }
  if (L.style === 'nature' && L.look.texture === 'parchment') {
    // Eski qog'oz: iliq dog'lar va chetlari to'qroq (bot: art.texture("parchment"))
    return `radial-gradient(ellipse at 50% 50%, transparent 45%, rgba(95, 60, 25, 0.35) 100%), radial-gradient(circle at 25% 30%, rgba(120, 80, 35, 0.12), transparent 40%), radial-gradient(circle at 75% 70%, rgba(120, 80, 35, 0.1), transparent 45%), linear-gradient(145deg, #${t.bg}, #${t.bg2})`;
  }
  if (L.style === 'nature' && L.look.texture === 'marble') {
    return `radial-gradient(ellipse at 30% 20%, rgba(255, 255, 255, 0.55), transparent 55%), linear-gradient(125deg, transparent 40%, rgba(130, 130, 128, 0.08) 48%, transparent 56%), linear-gradient(145deg, #${t.bg}, #${t.bg2})`;
  }
  if (L.style === 'nature' && t.bg === t.bg2) return `#${t.bg}`;
  return `linear-gradient(${180 - angle}deg, #${t.bg}, #${t.bg2})`;
}

/** item: { type: 'cover' | 'contents' | 'plan' | 'conclusion' | 'slide', pi, si } */
export function SlideCanvas({ deck, item, index, total, media }) {
  const { content, theme: t, lang, author } = deck;
  const L = lookOf(t);
  const labels = LABELS[lang] ?? LABELS.uz;
  const angle = { cover: 120, conclusion: 60 }[item.type] ?? (index % 2 ? 135 : 45);
  let body;
  let hasMedia = false;

  if (item.type === 'cover') {
    body = <Cover L={L} t={t} content={content} author={author} labels={labels} media={media} index={index} />;
  } else if (item.type === 'contents') {
    body = <Contents L={L} t={t} content={content} labels={labels} total={total} />;
  } else if (item.type === 'plan') {
    body = <Plan L={L} t={t} content={content} labels={labels} />;
  } else if (item.type === 'conclusion') {
    // Barokko xulosasi muqova rasmi ustida (builder: BaroqueDeck.conclusion_slide)
    const image = L.style === 'baroque' ? media(content.cover_image) : null;
    hasMedia = Boolean(image);
    body = (
      <>
        {image && <Media L={L} t={t} image={image} index={index} />}
        <Conclusion L={L} t={t} content={content} labels={labels} areaW={image ? L.textW : W - 2 * MARGIN} />
      </>
    );
  } else {
    const plan = content.plans[item.pi];
    const slide = plan.slides[item.si];
    hasMedia = Boolean(slide.video || slide.image);
    const areaW = hasMedia ? L.textW : W - 2 * MARGIN;
    const [heading, top] = Heading({ L, t, title: slide.title, tag: `${item.pi + 1}. ${plan.title}`, areaW, hasMedia });
    let y = top;
    let kind = slide.kind;
    // builder.py kabi: rasmli slaydda ko'p ustunli maketlar ro'yxatga aylanadi
    if (hasMedia && (kind === 'cards' || kind === 'timeline' || (kind === 'stats' && slide.items.length > 3))) kind = 'bullets';
    const intro = kind !== 'quote' && slide.text;
    const Layout = LAYOUTS[kind] ?? Bullets;
    body = (
      <>
        {hasMedia && !(L.style === 'nature' && (L.media === 'full' || L.media === 'fade')) && <Media L={L} t={t} image={media(slide.image)} video={slide.video} index={index} />}
        {heading}
        {intro && (
          <Box x={MARGIN} y={y} w={areaW} h={70} style={{ font: `${pt(15)}px/1.3 ${L.fonts.body}`, color: `#${t.muted}` }}>
            {slide.text}
          </Box>
        )}
        <Layout L={L} t={t} slide={slide} x={MARGIN} y={(y += intro ? 85 : 0)} w={areaW} h={H - 85 - y} hasMedia={hasMedia} />
      </>
    );
  }

  return (
    <div
      style={{
        position: 'absolute', left: 0, top: 0, width: W, height: H, overflow: 'hidden',
        background: background(L, t, angle), fontFamily: L.fonts.body,
      }}
    >
      {L.style === 'corporate' && <Frame L={L} t={t} />}
      {(item.type !== 'cover' && L.style === 'classic') && <Decorations L={L} t={t} index={index} total={total} title={content.title} hasMedia={hasMedia} />}
      {/* Tabiat: rasm (to'liq fon bo'lsa) → bezaklar → matn (bot: side_media → decorations → maket) */}
      {(item.type !== 'cover' && L.style === 'nature') && (L.media === 'full' || L.media === 'fade') && hasMedia && item.type === 'slide' && (
        <Media L={L} t={t} image={media(content.plans[item.pi].slides[item.si].image)} video={content.plans[item.pi].slides[item.si].video} index={index} />
      )}
      {(item.type !== 'cover' && L.style === 'nature') && <Decorations L={L} t={t} index={index} total={total} title={content.title} hasMedia={hasMedia} />}
      {body}
      {/* Shablonlarda ramka va raqam rasm ustida turadi (builder: decorations rasmdan keyin chiziladi) */}
      {(item.type !== 'cover' && L.style !== 'classic' && L.style !== 'nature') && <Decorations L={L} t={t} index={index} total={total} title={content.title} hasMedia={hasMedia} />}
    </div>
  );
}

/** Slaydni konteyner kengligiga moslab kichraytiradi. */
export default function SlideView(props) {
  const ref = useRef();
  const [scale, setScale] = useState(0);
  useLayoutEffect(() => {
    const node = ref.current;
    const update = () => setScale(node.clientWidth / W);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    // height — aspect-ratio ni qo'llamaydigan eski iOS (15 gacha) uchun
    <div ref={ref} className={`slide-view ${props.className ?? ''}`} style={{ aspectRatio: `${W} / ${H}`, height: scale ? H * scale : undefined }}>
      {scale > 0 && (
        <div style={{ position: 'absolute', left: 0, top: 0, width: W, height: H, transform: `scale(${scale})`, transformOrigin: '0 0' }}>
          <SlideCanvas {...props} />
        </div>
      )}
    </div>
  );
}
