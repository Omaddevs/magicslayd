import { getLang, t } from '../lib/i18n.js';
import SlideView from './SlideView.jsx';

/** Bot dizaynining (presentation/themes.py) kichik ko'rinishi — ranglar bazadan keladi.
 *  Shablonlar (style bor) o'z maketi bilan chiziladi — bot kollajidagi (presentation/preview.py) plitkalar kabi. */
export default function SlidePreview({ theme }) {
  // Tabiat shablonlari — haqiqiy muqova (SlideView) namuna foto bilan: kartochka taqdimotning o'ziga aynan mos
  if (['nature', 'heritage', 'sport', 'office', 'edu', 'tech', 'art', 'med', 'law'].includes(theme.style)) {
    // Namuna muqova matni — shablon sohasiga qarab
    const [title, subtitle] = {
      tarix: ["Buyuk ipak yo'li", 'Sivilizatsiyalar merosi'],
      sport: ['Sport kuchi', "Salomatlik, iroda va g'alaba"],
      ofis: ['Biznes reja', "Strategiya, bozor va o'sish"],
      talim: ["Ta'lim kelajagi", 'Bilim, innovatsiya va rivojlanish'],
      sanat: ["San'at olami", "Ijod, go'zallik va madaniyat"],
      tibbiyot: ["Sog'lom kelajak", "Zamonaviy tibbiyot va sog'liqni saqlash"],
      huquq: ['Qonun va adolat', 'Huquq, burch va jamiyat'],
      fan: ['Raqamli kelajak', "Sun'iy intellekt va texnologiyalar"],
    }[theme.category] ?? ['Tabiat va inson', 'Ekologiya va barqaror kelajak'];
    const deck = {
      theme,
      lang: getLang(),
      author: '',
      content: { title: t(title), subtitle: t(subtitle), cover_image: theme.sample ?? null, plans: [], conclusion: [] },
    };
    return (
      <div className="tpl tpl--nature" style={{ background: `#${theme.bg}` }}>
        <SlideView deck={deck} item={{ type: 'cover' }} index={1} total={10} media={(name) => name || null} />
      </div>
    );
  }
  if (theme.style && TEMPLATES[theme.style]) {
    const Template = TEMPLATES[theme.style];
    return (
      <div className={`tpl tpl--${theme.style}`} style={vars(theme)}>
        <Template t={theme} />
      </div>
    );
  }
  const c = (key) => `#${theme[key]}`;
  return (
    <div className="slide-preview" style={{ background: `linear-gradient(135deg, ${c('bg')}, ${c('bg2')})` }}>
      <div className="slide-preview__orb" style={{ background: `radial-gradient(circle, ${c('accent2')}, transparent 70%)` }} />
      <div className="slide-preview__bar" style={{ background: c('accent') }} />
      <div className="slide-preview__title" style={{ background: c('text') }} />
      <div className="slide-preview__line" style={{ width: '58%', background: c('muted') }} />
      <div className="slide-preview__line" style={{ width: '44%', background: c('muted') }} />
    </div>
  );
}

/** Shablon ranglari CSS o'zgaruvchilari sifatida (styles.css dagi .tpl--* shular bilan chiziladi). */
function vars(t) {
  const style = {};
  for (const key of ['bg', 'bg2', 'accent', 'accent2', 'card', 'text', 'muted', 'card_text', 'card_muted']) {
    if (t[key]) style[`--t-${key.replace('_', '-')}`] = `#${t[key]}`;
  }
  return style;
}

