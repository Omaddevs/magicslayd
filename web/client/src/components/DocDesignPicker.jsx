import { useApp } from '../app/AppContext.jsx';
import { haptic } from '../lib/telegram.js';
import { t } from '../lib/i18n.js';

// Bot dizaynlari (diploma/designs.py) kelmagan bo'lsa — shu ro'yxat
const FALLBACK = [
  { key: 'classic', name: '📘 Klassik', about: "Times New Roman, qora sarlavhalar — ko'pchilik OTM talabi" },
  { key: 'frame', name: '🖼 Ramkali', about: 'Har bir sahifa chiziqli ramka ichida' },
  { key: 'modern', name: '🔷 Zamonaviy', about: "To'q ko'k sarlavhalar, bob nomi ostida chiziq" },
  { key: 'elegant', name: '✒️ Nafis', about: "Cambria shrift, to'q bordo sarlavhalar va qo'sh ramka" },
];

// Kichik sahifa namunasi: ramka, sarlavha rangi va chiziq — dizayn qanday ko'rinishini oldindan ko'rsatadi
const LOOK = {
  classic: { ink: '#111', rule: null, frame: null },
  frame: { ink: '#111', rule: null, frame: 'single' },
  modern: { ink: '#1F3864', rule: '#2E5597', frame: null },
  elegant: { ink: '#6B1E2B', rule: '#6B1E2B', frame: 'double' },
};

function PagePreview({ look }) {
  return (
    <span
      className={`doc-page ${look.frame ? `doc-page--${look.frame}` : ''}`}
      style={{ '--ink': look.ink, '--rule': look.rule || 'transparent', '--frame': look.ink }}
      aria-hidden="true"
    >
      <span className="doc-page__title" />
      <span className="doc-page__rule" />
      <span className="doc-page__line" />
      <span className="doc-page__line" />
      <span className="doc-page__line doc-page__line--short" />
      <span className="doc-page__line" />
    </span>
  );
}

/** «🎨 Boshqa dizaynda olish» — diplom ishi va dissertatsiya fayli uchun rasmiylashtirish dizayni.
 *  Tanlansa — fayl shu dizaynda qayta yig'iladi va Telegram chatga yuboriladi (matn o'zgarmaydi, pul yechilmaydi). */
export default function DocDesignPicker({ current, locked, onPick }) {
  const { boot } = useApp();
  const designs = boot.settings.doc_designs?.length ? boot.settings.doc_designs : FALLBACK;
  const active = designs.some((d) => d.key === current) ? current : 'classic';

  return (
    <section className="card">
      <div className="card__label">{t("🎨 Dizayn")}</div>
      <p className="card__hint">
        {t("Fayl ko'rinishini tanlang — matn o'zgarmaydi. Metodik qo'llanmadagi talablar (shrift o'lchami, interval, chekkalar) saqlanadi.")}
      </p>
      <div className="doc-designs mt-12">
        {designs.map((d) => {
          const on = d.key === active;
          return (
            <button
              key={d.key}
              className={`doc-design pressable ${on ? 'doc-design--active' : ''}`}
              disabled={locked}
              aria-pressed={on}
              onClick={() => {
                if (on) return;
                haptic('select');
                onPick(d.key);
              }}
            >
              <PagePreview look={LOOK[d.key] || LOOK.classic} />
              <span className="doc-design__name">{t(d.name)}</span>
              <span className="doc-design__about">{t(d.about)}</span>
              {on && <span className="doc-design__badge">{t("Tanlangan")}</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
