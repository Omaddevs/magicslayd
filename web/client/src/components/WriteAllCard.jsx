import { t } from '../lib/i18n.js';

/** Bitta tugma — butun ish (yoki qolgan qismlar) ketma-ket yoziladi, tayyor fayl Telegram chatga keladi.
 *  parts: [{ key, label, done }] — yozish tartibida (label allaqachon tarjima qilingan). */
export default function WriteAllCard({ parts, about, locked, onWrite }) {
  const written = parts.filter((p) => p.done).length;
  const next = parts.find((p) => !p.done);
  return (
    <section className="card write-all">
      <div className="write-all__icon" aria-hidden="true">✍️</div>
      <b className="write-all__title">{written ? t('Qolgan qismlarni yozish') : t('Butun ishni yozish')}</b>
      <p className="card__hint">
        {written
          ? t('{done}/{total} qism yozilgan. Qolganlari ({next} va keyingilari) bir bosishda yoziladi.', { done: written, total: parts.length, next: next?.label ?? '' })
          : t(about)}
      </p>
      <div className="write-all__parts">
        {parts.map((p) => (
          <span key={p.key} className={`write-all__part ${p.done ? 'write-all__part--done' : ''}`}>
            {p.done ? '✓ ' : ''}{p.label}
          </span>
        ))}
      </div>
      <button className="btn btn--primary mt-12" disabled={locked} onClick={onWrite}>
        ✍️ {written ? t('Qolganini yozish') : t('Hammasini yozish')}
      </button>
      <p className="card__hint mt-12">{t('Keyin istalgan qismni shu yerda tahrirlash, AI bilan kengaytirish yoki qayta yozdirish mumkin.')}</p>
    </section>
  );
}
