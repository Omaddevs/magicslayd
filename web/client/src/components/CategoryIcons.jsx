// Shablon sohalari uchun rangli belgilar (kvadrat plitkalar). Kalitlar — bot presentation/themes.py THEME_CATEGORIES.
// Yangi soha qo'shilsa va bu yerda belgisi bo'lmasa — emojisi rangli fonda chiqadi.

const S = ({ children, fill = 'none' }) => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

const ICONS = {
  ofis: {
    colors: ['#34d399', '#059669'],
    icon: (
      <S>
        <path d="M5 20V12M10 20V8M15 20v-6M20 20V5" strokeWidth="2.6" />
      </S>
    ),
  },
  talim: {
    colors: ['#38bdf8', '#2563eb'],
    icon: (
      <S fill="currentColor">
        <path d="M12 4 1.5 9 12 14l8-3.8V16h1.8V9z" strokeWidth="1" />
        <path d="M6 12.2V16c0 1.4 2.7 3 6 3s6-1.6 6-3v-3.8L12 15z" strokeWidth="1" />
      </S>
    ),
  },
  tarix: {
    colors: ['#fbbf24', '#b45309'],
    icon: (
      <S>
        <path d="M3 9.5 12 4l9 5.5M4.5 20h15M5 17h14" />
        <path d="M6.5 10v7M10 10v7M14 10v7M17.5 10v7" />
      </S>
    ),
  },
  sanat: {
    colors: ['#f472b6', '#c026d3'],
    icon: (
      <S>
        <path d="M12 3a9 9 0 1 0 0 18c1.4 0 2-1 2-2 0-1.3-1-1.6-1-3 0-1 .8-2 2-2h2.5a3.5 3.5 0 0 0 3.5-3.5C21 6.6 17 3 12 3z" />
        <circle cx="7.5" cy="11" r="1.3" fill="currentColor" />
        <circle cx="10" cy="7" r="1.3" fill="currentColor" />
        <circle cx="15" cy="7" r="1.3" fill="currentColor" />
      </S>
    ),
  },
  fan: {
    colors: ['#60a5fa', '#4f46e5'],
    icon: (
      <S>
        <rect x="3" y="4" width="18" height="16" rx="3" />
        <path d="m10 10-2 2 2 2M14 10l2 2-2 2" />
      </S>
    ),
  },
  tabiat: {
    colors: ['#a3e635', '#16a34a'],
    icon: (
      <S>
        <path d="M5 19c0-8 5-13 15-14-1 10-6 15-14 15" />
        <path d="M5 19 13 11" />
      </S>
    ),
  },
  sport: {
    colors: ['#fb923c', '#ea580c'],
    icon: (
      <S>
        <path d="M7 4h10v5a5 5 0 0 1-10 0z" />
        <path d="M7 6H4.5a2.5 2.5 0 0 0 2.6 3.4M17 6h2.5a2.5 2.5 0 0 1-2.6 3.4M12 14v3M8 20h8M9.5 17h5" />
      </S>
    ),
  },
  tibbiyot: {
    colors: ['#f87171', '#dc2626'],
    icon: (
      <S>
        <path d="M12 20s-7.5-4.5-7.5-10A4.3 4.3 0 0 1 12 7.3 4.3 4.3 0 0 1 19.5 10c0 5.5-7.5 10-7.5 10z" />
        <path d="M7.5 12h2.5l1.2-2 1.6 4 1.2-2h2.5" />
      </S>
    ),
  },
  huquq: {
    colors: ['#a78bfa', '#6d28d9'],
    icon: (
      <S>
        <path d="M12 4v16M8 20h8M5 7h14M12 5.5 5 7M12 5.5 19 7" />
        <path d="m5 7-2.5 6a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z" />
      </S>
    ),
  },
  umumiy: {
    colors: ['#c084fc', '#7c3aed'],
    icon: (
      <S fill="currentColor">
        <path d="M12 2.5c.6 4.6 2.4 6.9 7 8-4.6 1.1-6.4 3.4-7 8-.6-4.6-2.4-6.9-7-8 4.6-1.1 6.4-3.4 7-8z" strokeWidth="0" />
        <path d="M19 15.5c.25 1.7.9 2.5 2.5 2.9-1.6.4-2.25 1.2-2.5 2.9-.25-1.7-.9-2.5-2.5-2.9 1.6-.4 2.25-1.2 2.5-2.9z" strokeWidth="0" />
      </S>
    ),
  },
};

const FALLBACK = ['#94a3b8', '#475569'];

/** Rangli kvadrat ichidagi belgi. */
export function CategoryBadge({ category, size = 44 }) {
  const item = ICONS[category.key];
  const [from, to] = item?.colors || FALLBACK;
  return (
    <span
      className="cat-badge"
      style={{ width: size, height: size, '--from': from, '--to': to }}
      aria-hidden="true"
    >
      {item ? item.icon : <span className="cat-badge__emoji">{category.emoji}</span>}
    </span>
  );
}
