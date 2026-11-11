import { useId } from 'react';

// Rasmdagi «3D» illyustratsiyalar — gradient va yumshoq soya bilan chizilgan SVG.
// Har bir nusxada gradient ID'lari takrorlanmasligi uchun useId ishlatiladi
function useIds() {
  const base = useId().replace(/:/g, '');
  return (name) => `${base}-${name}`;
}

function Shadow({ id, color = '#2a1680', opacity = 0.25, dy = 3, blur = 3 }) {
  return (
    <filter id={id} x="-30%" y="-30%" width="160%" height="170%">
      <feDropShadow dx="0" dy={dy} stdDeviation={blur} floodColor={color} floodOpacity={opacity} />
    </filter>
  );
}

const Sparkle = ({ x, y, r, fill = '#FFD15C' }) => (
  <path
    d={`M${x} ${y - r}C${x + r * 0.15} ${y - r * 0.15} ${x + r * 0.15} ${y - r * 0.15} ${x + r} ${y}C${x + r * 0.15} ${y + r * 0.15} ${x + r * 0.15} ${y + r * 0.15} ${x} ${y + r}C${x - r * 0.15} ${y + r * 0.15} ${x - r * 0.15} ${y + r * 0.15} ${x - r} ${y}C${x - r * 0.15} ${y - r * 0.15} ${x - r * 0.15} ${y - r * 0.15} ${x} ${y - r}z`}
    fill={fill}
  />
);

// ===== Hero: qog'ozlar va bitiruv qalpoqchasi =====
export function HeroArt({ className }) {
  const id = useIds();
  return (
    <svg className={className} viewBox="0 0 150 112" aria-hidden="true">
      <defs>
        <linearGradient id={id('paper')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#DCD3FF" />
        </linearGradient>
        <linearGradient id={id('cap')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7A60F5" />
          <stop offset="1" stopColor="#3F25B6" />
        </linearGradient>
        <linearGradient id={id('gold')} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFD873" />
          <stop offset="1" stopColor="#F2A81D" />
        </linearGradient>
        <Shadow id={id('sh')} opacity={0.35} dy={5} blur={4} />
      </defs>
      <Sparkle x={20} y={40} r={7} />
      <Sparkle x={12} y={64} r={4.5} />
      <Sparkle x={140} y={86} r={4} fill="#FFE39A" />
      <g filter={`url(#${id('sh')})`}>
        <rect x="50" y="38" width="64" height="58" rx="9" fill="#C3B5FF" transform="rotate(-9 82 67)" />
        <rect x="40" y="46" width="72" height="58" rx="10" fill={`url(#${id('paper')})`} />
        <rect x="50" y="58" width="12" height="12" rx="3" fill="#B6A6FF" />
        <rect x="67" y="59" width="34" height="5" rx="2.5" fill="#8A73F5" />
        <rect x="67" y="67" width="24" height="4" rx="2" fill="#B6A6FF" />
        <rect x="50" y="78" width="52" height="5" rx="2.5" fill="#9C88F7" />
        <rect x="50" y="88" width="38" height="5" rx="2.5" fill="#C3B5FF" />
      </g>
      <g filter={`url(#${id('sh')})`}>
        <path d="M72 38v11c0 5 9 9 21 9s21-4 21-9V38l-21 8z" fill="#3A22A8" />
        <path d="M93 16 133 31 93 46 53 31z" fill={`url(#${id('cap')})`} />
        <path d="M93 16 133 31 93 23 53 31z" fill="#FFFFFF" opacity="0.18" />
        <circle cx="93" cy="31" r="3" fill={`url(#${id('gold')})`} />
        <path d="M93 31 124 36v20" stroke={`url(#${id('gold')})`} strokeWidth="2.6" fill="none" strokeLinecap="round" />
        <path d="M120 55h8l2 13h-12z" fill={`url(#${id('gold')})`} />
      </g>
    </svg>
  );
}

// ===== Xizmat kartalaridagi ikonkalar =====
function PresArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('scr')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E2D9FF" />
        </linearGradient>
      </defs>
      <path d="M32 40v8M32 44l-9 11M32 44l9 11" stroke="#EDE7FF" strokeWidth="3.2" strokeLinecap="round" />
      <rect x="7" y="9" width="50" height="33" rx="5" fill={`url(#${id('scr')})`} />
      <rect x="4" y="5" width="56" height="7" rx="3.5" fill="#F6F2FF" />
      <rect x="13" y="18" width="16" height="4" rx="2" fill="#8B6BFF" />
      <rect x="13" y="25" width="11" height="3" rx="1.5" fill="#C2B4FF" />
      <rect x="35" y="26" width="5" height="10" rx="1.5" fill="#B4A3FF" />
      <rect x="42" y="21" width="5" height="15" rx="1.5" fill="#8B6BFF" />
      <rect x="49" y="17" width="5" height="19" rx="1.5" fill="#6A4BF0" />
    </>
  );
}

function ReferatArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('doc')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#D4F5E3" />
        </linearGradient>
      </defs>
      <path d="M15 6a4 4 0 0 1 4-4h18l12 12v36a4 4 0 0 1-4 4H19a4 4 0 0 1-4-4z" fill={`url(#${id('doc')})`} />
      <path d="M37 2v8a4 4 0 0 0 4 4h8z" fill="#A9E9C6" />
      <rect x="21" y="21" width="22" height="4" rx="2" fill="#19B865" />
      <rect x="21" y="29" width="18" height="4" rx="2" fill="#19B865" />
      <rect x="21" y="37" width="22" height="4" rx="2" fill="#7FDBA8" />
      <rect x="21" y="44" width="12" height="3.5" rx="1.75" fill="#7FDBA8" />
    </>
  );
}

function KursArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('pg')} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#FFE0CC" />
        </linearGradient>
      </defs>
      <path d="M32 14C25 8 15 7 5 9v37c10-2 20-1 27 5z" fill={`url(#${id('pg')})`} />
      <path d="M32 14c7-6 17-7 27-5v37c-10-2-20-1-27 5z" fill={`url(#${id('pg')})`} />
      <path d="M32 14v37" stroke="#FFB48A" strokeWidth="2" />
      <path d="M11 18c5-1 10 0 15 2M11 25c5-1 10 0 15 2M11 32c5-1 10 0 15 2M38 20c5-2 10-3 15-2M38 27c5-2 10-3 15-2M38 34c5-2 10-3 15-2" stroke="#FFA06A" strokeWidth="2.4" strokeLinecap="round" />
    </>
  );
}

function MustaqilArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('cap')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#CFE0FF" />
        </linearGradient>
      </defs>
      <path d="M16 26v12c0 5 7 9 16 9s16-4 16-9V26l-16 7z" fill="#B7D0FF" />
      <path d="M32 8 61 21 32 34 3 21z" fill={`url(#${id('cap')})`} />
      <path d="M32 21 53 25v15" stroke="#FFC64D" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M50 39h6l1.5 9h-9z" fill="#FFC64D" />
      <circle cx="32" cy="21" r="2.6" fill="#FFC64D" />
    </>
  );
}

function ShablonArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('top')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#FFE1EC" />
        </linearGradient>
      </defs>
      <path d="M32 32 58 42 32 52 6 42z" fill="#FFB3CF" />
      <path d="M32 22 58 32 32 42 6 32z" fill="#FFD0E1" />
      <path d="M32 8 58 19 32 30 6 19z" fill={`url(#${id('top')})`} />
    </>
  );
}

