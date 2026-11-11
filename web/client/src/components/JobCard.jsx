import { t } from '../lib/i18n.js';

/** Bajarilayotgan AI vazifasi. «Hammasini yozish» da — qaysi qism yozilayotgani va umumiy jarayon chizig'i. */
export default function JobCard({ job, progress, text }) {
  const all = job.action === 'write_all';
  const share = all && progress?.total ? Math.max(4, Math.round((progress.done / progress.total) * 100)) : null;
  return (
    <div className="card preparing">
      <div className="spinner" />
      <b>{t(text[job.action] ?? 'Bajarilmoqda…')}</b>
      {all && progress && (
        <>
          <span className="job-progress__now">
            {progress.part === 'quality' ? t("Sifat nazorati o'tkazilmoqda") : `${progress.done + 1}/${progress.total} · ${progress.name}`}
          </span>
          <div className="job-progress" role="progressbar" aria-valuenow={share} aria-valuemin={0} aria-valuemax={100}>
            <span style={{ width: `${share}%` }} />
          </div>
        </>
      )}
      <span className="card__hint">
        {all
          ? t('Har bir bob odatda 1–3 daqiqada yoziladi. Tayyor fayl Telegram chatga keladi. Sahifani yopsangiz ham ish davom etadi.')
          : t('Sahifani yopsangiz ham ish davom etadi — natija saqlanadi.')}
      </span>
    </div>
  );
}
