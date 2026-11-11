// Til bayroqlari — SVG (emoji bayroqlar Windows'da «UZ», «RU», «GB» harflari bo'lib chiqadi)
const FLAGS = {
  uz: (
    <>
      <rect width="30" height="20" fill="#1eb53a" />
      <rect width="30" height="13.33" fill="#fff" />
      <rect width="30" height="6.67" fill="#0099b5" />
      <rect y="6.4" width="30" height="0.53" fill="#ce1126" />
      <rect y="13.07" width="30" height="0.53" fill="#ce1126" />
      <circle cx="5.2" cy="3.33" r="2.2" fill="#fff" />
      <circle cx="6" cy="3.33" r="2.2" fill="#0099b5" />
      <g fill="#fff">
        <circle cx="9" cy="4.9" r="0.42" />
        <circle cx="10.5" cy="4.9" r="0.42" />
        <circle cx="12" cy="4.9" r="0.42" />
        <circle cx="10.5" cy="3.4" r="0.42" />
        <circle cx="12" cy="3.4" r="0.42" />
        <circle cx="12" cy="1.9" r="0.42" />
      </g>
    </>
  ),
  ru: (
    <>
      <rect width="30" height="20" fill="#d52b1e" />
      <rect width="30" height="13.33" fill="#0039a6" />
      <rect width="30" height="6.67" fill="#fff" />
    </>
  ),
  en: (
    <>
      <clipPath id="flag-gb">
        <rect width="30" height="20" />
      </clipPath>
      <g clipPath="url(#flag-gb)">
        <rect width="30" height="20" fill="#012169" />
        <path d="M0 0 30 20M30 0 0 20" stroke="#fff" strokeWidth="4" />
        <path d="M0 0 30 20M30 0 0 20" stroke="#c8102e" strokeWidth="1.6" />
        <path d="M15 0v20M0 10h30" stroke="#fff" strokeWidth="6" />
        <path d="M15 0v20M0 10h30" stroke="#c8102e" strokeWidth="3.6" />
      </g>
    </>
  ),
};

export default function Flag({ lang, width = 22, className = 'flag' }) {
  const flag = FLAGS[lang];
  if (!flag) return null;
  return (
    <svg className={className} viewBox="0 0 30 20" width={width} height={Math.round((width * 2) / 3)} aria-hidden="true">
      {flag}
    </svg>
  );
}