/** Namuna rasm: osmon, quyosh va tog'lar (haqiqiy taqdimotda bu joyga AI chizgan rasm tushadi). */
function Photo({ className, sky = ['#9cc9e8', '#3e7a55'] }) {
  const id = `sky-${sky.join('').replace(/#/g, '')}`;
  return (
    <svg className={className} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0" stopColor={sky[0]} />
          <stop offset="1" stopColor={sky[1]} />
        </linearGradient>
      </defs>
      <rect width="100" height="100" fill={`url(#${id})`} />
      <circle cx="70" cy="26" r="9" fill="rgba(255,255,255,0.75)" />
      <polygon points="0,100 35,48 62,100" fill="rgba(0,0,0,0.22)" />
      <polygon points="34,100 72,38 100,78 100,100" fill="rgba(0,0,0,0.32)" />
    </svg>
  );
}

const Sparkle = () => (
  <svg className="tpl__doodle tpl__doodle--sparkle" viewBox="0 0 40 40" aria-hidden="true">
    <path d="M20 2 C21 15 25 19 38 20 C25 21 21 25 20 38 C19 25 15 21 2 20 C15 19 19 15 20 2 Z" fill="none" stroke="#141414" strokeWidth="2.2" strokeLinejoin="round" />
  </svg>
);
const Spiral = () => (
  <svg className="tpl__doodle tpl__doodle--spiral" viewBox="0 0 40 40" aria-hidden="true">
    <path d="M20 20 m0 -2 a2 2 0 1 1 -2 2 a4 4 0 1 1 4 4 a6 6 0 1 1 -6 -6 a8 8 0 1 1 8 8 a10 10 0 1 1 -10 -10 a12 12 0 1 1 12 12" fill="none" stroke="#141414" strokeWidth="2" strokeLinecap="round" />
  </svg>
);
const Squiggle = () => (
  <svg className="tpl__doodle tpl__doodle--squiggle" viewBox="0 0 60 14" aria-hidden="true">
    <path d="M2 8 C8 0 12 0 16 7 S24 14 30 7 S40 0 44 7 S52 14 58 6" fill="none" stroke="#141414" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

/** Sarlavhani ikki qatorga bo'ladi (birinchi so'z — yuqorida), tarjimada ham kartochkaga sig'adi. */
const twoLines = (text) => {
  const i = text.indexOf(' ');
  return i < 0 ? text : <>{text.slice(0, i)}<br />{text.slice(i + 1)}</>;
};

const TEMPLATES = {
  corporate: () => (
    <>
      <div className="tpl__frame" />
      <span className="tpl__badge">{t('TAQDIMOT')}</span>
      <b className="tpl__title">{twoLines(t('Kompaniya taqdimoti'))}</b>
      <i className="tpl__row" />
      <i className="tpl__row tpl__row--2" />
      <div className="tpl__block" />
      <Photo className="tpl__photo" />
    </>
  ),
  doodle: () => (
    <>
      <span className="tpl__badge">{t('TAQDIMOT')}</span>
      <b className="tpl__banner">{t('Loyiha')}</b>
      <b className="tpl__banner tpl__banner--2">{t('taqdimoti')}</b>
      <div className="tpl__shadow" />
      <Photo className="tpl__photo" sky={['#ffd6ec', '#9ee8cf']} />
      <div className="tpl__rings" />
      <Sparkle />
      <Spiral />
      <Squiggle />
    </>
  ),
  vintage: () => (
    <>
      <div className="tpl__frame" />
      <div className="tpl__paper">
        <b className="tpl__title">{twoLines(t('TARIX SAHIFALARI'))}</b>
        <i className="tpl__rule" />
        <span className="tpl__sub">{t('XIV–XV asrlar')}</span>
      </div>
      <div className="tpl__polaroid">
        <Photo className="tpl__photo" sky={['#d8c8a8', '#6b4a2b']} />
      </div>
    </>
  ),
  baroque: () => (
    <>
      <div className="tpl__painting" />
      <div className="tpl__fade" />
      <div className="tpl__frame" />
      <span className="tpl__badge">{t('TAQDIMOT')}</span>
      <b className="tpl__title">{twoLines(t("Barokko san'ati"))}</b>
      <i className="tpl__rule" />
      <span className="tpl__sub">{t('Drama va nafosat')}</span>
    </>
  ),
};
