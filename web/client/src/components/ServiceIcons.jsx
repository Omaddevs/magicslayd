// «Xizmatlarimiz» plitkalaridagi hajmli belgilar: oq-yorug' gradient, yumshoq soya — rangli fon ustida.
const Defs = ({ id, from = '#ffffff', to = '#dcd6ff' }) => (
  <defs>
    <linearGradient id={`${id}-a`} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor={from} />
      <stop offset="1" stopColor={to} />
    </linearGradient>
    <filter id={`${id}-s`} x="-30%" y="-30%" width="160%" height="170%">
      <feDropShadow dx="0" dy="3" stdDeviation="2.4" floodColor="#000" floodOpacity="0.28" />
    </filter>
  </defs>
);

const ICONS = {
  pres: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-pres" to="#d8d0ff" />
      <g filter="url(#si-pres-s)">
        <rect x="6" y="8" width="36" height="24" rx="4" fill="url(#si-pres-a)" />
        <rect x="10" y="12" width="28" height="16" rx="2" fill="#6d4ff0" />
        <path d="M14 24l5-6 4 4 3-3 6 5z" fill="#c4b5fd" />
        <circle cx="31" cy="16" r="2" fill="#fde68a" />
        <path d="M24 32v6M17 40h14" stroke="url(#si-pres-a)" strokeWidth="3.2" strokeLinecap="round" />
      </g>
    </svg>
  ),
  referat: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-ref" to="#cfe0ff" />
      <g filter="url(#si-ref-s)">
        <path d="M12 6h17l9 9v25a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3z" fill="url(#si-ref-a)" />
        <path d="M29 6v6a3 3 0 0 0 3 3h6" fill="#9cc0ff" />
        <path d="M15 22h17M15 27.5h17M15 33h11" stroke="#3b82f6" strokeWidth="2.6" strokeLinecap="round" />
      </g>
    </svg>
  ),
  kurs: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-kurs" from="#fff3d6" to="#f6c86b" />
      <g filter="url(#si-kurs-s)">
        <path d="M24 9 4 18l20 9 20-9z" fill="url(#si-kurs-a)" />
        <path d="M12 22.5v9c0 3.5 5.4 6.5 12 6.5s12-3 12-6.5v-9L24 28z" fill="#e7a93a" />
        <path d="M41 19v12" stroke="#fff3d6" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="41" cy="33" r="2.6" fill="#fff3d6" />
      </g>
    </svg>
  ),
  diss: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-diss" to="#e3d6ff" />
      <g filter="url(#si-diss-s)">
        <path d="M24 13c-4-3-10-4-17-3v26c7-1 13 0 17 3 4-3 10-4 17-3V10c-7-1-13 0-17 3z" fill="url(#si-diss-a)" />
        <path d="M24 13v26" stroke="#a78bfa" strokeWidth="2.4" />
        <path d="M11 17c3.5-.4 6.5 0 9 1.2M11 22.5c3.5-.4 6.5 0 9 1.2M28 18.2c2.5-1.2 5.5-1.6 9-1.2M28 23.7c2.5-1.2 5.5-1.6 9-1.2" stroke="#b9a5f7" strokeWidth="2" strokeLinecap="round" />
      </g>
    </svg>
  ),
  diplom: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-dip" to="#c8f5ec" />
      <g filter="url(#si-dip-s)">
        <rect x="7" y="8" width="34" height="26" rx="4" fill="url(#si-dip-a)" />
        <path d="M13 15h22M13 20h14" stroke="#14b8a6" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="31" cy="29" r="6.5" fill="#fbbf24" />
        <circle cx="31" cy="29" r="3.4" fill="#fde68a" />
        <path d="M27.5 34.5 26 42l5-2.6 5 2.6-1.5-7.5" fill="#f59e0b" />
      </g>
    </svg>
  ),
  mustaqil: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-mus" to="#d3dcff" />
      <g filter="url(#si-mus-s)">
        <rect x="9" y="6" width="30" height="37" rx="4" fill="url(#si-mus-a)" />
        <path d="M15 16h18M15 22h18M15 28h12" stroke="#4f6bf5" strokeWidth="2.6" strokeLinecap="round" />
        <path d="m28 35 3.5 3.5L38 32" stroke="#22c55e" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  ),
  maqola: (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <Defs id="si-maq" to="#c9f0d6" />
      <g filter="url(#si-maq-s)">
        <rect x="8" y="6" width="28" height="36" rx="4" fill="url(#si-maq-a)" />
        <path d="M13 13h18" stroke="#16a34a" strokeWidth="2.8" strokeLinecap="round" />
        <rect x="13" y="18" width="8" height="7" rx="1.5" fill="#86d9a6" />
        <path d="M24 19h7M24 23.5h7M13 30h18M13 35h12" stroke="#4fb978" strokeWidth="2.2" strokeLinecap="round" />
        <path d="m31 37 10-10 3.5 3.5-10 10-4.8 1.3z" fill="#fbbf24" />
      </g>
    </svg>
  ),
};

export default function ServiceIcon({ kind }) {
  return <span className="svc__icon">{ICONS[kind]}</span>;
}
