import { useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { TileArt } from '../components/Art.jsx';
import { DownloadIcon, SparkIcon } from '../components/Icons.jsx';
import { TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { SERVICES } from '../lib/services.js';
import { getLang, t } from '../lib/i18n.js';
import { haptic, saveFile } from '../lib/telegram.js';

const POLL_MS = 2000;
const POLL_LIMIT_MS = 5 * 60 * 1000; // bot servisida har bir AI so'rovi 90 s bilan cheklangan — 5 daqiqa yetarli
const NETWORK_FAILS = 5;
const FILE_LABELS = { pptx: 'PowerPoint (.pptx)', docx: 'Word (.docx)', pdf: 'PDF' };
const STAGES = {
  pres: ['Mavzu tahlil qilinmoqda', 'Slaydlar rejasi tuzilmoqda', 'Matn yozilmoqda', 'Fayl tayyorlanmoqda'],
  doc: ['Mavzu tahlil qilinmoqda', 'Reja tuzilmoqda', "Bo'limlar yozilmoqda", 'Word va PDF tayyorlanmoqda'],
};

/** Formani tekshiradi (server bilan bir xil qoidalar) — { maydon: xato matni }. */
function validate(form, rules) {
  const errors = {};
  if (!rules.types[form.type]) errors.type = t('Ish turini tanlang.');
  const topic = form.topic.trim().replace(/\s+/g, ' ');
  if (topic.length < rules.topic_min) errors.topic = t("Mavzu kamida {n} ta belgidan iborat bo'lsin.", { n: rules.topic_min });
  else if (topic.length > rules.topic_max) errors.topic = t('Mavzu {n} belgidan oshmasin.', { n: rules.topic_max });
  if (form.subject.trim().length > rules.subject_max) errors.subject = t('Fan nomi {n} belgidan oshmasin.', { n: rules.subject_max });
  const limits = rules.types[form.type];
  if (limits && !(Number.isInteger(form.size) && form.size >= limits.min && form.size <= limits.max)) {
    errors.size = t("Hajm {min}–{max} {unit} oralig'ida bo'lsin.", { min: limits.min, max: limits.max, unit: t(limits.unit) });
  }
  if (!rules.languages[form.language]) errors.language = t('Tilni tanlang.');
  return errors;
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export default function Assistant() {
  const { boot, toast } = useApp();
  const rules = boot.settings.ai;
  const [form, setForm] = useState({ type: 'pres', topic: '', subject: '', size: rules.types.pres.default, language: rules.languages[getLang()] ? getLang() : 'uz' });
  const [errors, setErrors] = useState({});
  const [left, setLeft] = useState(null);
  const [phase, setPhase] = useState('form'); // form | loading | done | failed
  const [stage, setStage] = useState(0);
  const [outcome, setOutcome] = useState(null); // { result, files } | { error }
  const busy = useRef(false); // takroriy bosish ikkinchi so'rov yubormasin
  const alive = useRef(true);

  useEffect(() => {
    api('/ai/limits').then((data) => setLeft(data.left)).catch(() => {});
    return () => {
      alive.current = false;
    };
  }, []);

  // Kutish paytida bosqichlar almashib turadi
  useEffect(() => {
    if (phase !== 'loading') return undefined;
    setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, 3)), 6000);
    return () => clearInterval(timer);
  }, [phase]);

  const limits = rules.types[form.type];
  const set = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  function chooseType(type) {
    haptic('select');
    setForm((prev) => ({ ...prev, type, size: rules.types[type].default }));
    setErrors((prev) => ({ ...prev, type: undefined, size: undefined }));
  }

  async function poll(jobId) {
    const started = Date.now();
    let fails = 0;
    while (alive.current && Date.now() - started < POLL_LIMIT_MS) {
      await wait(POLL_MS);
      try {
        const job = await api(`/ai/jobs/${jobId}`);
        fails = 0;
        if (job.status === 'done') return { result: job.result, files: job.files };
        if (job.status === 'failed') return { error: t(job.error || t("Tayyorlab bo'lmadi. Qayta urinib ko'ring.")) };
      } catch (error) {
        fails += 1;
        if (fails >= NETWORK_FAILS) return { error: error.message };
      }
    }
    return { error: t("Javob juda kechikdi. Iltimos, qayta urinib ko'ring.") };
  }

  async function submit() {
    if (busy.current) return;
    const found = validate(form, rules);
    setErrors(found);
    if (Object.keys(found).length) {
      haptic('error');
      return;
    }
    busy.current = true;
    haptic('medium');
    setPhase('loading');
    try {
      const { jobId, left: rest } = await api('/ai/generate', { method: 'POST', body: form });
      setLeft(rest);
      const done = await poll(jobId);
      if (!alive.current) return;
      setOutcome(done);
      setPhase(done.error ? 'failed' : 'done');
      haptic(done.error ? 'error' : 'success');
    } catch (error) {
      // 400 — maydon xatosi formada, qolganlari (limit, internet) — xabar bilan
      if (error.data?.field) setErrors({ [error.data.field]: error.message });
      else toast(error.message, 'error');
      setPhase('form');
    } finally {
      busy.current = false;
    }
  }

  // ===== Kutish =====
  if (phase === 'loading') {
    const stages = STAGES[form.type === 'pres' ? 'pres' : 'doc'];
    return (
      <main className="page">
        <TopBar title={t('AI yordamchi')} />
        <div className="card preparing">
          <div className="spinner" />
          <b>{t('Tayyorlanmoqda...')}</b>
          <span className="card__hint">{t(stages[stage])} · {t('odatda 15–60 soniya')}</span>
        </div>
        <div className="card steps">
          {stages.map((text, i) => (
            <div key={text} className={`step ${i < stage ? 'step--done' : i === stage ? 'step--current' : ''}`}>
              <span className="step__dot">{i < stage && '✓'}</span>
              {t(text)}
            </div>
          ))}
        </div>
      </main>
    );
  }

  // ===== Natija =====
  if (phase === 'done' && outcome?.result) {
    const { result, files } = outcome;
    return (
      <main className="page ai-result">
        <TopBar title={t('AI yordamchi')} />
        <section className="card">
          <span className="badge">{t(limits.label)}</span>
          <h2 className="mt-12">{result.title}</h2>
        </section>

        {result.slides ? (
          <div className="list mt-12">
            {result.slides.map((slide, i) => (
              <div key={i} className="ai-slide">
                <span className="ai-slide__no">{i + 2}</span>
                <div>
                  <b>{slide.title}</b>
                  <ul>
                    {slide.bullets.map((bullet, j) => (
                      <li key={j}>{bullet}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <section className="card ai-doc">
            <h3 style={{ marginTop: 0 }}>{t('Reja')}</h3>
            <ol>
              {result.plan.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ol>
            {result.sections.map((section, i) => {
              const Heading = /^\d+\.\d+\./.test(section.heading) ? 'h4' : 'h3';
              return (
                <div key={i}>
                  <Heading>{section.heading}</Heading>
                  {section.content.split('\n\n').filter(Boolean).map((text, j) => (
                    <p key={j}>{text}</p>
                  ))}
                </div>
              );
            })}
            <h3>{result.plan[result.plan.length - 1]}</h3>
            <ol>
              {result.references.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ol>
          </section>
        )}

        <div className="note note--warn">⚠️ {t('AI tomonidan yaratilgan. Topshirishdan oldin tekshirib chiqing.')}</div>

        <section className="ai-downloads mt-16">
          {files.map((file, i) => (
            <button
              key={file.ext}
              className={`btn ${i === 0 ? 'btn--primary' : 'btn--white'}`}
              onClick={() => {
                haptic('medium');
                saveFile(file.url, file.name);
              }}
            >
              <DownloadIcon size={20} /> {FILE_LABELS[file.ext]}
            </button>
          ))}
          <button className="btn btn--soft" onClick={() => setPhase('form')}>
            <SparkIcon size={18} /> {t('Yangi yaratish')}
          </button>
        </section>
        {left !== null && <p className="card__hint mt-12" style={{ textAlign: 'center' }}>{t('Bugun yana {n} ta bepul yaratish mumkin.', { n: left })}</p>}
      </main>
    );
  }

  // ===== Forma =====
  const unit = t(limits.unit);
  return (
    <main className="page" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar title={t('AI yordamchi')} right={left !== null && <span className="badge">{t('Bepul')}: {left}</span>} />

      {phase === 'failed' && (
        <div className="note note--error" style={{ marginTop: 0, marginBottom: 12 }}>😕 {outcome?.error}</div>
      )}

      <section className="card">
        <div className="card__label">{t('Ish turi')}</div>
        <div className="ai-types">
          {Object.keys(rules.types).map((type) => (
            <button
              key={type}
              className={`ai-type tile--${SERVICES[type].color} ${form.type === type ? 'ai-type--active' : ''}`}
              onClick={() => chooseType(type)}
              aria-pressed={form.type === type}
            >
              <TileArt kind={type} className="" />
              {t(rules.types[type].label)}
            </button>
          ))}
        </div>
        {errors.type && <div className="field-error">{errors.type}</div>}
      </section>

      <section className="card">
        <label className="card__label" htmlFor="ai-topic">
          {t('Mavzu')} <span className="card__hint">{form.topic.trim().length}/{rules.topic_max}</span>
        </label>
        <textarea
          id="ai-topic"
          className={`field ${errors.topic ? 'field--error' : ''}`}
          rows={3}
          maxLength={rules.topic_max}
          placeholder={t('Masalan: Oʻzbekistonda turizmning rivojlanish istiqbollari')}
          value={form.topic}
          onChange={(e) => set('topic', e.target.value)}
        />
        {errors.topic && <div className="field-error">{errors.topic}</div>}

        <label className="field-label" htmlFor="ai-subject">{t('Fan (ixtiyoriy)')}</label>
        <input
          id="ai-subject"
          className={`field ${errors.subject ? 'field--error' : ''}`}
          maxLength={rules.subject_max}
          placeholder={t('Masalan: Turizm iqtisodiyoti')}
          value={form.subject}
          onChange={(e) => set('subject', e.target.value)}
        />
        {errors.subject && <div className="field-error">{errors.subject}</div>}
      </section>

      <section className="card">
        <div className="card__label">
          {t('Hajm')} <span className="card__hint">{limits.min}–{limits.max} {unit}</span>
        </div>
        <div className="stepper-input">
          <button onClick={() => set('size', Math.max(limits.min, form.size - 1))} disabled={form.size <= limits.min} aria-label={t('Kamaytirish')}>
            −
          </button>
          <input
            className={`field ${errors.size ? 'field--error' : ''}`}
            inputMode="numeric"
            value={Number.isNaN(form.size) ? '' : form.size}
            onChange={(e) => set('size', e.target.value === '' ? NaN : Number(e.target.value.replace(/\D/g, '')))}
            aria-label={`${t('Hajm')} (${unit})`}
          />
          <button onClick={() => set('size', Math.min(limits.max, (form.size || limits.min) + 1))} disabled={form.size >= limits.max} aria-label={t("Ko'paytirish")}>
            +
          </button>
          <span>{unit}</span>
        </div>
        {errors.size && <div className="field-error">{errors.size}</div>}
      </section>

      <section className="card">
        <div className="card__label">{t('Til')}</div>
        <div className="segment segment--wrap">
          {Object.entries(rules.languages).map(([key, name]) => (
            <button key={key} className={form.language === key ? 'segment--active' : ''} onClick={() => set('language', key)}>
              {name}
            </button>
          ))}
        </div>
        {errors.language && <div className="field-error">{errors.language}</div>}
      </section>

      <div className="bottom-bar">
        <button className="btn btn--primary" onClick={submit} disabled={busy.current || left === 0}>
          <SparkIcon size={20} /> {left === 0 ? t('Bugungi limit tugadi') : t('Yaratish')}
        </button>
      </div>
    </main>
  );
}