function MaqolaArt({ id }) {
  return (
    <>
      <defs>
        <linearGradient id={id('paper')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#CDEFD9" />
        </linearGradient>
      </defs>
      <rect x="10" y="6" width="38" height="46" rx="5" fill={`url(#${id('paper')})`} />
      <path d="M16 15h26" stroke="#16a34a" strokeWidth="3.2" strokeLinecap="round" />
      <rect x="16" y="21" width="12" height="10" rx="2" fill="#86d9a6" />
      <path d="M31 22h11M31 26.5h11M31 31h8M16 37h26M16 42h18" stroke="#6cc58f" strokeWidth="2.2" strokeLinecap="round" />
      <path d="m44 40 12-12 4 4-12 12-5.5 1.5z" fill="#FFC64D" />
      <path d="m56 28 2-2a2 2 0 0 1 3 0l1 1a2 2 0 0 1 0 3l-2 2z" fill="#F59E0B" />
    </>
  );
}

const TILE_ART = { pres: PresArt, referat: ReferatArt, kurs: KursArt, mustaqil: MustaqilArt, shablon: ShablonArt, maqola: MaqolaArt };

export function TileArt({ kind, className = 'tile__art' }) {
  const id = useIds();
  const Art = TILE_ART[kind] ?? ReferatArt;
  return (
    <svg className={className} viewBox="0 0 64 58" aria-hidden="true">
      <defs>
        <Shadow id={id('sh')} opacity={0.28} dy={3} blur={2.5} />
      </defs>
      <g filter={`url(#${id('sh')})`}>
        <Art id={id} />
      </g>
    </svg>
  );
}

// ===== Bosh sahifadagi «Maqola» kartasi: qog'ozlar to'plami va ruchka =====
const SPARKLE = 'M0 -6C1 -1 1 -1 6 0C1 1 1 1 0 6C-1 1 -1 1 -6 0C-1 -1 -1 -1 0 -6Z';

export function MaqolaHeroArt({ className }) {
  const id = useIds();
  return (
    <svg className={className} viewBox="0 0 120 100" aria-hidden="true">
      <defs>
        <Shadow id={id('sh')} opacity={0.18} dy={4} blur={3.5} />
        <linearGradient id={id('page')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#EEE9FF" />
        </linearGradient>
        <linearGradient id={id('pen')} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3A3486" />
          <stop offset="1" stopColor="#1F1B57" />
        </linearGradient>
      </defs>
      <g filter={`url(#${id('sh')})`}>
        <rect x="16" y="24" width="54" height="66" rx="6" fill="#DCD3FF" transform="rotate(-16 43 57)" />
        <rect x="22" y="18" width="54" height="68" rx="6" fill="#EEE9FF" transform="rotate(-7 49 52)" />
        <rect x="30" y="12" width="56" height="72" rx="6" fill={`url(#${id('page')})`} />
        <path d="M39 25h30" stroke="#7357F6" strokeWidth="3.4" strokeLinecap="round" />
        <path d="M39 35h38M39 43h38M39 51h30M39 59h38M39 67h24" stroke="#C9BDFF" strokeWidth="2.6" strokeLinecap="round" />
        <g transform="translate(101 20) rotate(36)">
          <rect x="-5" y="0" width="10" height="52" rx="4" fill={`url(#${id('pen')})`} />
          <rect x="-5" y="9" width="10" height="5" fill="#F5B93C" />
          <path d="M-5 52h10l-5 13z" fill="#F5C766" />
          <path d="M-1.6 60h3.2L0 65z" fill="#1F1B57" />
          <rect x="-1.2" y="-4" width="2.4" height="16" rx="1.2" fill="#C9C3F0" transform="translate(6 0)" />
        </g>
      </g>
      <path d={SPARKLE} fill="#FFFFFF" transform="translate(14 16) scale(0.9)" />
    </svg>
  );
}

export function MaqolaDecor({ className }) {
  return (
    <svg className={className} viewBox="0 0 90 110" aria-hidden="true">
      <g transform="rotate(12 50 60)" opacity="0.6">
        <rect x="26" y="26" width="50" height="64" rx="6" fill="#FFFFFF" />
        <path d="M34 38h26M34 47h34M34 55h34M34 63h22" stroke="#C9BDFF" strokeWidth="2.6" strokeLinecap="round" />
      </g>
      <path d={SPARKLE} fill="#FFFFFF" opacity="0.95" transform="translate(16 20) scale(1.2)" />
      <path d={SPARKLE} fill="#CDBFFF" transform="translate(80 18) scale(0.7)" />
      <path d={SPARKLE} fill="#FFFFFF" opacity="0.8" transform="translate(14 92) scale(0.6)" />
    </svg>
  );
}

// ===== AI yordamchi: hujjat, sehrli tayoqcha va yulduzchalar =====
// Rasmni almashtirish: faylni client/public/ ga qo'ying (masalan ai-card.png) va shu yerga yozing: '/ai-card.png'
export const AI_CARD_IMAGE = null;

export function AiArt({ className }) {
  const id = useIds();
  if (AI_CARD_IMAGE) return <img className={className} src={AI_CARD_IMAGE} alt="" />;
  return (
    <svg className={className} viewBox="0 0 150 124" aria-hidden="true">
      <defs>
        <linearGradient id={id('sheet')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E7E0FF" />
        </linearGradient>
        <linearGradient id={id('wand')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#9277FF" />
          <stop offset="1" stopColor="#4B2FC9" />
        </linearGradient>
        <linearGradient id={id('ai')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5AA6FF" />
          <stop offset="1" stopColor="#7357F6" />
        </linearGradient>
        <Shadow id={id('sh')} color="#9a5a00" opacity={0.28} dy={5} blur={4} />
      </defs>
      <g filter={`url(#${id('sh')})`}>
        <g transform="rotate(-8 60 64)">
          <rect x="22" y="14" width="74" height="96" rx="11" fill={`url(#${id('sheet')})`} />
          <rect x="34" y="26" width="30" height="20" rx="6" fill={`url(#${id('ai')})`} />
          <text x="41" y="41" fontSize="13" fontWeight="900" fill="#fff" fontFamily="Nunito, sans-serif">AI</text>
          <rect x="34" y="56" width="50" height="5" rx="2.5" fill="#A996FF" />
          <rect x="34" y="67" width="42" height="5" rx="2.5" fill="#C9BEFF" />
          <rect x="34" y="78" width="48" height="5" rx="2.5" fill="#C9BEFF" />
          <rect x="34" y="89" width="30" height="5" rx="2.5" fill="#DDD5FF" />
        </g>
        <g transform="rotate(38 112 80)">
          <rect x="106" y="50" width="12" height="64" rx="6" fill={`url(#${id('wand')})`} />
          <rect x="106" y="50" width="12" height="15" rx="6" fill="#FFFFFF" />
        </g>
      </g>
      <Sparkle x={128} y={30} r={11} />
      <Sparkle x={104} y={18} r={6} fill="#FFFFFF" />
      <Sparkle x={140} y={56} r={5} fill="#FFFFFF" />
      <Sparkle x={14} y={30} r={5} fill="#FFE39A" />
    </svg>
  );
}

// ===== Fayl ikonkasi (Word / PowerPoint / PDF) =====
const FILE_STYLES = {
  docx: { letter: 'W', color: '#2B6BEA', paper: '#EAF1FF', fold: '#C9DAFF' },
  doc: { letter: 'W', color: '#2B6BEA', paper: '#EAF1FF', fold: '#C9DAFF' },
  pptx: { letter: 'P', color: '#E8552C', paper: '#FFF0EA', fold: '#FFD3C2' },
  ppt: { letter: 'P', color: '#E8552C', paper: '#FFF0EA', fold: '#FFD3C2' },
  pdf: { letter: 'PDF', color: '#E5364B', paper: '#FFECEF', fold: '#FFC9D1' },
  xlsx: { letter: 'X', color: '#18A55A', paper: '#E8F8EF', fold: '#BDEBD1' },
};

export function FileIcon({ type = 'docx', className = 'item__icon' }) {
  const style = FILE_STYLES[type] ?? FILE_STYLES.docx;
  const small = style.letter.length > 1;
  return (
    <svg className={className} viewBox="0 0 46 52" aria-hidden="true">
      <path d="M8 4a4 4 0 0 1 4-4h20l12 12v36a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4z" fill={style.paper} />
      <path d="M32 0v8a4 4 0 0 0 4 4h8z" fill={style.fold} />
      <rect x="0" y="20" width={small ? 32 : 26} height="22" rx="5" fill={style.color} />
      <text
        x={small ? 16 : 13}
        y="36"
        textAnchor="middle"
        fontSize={small ? 10.5 : 14}
        fontWeight="900"
        fill="#fff"
        fontFamily="Nunito, sans-serif"
      >
        {style.letter}
      </text>
    </svg>
  );
}
