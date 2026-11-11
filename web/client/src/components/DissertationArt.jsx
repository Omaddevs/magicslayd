import { useId } from 'react';

/** Dissertatsiya illyustratsiyasi: ilmiy kitob, kolba va grafik (platforma ranglarida). */
export default function DissertationArt({ className }) {
  const raw = useId().replace(/:/g, '');
  const id = (name) => `${raw}-${name}`;
  return (
    <svg className={className} viewBox="0 0 150 124" aria-hidden="true">
      <defs>
        <linearGradient id={id('book')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7C63FA" />
          <stop offset="1" stopColor="#4B2FD1" />
        </linearGradient>
        <linearGradient id={id('page')} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E6DFFF" />
        </linearGradient>
        <linearGradient id={id('liquid')} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5FE0B5" />
          <stop offset="1" stopColor="#1FAE7F" />
        </linearGradient>
        <filter id={id('sh')} x="-20%" y="-20%" width="140%" height="150%">
          <feDropShadow dx="0" dy="5" stdDeviation="4" floodColor="#3A22B8" floodOpacity="0.3" />
        </filter>
      </defs>
      <g filter={`url(#${id('sh')})`}>
        {/* Kitob */}
        <rect x="14" y="40" width="74" height="78" rx="8" fill={`url(#${id('book')})`} />
        <rect x="22" y="46" width="62" height="66" rx="5" fill={`url(#${id('page')})`} />
        <rect x="30" y="56" width="40" height="5" rx="2.5" fill="#B7A8FF" />
        {/* Grafik */}
        <path d="M30 100 L42 88 L52 94 L66 74 L76 80" fill="none" stroke="#7357F6" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="66" cy="74" r="3.5" fill="#FFB547" />
        {/* Kolba */}
        <path d="M104 18 h18 v8 h-3 v20 l18 34 c4 8 -1 16 -10 16 h-28 c-9 0 -14 -8 -10 -16 l18 -34 v-20 h-3 z" fill="#FFFFFF" opacity="0.95" />
        <path d="M95 82 l8 -15 h22 l8 15 c3 6 -1 11 -7 11 h-24 c-6 0 -10 -5 -7 -11 z" fill={`url(#${id('liquid')})`} />
        <circle cx="108" cy="80" r="3" fill="#FFFFFF" opacity="0.8" />
        <circle cx="118" cy="74" r="2" fill="#FFFFFF" opacity="0.8" />
      </g>
      <path d="M140 12 l2 5 l5 2 l-5 2 l-2 5 l-2 -5 l-5 -2 l5 -2 z" fill="#FFFFFF" opacity="0.9" />
      <path d="M8 18 l1.6 3.8 l3.8 1.6 l-3.8 1.6 l-1.6 3.8 l-1.6 -3.8 l-3.8 -1.6 l3.8 -1.6 z" fill="#FFFFFF" opacity="0.85" />
    </svg>
  );
}
