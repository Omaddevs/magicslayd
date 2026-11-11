import { useId } from 'react';

/** Diplom ishi illyustratsiyasi: bitiruvchi qalpog'i, o'ralgan diplom va uchqunlar (platforma ranglarida). */
export default function DiplomaArt({ className }) {
  const raw = useId().replace(/:/g, '');
  const id = (name) => `${raw}-${name}`;
  return (
    <svg className={className} viewBox="0 0 150 124" aria-hidden="true">
      <defs>
        <linearGradient id={id('paper')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E4DCFF" />
        </linearGradient>
        <linearGradient id={id('cap')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8B73FF" />
          <stop offset="1" stopColor="#5B3FE0" />
        </linearGradient>
        <linearGradient id={id('ribbon')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFD36B" />
          <stop offset="1" stopColor="#FFA928" />
        </linearGradient>
        <filter id={id('sh')} x="-20%" y="-20%" width="140%" height="150%">
          <feDropShadow dx="0" dy="5" stdDeviation="4" floodColor="#4B2FD1" floodOpacity="0.28" />
        </filter>
      </defs>
      <g filter={`url(#${id('sh')})`}>
        {/* Diplom varag'i */}
        <rect x="22" y="44" width="92" height="66" rx="10" fill={`url(#${id('paper')})`} />
        <rect x="34" y="58" width="52" height="6" rx="3" fill="#B7A8FF" />
        <rect x="34" y="70" width="66" height="5" rx="2.5" fill="#D6CCFF" />
        <rect x="34" y="80" width="58" height="5" rx="2.5" fill="#D6CCFF" />
        <rect x="34" y="90" width="40" height="5" rx="2.5" fill="#D6CCFF" />
        {/* Muhr va lenta */}
        <circle cx="98" cy="96" r="11" fill={`url(#${id('ribbon')})`} />
        <path d="M92 104 l-4 14 l8 -5 l6 6 l1 -15 z" fill="#FF9F1C" />
        <circle cx="98" cy="96" r="5.5" fill="#FFF3D0" />
        {/* Qalpoq */}
        <path d="M78 8 L136 28 L78 48 L20 28 Z" fill={`url(#${id('cap')})`} />
        <path d="M50 36 v14 c0 8 56 8 56 0 v-14 l-28 10 z" fill="#4A2FC8" />
        <path d="M118 33 v22" stroke="#FFC23D" strokeWidth="3" strokeLinecap="round" />
        <circle cx="118" cy="58" r="4.5" fill="#FFC23D" />
      </g>
      {/* Uchqunlar */}
      <path d="M14 14 l2.5 6 l6 2.5 l-6 2.5 l-2.5 6 l-2.5 -6 l-6 -2.5 l6 -2.5 z" fill="#FFFFFF" opacity="0.9" />
      <path d="M140 84 l1.8 4.2 l4.2 1.8 l-4.2 1.8 l-1.8 4.2 l-1.8 -4.2 l-4.2 -1.8 l4.2 -1.8 z" fill="#FFFFFF" opacity="0.85" />
    </svg>
  );
}
