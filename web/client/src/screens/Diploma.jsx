import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t } from '../lib/i18n.js';

import { useApp } from '../app/AppContext.jsx';
import DiplomaArt from '../components/DiplomaArt.jsx';
import DocDesignPicker from '../components/DocDesignPicker.jsx';
import Flag from '../components/Flag.jsx';
import JobCard from '../components/JobCard.jsx';
import WriteAllCard from '../components/WriteAllCard.jsx';
import { ChevronRight, CloseIcon, DownloadIcon, PlusIcon } from '../components/Icons.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api, apiUpload } from '../lib/api.js';
import { downloadFile } from '../lib/download.js';
import { clone, pollOrder } from '../lib/editing.js';
import { money, shortDate } from '../lib/format.js';
import { prepareImage } from '../lib/media.js';
import { confirmDialog, haptic } from '../lib/telegram.js';

// Diplom ishi: ma'lumotlar → metodika → reja → yozish (kirish, boblar, xulosa) → fayl.
// Matn va reja shu yerda tahrirlanadi va avtomatik saqlanadi; AI ishlari bot navbatida bajariladi (bot bilan bitta loyiha).

const STEPS = [
  ['info', "Ma'lumot"],
  ['method', 'Metodika'],
  ['plan', 'Reja'],
  ['write', 'Yozish'],
  ['file', 'Fayl'],
];
const FIELDS = [
  ['topic', 'Diplom ishi mavzusi', 'Masalan: Kichik biznesda raqamli marketing strategiyalari', 300],
  ['student', 'Talabaning F.I.Sh.', 'Aliyev Vali Karimovich', 200],
  ['university', 'Universitet yoki institut', 'Toshkent davlat iqtisodiyot universiteti', 200],
  ['faculty', 'Fakultet', 'Marketing fakulteti', 200],
  ['direction', "Ta'lim yo'nalishi", 'Marketing', 200],
  ['specialty', 'Mutaxassislik nomi va kodi', 'Marketing (60410500)', 200],
  ['course_group', 'Kursi va guruhi', '4-kurs, MR-21', 100],
  ['supervisor', 'Ilmiy rahbar F.I.Sh.', 'i.f.n., dots. Karimov A.B.', 200],
];
const LANGS = { uz: "O'zbekcha", ru: 'Русский', en: 'English' };
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'];
const AI_OPS = [
  ['expand', 'Kengaytirish'],
  ['shorten', 'Qisqartirish'],
  ['fix', 'Imloni tuzatish'],
  ['style', 'Uslubni yaxshilash'],
  ['regenerate', 'Qayta yozish'],
];
const JOB_TEXT = {
  analyze: 'Metodik qo\'llanma tahlil qilinmoqda…',
  plan: 'Reja tuzilmoqda… Odatda 15–40 soniya.',
  approve_plan: 'Reja tasdiqlanmoqda, haqiqiy ilmiy manbalar qidirilmoqda…',
  generate: 'Matn yozilmoqda… Bob uchun odatda 30–90 soniya.',
  write_all: 'Diplom ishi yozilmoqda…',
  rewrite: 'Xatboshi qayta ishlanmoqda…',
  sources: 'Ilmiy manbalar qidirilmoqda…',
  export: 'Fayl tayyorlanmoqda va Telegram chatga yuborilmoqda…',
  design: 'Fayl yangi dizaynda yig\'ilmoqda va Telegram chatga yuborilmoqda…',
};
const SAVE_DELAY = 1200;
const STAGE_LABEL = { info: "Ma'lumotlar", plan: 'Reja', writing: 'Yozilmoqda', done: '✅ Tayyor' };

const partKeys = (p) => ['intro', ...p.chapters.map((_, i) => `chapter:${i}`), 'conclusion'];
const partOf = (p, key) => (key === 'intro' ? p.intro : key === 'conclusion' ? p.conclusion : p.chapters[Number(key.slice(8))]);
const partLabel = (p, key) => (key === 'intro' ? t('Kirish#qism') : key === 'conclusion' ? t("Xulosa") : t('{n} bob', { n: ROMAN[Number(key.slice(8))] }));
function hasText(p, key) {
  const part = partOf(p, key);
  if (key === 'intro') return part.items.length > 0;
  if (key === 'conclusion') return part.paragraphs.length > 0;
  return part.sections.some((s) => s.paragraphs.length);
}
const rowsFor = (text) => Math.min(14, Math.max(3, Math.ceil((text?.length ?? 0) / 42)));
const stepOf = (p) => (p.stage === 'info' ? (p.plan.chapters.length ? 'plan' : 'info') : p.stage === 'plan' ? 'plan' : p.stage === 'done' ? 'file' : 'write');

// ===== Ro'yxat (diplom tanlash yoki yangisi) =====
export default function Diploma({ diplomaId, documentId }) {
  const { toast } = useApp();
  const [id, setId] = useState(diplomaId ?? null);

  useEffect(() => {
    if (!id && documentId) {
      api(`/diplomas/by-document/${documentId}`).then((d) => setId(d.id)).catch((e) => toast(e.message, 'error'));
    }
  }, [id, documentId, toast]);

  if (id) return <DiplomaProject id={id} onBack={diplomaId ? null : () => setId(null)} />;
  if (documentId) return <main className="page"><TopBar title={t("Diplom ishi")} /><Skeleton height={80} count={3} /></main>;
  return <DiplomaList onOpen={setId} />;
}

function DiplomaHero({ compact }) {
  return (
    <div className={`diploma-hero ${compact ? 'diploma-hero--compact' : ''}`}>
      <div className="diploma-hero__text">
        <b>{t("Diplom ishi")}</b>
        <span>{compact ? t("Mavzudan tayyor DOCX gacha — bosqichma-bosqich") : t("Reja, kirish, boblar, xulosa, haqiqiy ilmiy manbalar va DOCX/PDF — har bir bosqichni o'zingiz tasdiqlaysiz")}</span>
      </div>
      <DiplomaArt className="diploma-hero__art" />
    </div>
  );
}

function DiplomaList({ onOpen }) {
  const { boot, toast } = useApp();
  const [items, setItems] = useState(null);
  const [topic, setTopic] = useState('');
  const [busy, setBusy] = useState(false);
  const cfg = boot.settings.diploma ?? { page_price: 700, min: 40, max: 150 };

  useEffect(() => {
    api('/diplomas').then((d) => setItems(d.diplomas)).catch(() => setItems([]));
  }, []);

  async function create() {
    const clean = topic.trim().replace(/\s+/g, ' ');
    if (clean.length < 5) {
      toast(t("Mavzu kamida 5 belgi bo'lsin"), 'error');
      return;
    }
    setBusy(true);
    try {
      const { id } = await api('/diplomas', { method: 'POST', body: { topic: clean } });
      haptic('success');
      onOpen(id);
    } catch (error) {
      toast(error.message, 'error');
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <TopBar title={t("Diplom ishi")} />
      <DiplomaHero />
      <section className="card">
        <div className="card__label">{t("Yangi diplom ishi")}</div>
        <textarea className="field" rows={3} maxLength={300} placeholder={t(FIELDS[0][2])} value={topic} onChange={(e) => setTopic(e.target.value)} />
        <button className="btn btn--primary mt-12" onClick={create} disabled={busy}>
          {busy ? t("Yaratilmoqda…") : t("Boshlash")} <ChevronRight size={18} />
        </button>
        <p className="card__hint mt-12">
          {t("Narxi — har bir bet {price} ({min}–{max} bet). Ma'lumotlar va reja bepul, pul faqat reja tasdiqlanganda bir marta yechiladi.", { price: money(cfg.page_price), min: cfg.min, max: cfg.max })}
        </p>
      </section>
      {items === null ? (
        <Skeleton height={64} count={2} />
      ) : items.length > 0 && (
        <>
          <div className="section-head"><h2>{t("Boshlangan ishlarim")}</h2></div>
          <div className="list">
            {items.map((d) => (
              <button key={d.id} className="item item--button pressable" onClick={() => onOpen(d.id)}>
                <span className="diploma-badge">🎓</span>
                <div className="item__body">
                  <div className="item__title">{d.title || t("Mavzusiz")}</div>
                  <div className="item__meta">{t(STAGE_LABEL[d.stage] ?? "Ma'lumotlar")} · {d.pages} {t('bet')} · {shortDate(d.updated_at)}</div>
                </div>
                <ChevronRight size={20} />
              </button>
            ))}
          </div>
        </>
      )}
    </main>
  );
}

// ===== Loyiha =====
function DiplomaProject({ id, onBack }) {
  const { boot, toast, topup, setLeaveGuard } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [project, setProject] = useState(null);
  const [step, setStep] = useState(null);
  const [job, setJob] = useState(null); // { id, action }
  const timers = useRef({});
  const pending = useRef({});
  const projectRef = useRef(null);
  projectRef.current = project;

  const apply = useCallback((view) => {
    setData(view);
    setProject(view.project);
    return view;
  }, []);

  const reload = useCallback(() => api(`/diplomas/${id}`).then(apply), [id, apply]);

  // ===== Avtomatik saqlash (har bir soha alohida, 1.2 s kechikish bilan) =====
  const savers = useMemo(() => ({
    info: (p) => api(`/diplomas/${id}/info`, { method: 'PUT', body: p.info }),
    plan: (p) => api(`/diplomas/${id}/plan`, { method: 'PUT', body: { chapters: p.plan.chapters } }),
  }), [id]);

  const saveNow = useCallback(async (area) => {
    clearTimeout(timers.current[area]);
    delete pending.current[area];
    const p = projectRef.current;
    try {
      let view;
      if (area.startsWith('part:')) {
        const key = area.slice(5);
        const target = partOf(p, key);
        const body = key === 'intro' ? { items: target.items } : key === 'conclusion' ? { paragraphs: target.paragraphs }
          : { sections: target.sections, summary: target.summary, figures: target.figures };
        view = await api(`/diplomas/${id}/part`, { method: 'PUT', body: { part: key, data: body } });
      } else {
        view = await savers[area](p);
      }
      setData((d) => ({ ...d, ...view, project: d.project }));
    } catch (err) {
      toast(err.message, 'error');
    }
  }, [id, savers, toast]);

  const schedule = useCallback((area) => {
    pending.current[area] = true;
    clearTimeout(timers.current[area]);
    timers.current[area] = setTimeout(() => saveNow(area), SAVE_DELAY);
  }, [saveNow]);

  const flush = useCallback(async () => {
    await Promise.all(Object.keys(pending.current).map((area) => saveNow(area)));
  }, [saveNow]);

  const edit = useCallback((area, fn) => {
    setProject((prev) => {
      const next = clone(prev);
      fn(next);
      return next;
    });
    schedule(area);
  }, [schedule]);

  // ===== AI vazifasi (bot navbati) =====
  const waitJob = useCallback(async (orderId, action) => {
    setJob({ id: orderId, action });
    try {
      await pollOrder(orderId);
      haptic('success');
      if (action === 'write_all') toast(t("🎉 Diplom ishi tayyor! DOCX fayl Telegram chatga yuborildi."));
      return true;
    } catch (err) {
      toast(err.message, 'error');
      return false;
    } finally {
      setJob(null);
      await reload().catch(() => {});
    }
  }, [reload, toast]);

  const runJob = useCallback(async (action, extra = {}) => {
    await flush();
    try {
      const { orderId } = await api(`/diplomas/${id}/jobs`, { method: 'POST', body: { action, ...extra } });
      return await waitJob(orderId, action);
    } catch (err) {
      if (err.status === 402) {
        toast(err.message, 'error');
        topup(err.data.need);
      } else if (err.status === 409 && err.data.orderId) {
        return waitJob(err.data.orderId, 'generate');
      } else {
        toast(err.message, 'error');
      }
      return false;
    }
  }, [flush, id, toast, topup, waitJob]);

  useEffect(() => {
    let alive = true;
    api(`/diplomas/${id}`)
      .then((view) => {
        if (!alive) return;
        apply(view);
        setStep(stepOf(view.project));
        const active = view.jobs[0];
        if (active) waitJob(active.id, active.action);
      })
      .catch((err) => alive && setError(err));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Butun ish yozilayotganda — qaysi qism yozilayotgani va tayyor bo'lgan qismlar ko'rinib tursin
  useEffect(() => {
    if (job?.action !== 'write_all') return undefined;
    const timer = setInterval(() => reload().catch(() => {}), 8000);
    return () => clearInterval(timer);
  }, [job, reload]);

  // Chiqib ketishdan oldin kutilayotgan o'zgarishlar saqlab olinadi (so'ralmaydi — hammasi avtomatik saqlanadi)
  useEffect(() => {
    setLeaveGuard(async () => {
      await flush();
      return true;
    });
    return () => {
      setLeaveGuard(null);
      Object.values(timers.current).forEach(clearTimeout);
    };
  }, [flush, setLeaveGuard]);

  if (error) {
    return <main className="page"><TopBar title={t("Diplom ishi")} /><Empty icon="🎓" title={t("Ochib bo'lmadi")} text={error.message} /></main>;
  }
  if (!project) {
    return <main className="page"><TopBar title={t("Diplom ishi")} /><Skeleton height={90} count={4} /></main>;
  }

  const locked = Boolean(job);
  const reached = { info: true, method: true, plan: true, write: project.plan.approved, file: project.plan.approved && hasText(project, 'intro') };
  const props = { project, data, edit, runJob, locked, setStep, flush, reload, id, settings: boot.settings };

  return (
    <main className="page diploma" style={{ paddingBottom: 'calc(40px + var(--safe-bottom))' }}>
      <TopBar title={t("Diplom ishi")} right={onBack && <button className="link-btn" onClick={onBack}>{t("Ro'yxat")}</button>} />
      <DiplomaHero compact />
      <div className="stepper" role="tablist">
        {STEPS.map(([key, label], i) => (
          <button
            key={key}
            role="tab"
            className={`stepper__item ${step === key ? 'stepper__item--active' : ''} ${reached[key] ? '' : 'stepper__item--off'}`}
            onClick={() => {
              if (!reached[key]) {
                toast(key === 'file' ? t("Avval kirish qismini yozing") : t("Avval rejani tasdiqlang"));
                return;
              }
              haptic('select');
              flush();
              setStep(key);
            }}
          >
            <span className="stepper__num">{i + 1}</span>
            {t(label)}
          </button>
        ))}
      </div>

      {job && <JobCard job={job} progress={project.progress} text={JOB_TEXT} />}

      {step === 'info' && <InfoStep {...props} />}
      {step === 'method' && <MethodStep {...props} />}
      {step === 'plan' && <PlanStep {...props} />}
      {step === 'write' && <WriteStep {...props} />}
      {step === 'file' && <FileStep {...props} />}
    </main>
  );
}

// ===== 1. Ma'lumotlar =====
function InfoStep({ project, edit, locked, setStep, settings }) {
  const cfg = settings.diploma ?? { page_price: 700, min: 40, max: 150, options: [50, 60, 70, 80, 90, 100] };
  const info = project.info;
  const fixed = project.plan.approved;
  const [custom, setCustom] = useState(cfg.options.includes(info.pages) ? '' : String(info.pages));
  const set = (key, value) => edit('info', (p) => { p.info[key] = value; });

  return (
    <>
      <section className="card">
        <div className="card__label">{t("Asosiy ma'lumotlar")}</div>
        {FIELDS.map(([key, label, hint, max]) => (
          <label key={key} className="editor-field">
            <span className="field-label">{t(label)}{key !== 'topic' && <span className="card__hint"> {t("· ixtiyoriy")}</span>}</span>
            {key === 'topic' ? (
              <textarea className="field" rows={2} maxLength={max} placeholder={t(hint)} value={info[key] ?? ''} disabled={locked} onChange={(e) => set(key, e.target.value)} />
            ) : (
              <input className="field" maxLength={max} placeholder={t(hint)} value={info[key] ?? ''} disabled={locked} onChange={(e) => set(key, e.target.value)} />
            )}
          </label>
        ))}
      </section>

      <section className="card">
        <div className="card__label">{t("Til")}</div>
        <div className="segment">
          {Object.entries(LANGS).map(([key, label]) => (
            <button key={key} className={info.lang === key ? 'segment--active' : ''} disabled={locked || fixed} onClick={() => { haptic('select'); set('lang', key); }}>
              <Flag lang={key} /> {label}
            </button>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card__label">{t("Hajmi")} <span className="card__hint">{t('har bir bet {price}', { price: money(cfg.page_price) })}</span></div>
        <div className="options">
          {cfg.options.map((n) => (
            <button key={n} className={`option ${info.pages === n ? 'option--active' : ''}`} disabled={locked || fixed}
              onClick={() => { haptic('select'); setCustom(''); set('pages', n); }}>
              <b>{n} {t('bet')}</b>
              <span>{money(n * cfg.page_price)}</span>
            </button>
          ))}
        </div>
        <label className="editor-field">
          <span className="field-label">{t("Yoki o'zingiz kiriting ({min}–{max} bet)", { min: cfg.min, max: cfg.max })}</span>
          <input className="field" inputMode="numeric" maxLength={3} placeholder={t("Masalan: 65")} value={custom} disabled={locked || fixed}
            onChange={(e) => {
              const value = e.target.value.replace(/\D/g, '');
              setCustom(value);
              const n = Number(value);
              if (n >= cfg.min && n <= cfg.max) set('pages', n);
            }} />
        </label>
        {custom && (Number(custom) < cfg.min || Number(custom) > cfg.max) && (
          <p className="note note--warn">{cfg.min} dan {cfg.max} gacha son kiriting.</p>
        )}
        {fixed && <p className="card__hint mt-12">{t("Reja tasdiqlangan — til va hajm endi o'zgarmaydi.")}</p>}
      </section>

      <section className="card">
        <div className="card__label">{t("Qo'shimcha talablar")} <span className="card__hint">{t('ixtiyoriy')}</span></div>
        <textarea className="field" rows={3} maxLength={1000} placeholder={t("Masalan: amaliy qism «Artel» korxonasi misolida bo'lsin")}
          value={info.extra ?? ''} disabled={locked} onChange={(e) => set('extra', e.target.value)} />
        <p className="card__hint mt-12">{t("O'zgarishlar avtomatik saqlanadi.")}</p>
      </section>

      <button className="btn btn--primary" onClick={() => setStep('method')}>
        {t('Davom etish')} <ChevronRight size={18} />
      </button>
    </>
  );
}

// ===== 2. Metodika va materiallar =====
function MethodStep({ project, id, runJob, locked, setStep, reload }) {
  const { toast } = useApp();
  const [uploading, setUploading] = useState(null);
  const method = project.method;
  const input = useRef();
  const target = useRef('method');

  function pick(purpose) {
    target.current = purpose;
    input.current.accept = purpose === 'method' ? '.pdf,.docx,.txt' : '.pdf,.docx,.xlsx,.csv,.txt';
    input.current.value = '';
    input.current.click();
  }

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      toast(t("Fayl 20 MB dan oshmasin"), 'error');
      return;
    }
    setUploading(target.current);
    try {
      await apiUpload(`/diplomas/${id}/upload?purpose=${target.current}`, file, { 'X-File-Name': encodeURIComponent(file.name) });
      haptic('success');
      await reload();
      if (target.current === 'method') await runJob('analyze');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(null);
    }
  }

  async function removeMaterial(file) {
    try {
      await api(`/diplomas/${id}/material/${file}`, { method: 'DELETE' });
      await reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <>
      <input ref={input} type="file" hidden onChange={onFile} />
      <section className="card">
        <div className="card__label">{t("Universitet metodik qo'llanmasi")} <span className="card__hint">{t("PDF yoki DOCX")}</span></div>
        {method.file ? (
          <p className="card__hint">📘 <b>{method.name}</b> — {method.status === 'analyzed' ? t('tahlil qilingan, {n} ta talab topildi', { n: method.found.length }) : method.status === 'uploaded' ? t("yuklangan, tahlil qilinmagan") : t("aniq talablar topilmadi")}</p>
        ) : (
          <p className="card__hint">{t("Qo'llanma yuklanmasa, namunaviy tuzilma va keng tarqalgan talablar ishlatiladi (bu alohida ko'rsatiladi).")}</p>
        )}
        <div className="btn-grid mt-12">
          <button className="btn btn--soft btn--sm" disabled={locked || Boolean(uploading) || project.plan.approved} onClick={() => pick('method')}>
            {uploading === 'method' ? t("Yuklanmoqda…") : method.file ? t("📘 Boshqa fayl") : t("📘 Qo'llanmani yuklash")}
          </button>
          {method.status === 'uploaded' && (
            <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => runJob('analyze')}>{t("🔍 Tahlil qilish")}</button>
          )}
        </div>
        {method.found.length > 0 && (
          <div className="rules">
            {method.found.map((rule, i) => (
              <details key={i} className="rule">
                <summary><b>{rule.label}:</b> {rule.value}</summary>
                <blockquote>«{rule.quote}»</blockquote>
              </details>
            ))}
            <p className="card__hint">{t("Faqat qo'llanmada yozilgan talablar olinadi — har biri asl matndan iqtibos bilan.")}</p>
          </div>
        )}
        {method.notes && <p className="note note--info">{method.notes}</p>}
      </section>

      <section className="card">
        <div className="card__label">{t("Amaliy qism uchun materiallar")} <span className="card__hint">{t('ixtiyoriy')}</span></div>
        <p className="card__hint">{t("Korxona hisobotlari, statistika, so'rovnoma natijalari (Excel, CSV, PDF, DOCX). AI faqat shu ma'lumotlarga tayanadi va manbasini ko'rsatadi — hech qanday raqam o'ylab topilmaydi.")}</p>
        {(project.materials ?? []).map((m) => (
          <div key={m.file} className="item-row">
            <span className="material">📎 {m.name}</span>
            <button className="icon-btn icon-btn--ghost" disabled={locked} onClick={() => removeMaterial(m.file)} aria-label={t("O'chirish")}><CloseIcon size={18} /></button>
          </div>
        ))}
        <button className="btn btn--soft btn--sm mt-12" disabled={locked || Boolean(uploading)} onClick={() => pick('material')}>
          {uploading === 'material' ? t("Yuklanmoqda…") : t("📎 Material qo'shish")}
        </button>
      </section>

      <button className="btn btn--primary" onClick={() => setStep('plan')}>
        {t("Rejaga o'tish")} <ChevronRight size={18} />
      </button>
    </>
  );
}

// ===== 3. Reja =====
function PlanStep({ project, data, edit, runJob, locked, setStep }) {
  const plan = project.plan;
  const approved = plan.approved;
  const lockedPlan = locked || approved;
  const set = (fn) => edit('plan', (p) => fn(p.plan.chapters));

  if (!plan.chapters.length) {
    return (
      <section className="card">
        <div className="card__label">{t("Reja")}</div>
        <p className="card__hint">{t("AI mavzuni tahlil qilib, aynan shu mavzuga mos boblar va paragraflarni taklif qiladi. Rejani o'zgartirishingiz va qayta tuzdirishingiz mumkin — bu bepul.")}</p>
        <button className="btn btn--primary mt-12" disabled={locked || project.info.topic.trim().length < 5} onClick={() => runJob('plan')}>
          📋 Reja tuzish (bepul)
        </button>
      </section>
    );
  }

  return (
    <>
      <div className={`note ${project.method.status === 'analyzed' ? 'note--info' : 'note--warn'}`} style={{ marginTop: 0 }}>
        {project.method.status === 'analyzed'
          ? t("✅ Reja metodik qo'llanma talablari asosida tuzildi.")
          : t("ℹ️ Metodik qo'llanma yuklanmagan — bu namunaviy tuzilma. Universitet talablari boshqacha bo'lsa, qo'llanmani yuklab, qayta tuzing.")}
      </div>
      <section className="card">
        <div className="card__label">{t("Kirish")}</div>
        {plan.chapters.map((chapter, ci) => (
          <div key={ci} className="plan-chapter">
            <div className="item-edit__head">
              <b>{ROMAN[ci]}</b>
              <input className="field" maxLength={300} value={chapter.title} disabled={lockedPlan} onChange={(e) => set((c) => { c[ci].title = e.target.value; })} />
              {!lockedPlan && plan.chapters.length > 1 && (
                <button className="icon-btn icon-btn--ghost" aria-label={t("Bobni o'chirish")}
                  onClick={async () => { if (await confirmDialog(t("{n} bobni o'chirasizmi?", { n: ROMAN[ci] }))) set((c) => { c.splice(ci, 1); }); }}>
                  <CloseIcon size={18} />
                </button>
              )}
            </div>
            {chapter.sections.map((section, si) => (
              <div key={si} className="plan-section">
                <span>{ci + 1}.{si + 1}.</span>
                <input className="field" maxLength={300} value={section.title} disabled={lockedPlan} onChange={(e) => set((c) => { c[ci].sections[si].title = e.target.value; })} />
                {!lockedPlan && chapter.sections.length > 1 && (
                  <button className="icon-btn icon-btn--ghost" aria-label={t("Paragrafni o'chirish")} onClick={() => set((c) => { c[ci].sections.splice(si, 1); })}>
                    <CloseIcon size={16} />
                  </button>
                )}
              </div>
            ))}
            {!lockedPlan && chapter.sections.length < 8 && (
              <button className="link-btn" onClick={() => set((c) => { c[ci].sections.push({ title: t('Yangi paragraf') }); })}>
                <PlusIcon size={14} /> {t("Paragraf qo'shish")}
              </button>
            )}
          </div>
        ))}
        {!lockedPlan && plan.chapters.length < 7 && (
          <button className="btn btn--soft btn--sm mt-12" onClick={() => set((c) => { c.push({ title: t('Yangi bob'), sections: [{ title: t('Yangi paragraf') }] }); })}>
            <PlusIcon size={16} /> {t("Bob qo'shish")}
          </button>
        )}
        <div className="card__label mt-12">{t("Xulosa · Foydalanilgan adabiyotlar")}</div>
      </section>

      {approved ? (
        <button className="btn btn--primary" onClick={() => setStep('write')}>{t("Yozishga o'tish")} <ChevronRight size={18} /></button>
      ) : (
        <section className="card">
          <div className="summary-row">{t("Narxi")} <b>{data.price ? money(data.price) : 'bepul'}</b></div>
          <div className="summary-row">{t("Balansingiz")} <b>{money(data.balance)}</b></div>
          <p className="card__hint">{t("Tasdiqlagach pul bir marta yechiladi va yozish boshlanadi. Shundan keyin reja tuzilmasi o'zgarmaydi.")}</p>
          <div className="btn-grid mt-12">
            <button className="btn btn--soft btn--sm" disabled={locked}
              onClick={async () => { if (await confirmDialog(t("Reja qaytadan tuzilsinmi? Hozirgi o'zgarishlar almashtiriladi."))) runJob('plan'); }}>
              {t("🔄 Qayta tuzish")}
            </button>
            <button className="btn btn--primary btn--sm" disabled={locked}
              onClick={async () => {
                if (!(await confirmDialog(t('Rejani tasdiqlaysizmi? {pay} Keyin butun ish avtomatik yoziladi.', { pay: data.price ? t('{sum} yechiladi.', { sum: money(data.price) }) : '' })))) return;
                if (await runJob('approve_plan')) {
                  setStep('write');
                  runJob('write_all');
                }
              }}>
              {t("✅ Tasdiqlash")}
            </button>
          </div>
        </section>
      )}
    </>
  );
}

// ===== 4. Yozish =====
function Paragraphs({ list, onChange, disabled, onAi, labelFirst }) {
  return list.map((text, i) => (
    <div key={i} className="item-edit">
      <div className="item-edit__head">
        <b>{i + 1}</b>
        <span className="paper-para__hint">{i === 0 && labelFirst ? labelFirst : 'xatboshi'}</span>
        {onAi && (
          <select className="ai-select" disabled={disabled} value="" aria-label={t("AI amali")}
            onChange={(e) => e.target.value && onAi(i, e.target.value)}>
            <option value="">{t("✨ AI")}</option>
            {AI_OPS.map(([op, label]) => <option key={op} value={op}>{t(label)}</option>)}
          </select>
        )}
        <button className="icon-btn icon-btn--ghost" aria-label={t("Xatboshini o'chirish")} disabled={disabled || list.length <= 1}
          onClick={async () => { if (await confirmDialog(t("Bu xatboshini o'chirasizmi?"))) onChange((l) => { l.splice(i, 1); }); }}>
          <CloseIcon size={18} />
        </button>
      </div>
      <textarea className="field" rows={rowsFor(text)} maxLength={6000} value={text} disabled={disabled}
        onChange={(e) => onChange((l) => { l[i] = e.target.value; })} />
    </div>
  ));
}

const partAnchor = (key) => `dpart-${key.replace(':', '-')}`;
const scrollToPart = (key) => document.getElementById(partAnchor(key))?.scrollIntoView({ behavior: 'smooth', block: 'start' });

/** Yozish: butun ish (kirish, barcha boblar, xulosa) bitta ustunda — har bir bobga alohida kirish shart emas.
 *  Yuqoridagi chiplar faqat kerakli joyga tez o'tish uchun. */
function WriteStep({ project, data, edit, runJob, locked, setStep, id, reload, flush }) {
  const keys = partKeys(project);
  const [tab, setTab] = useState('text');
  const anyWritten = keys.some((k) => hasText(project, k));
  const allApproved = keys.every((k) => partOf(project, k).status === 'approved');

  function afterApprove(view) {
    const next = partKeys(view.project).find((k) => partOf(view.project, k).status !== 'approved');
    if (next) setTimeout(() => scrollToPart(next), 50);
    else setStep('file');
  }

  return (
    <>
      <div className="chips chips--scroll part-nav">
        {keys.map((k) => {
          const status = partOf(project, k).status;
          return (
            <button key={k} className="chip chip--pill"
              onClick={() => { haptic('select'); setTab('text'); setTimeout(() => scrollToPart(k), 0); }}>
              {status === 'approved' ? '✅ ' : hasText(project, k) ? '✏️ ' : ''}{partLabel(project, k)}
            </button>
          );
        })}
        <button className={`chip chip--pill ${tab === 'sources' ? 'chip--active' : ''}`} onClick={() => setTab(tab === 'sources' ? 'text' : 'sources')}>
          📚 {t('Manbalar')} ({project.sources.length})
        </button>
      </div>

      {tab === 'sources' ? (
        <SourcesPanel project={project} id={id} runJob={runJob} locked={locked} reload={reload} />
      ) : !anyWritten ? (
        <WriteAllCard
          parts={keys.map((k) => ({ key: k, label: partLabel(project, k), done: hasText(project, k) }))}
          about="Kirish, barcha boblar (mavzuga mos rasm, sxema va jadvallar bilan) va xulosa ketma-ket yoziladi. Tayyor DOCX fayl Telegram chatga keladi."
          locked={locked} onWrite={() => runJob('write_all')} />
      ) : (
        <>
          <section className="card">
            <p className="card__hint">{t("Butun ish shu yerda — yuqoridan pastga. Matnni bevosita tahrirlang (avtomatik saqlanadi) yoki xatboshi yonidagi «✨ AI» orqali kengaytiring, qisqartiring, imlosini tuzating. Tasdiqlangan matn sizning roziligingizsiz o'zgartirilmaydi.")}</p>
          </section>
          {keys.map((k) => (
            <WritePart key={k} partKey={k} project={project} data={data} edit={edit} runJob={runJob} locked={locked}
              id={id} reload={reload} flush={flush} onApproved={afterApprove} />
          ))}
          {allApproved && (
            <button className="btn btn--primary mt-12" onClick={() => setStep('file')}>{t("Faylga o'tish")} <ChevronRight size={18} /></button>
          )}
        </>
      )}
    </>
  );
}

/** Bitta qism (kirish / bob / xulosa) — umumiy ustunning bir bo'lagi. */
function WritePart({ partKey: key, project, data, edit, runJob, locked, id, reload, flush, onApproved }) {
  const { toast } = useApp();
  const current = partOf(project, key);
  const written = hasText(project, key);
  const area = `part:${key}`;
  const input = useRef();
  const figTarget = useRef(null);

  const ai = (address) => (i, op) => runJob('rewrite', { part: key, op, address: { ...address, paragraph: i } });

  async function approve(approved) {
    try {
      await flush();
      await api(`/diplomas/${id}/approve-part`, { method: 'POST', body: { part: key, approved } });
      haptic('success');
      const view = await reload();
      if (approved) onApproved(view);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function onFigure(e) {
    const file = e.target.files?.[0];
    const fid = figTarget.current;
    if (!file || !fid) return;
    try {
      const { file: name } = await apiUpload(`/diplomas/${id}/upload?purpose=figure`, await prepareImage(file));
      edit(area, (p) => { const f = partOf(p, key).figures.find((x) => x.id === fid); if (f) f.file = name; });
      haptic('success');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  const head = (
    <div className="part-head" id={partAnchor(key)}>
      <h2>{partLabel(project, key)}{key.startsWith('chapter:') && current.title ? `. ${current.title}` : ''}</h2>
      {written && (
        <span className={`badge ${current.status === 'approved' ? '' : 'badge--warn'}`}>{current.status === 'approved' ? t('Tasdiqlangan#holat') : t('Qoralama')}</span>
      )}
    </div>
  );

  if (!written) {
    return (
      <>
        {head}
        <section className="card">
          <p className="card__hint">{t("Bu qism hali yozilmagan.")}</p>
          <button className="btn btn--primary btn--sm mt-12" disabled={locked} onClick={() => runJob('generate', { part: key })}>
            {t("✍️ Shu qismni yozish")}
          </button>
        </section>
      </>
    );
  }

  return (
    <>
      {head}
          <input ref={input} type="file" accept="image/*" hidden onChange={onFigure} />

          {key === 'intro' && current.items.map((item, ii) => (
            <section key={ii} className="card">
              <div className="card__label">{item.label}</div>
              <Paragraphs list={item.paragraphs} disabled={locked} onAi={ai({ item: ii })}
                onChange={(fn) => edit(area, (p) => fn(p.intro.items[ii].paragraphs))} />
            </section>
          ))}

          {key === 'conclusion' && (
            <section className="card">
              <Paragraphs list={current.paragraphs} disabled={locked} onAi={ai({})}
                onChange={(fn) => edit(area, (p) => fn(p.conclusion.paragraphs))} />
              <button className="btn btn--soft btn--sm mt-12" disabled={locked} onClick={() => edit(area, (p) => { p.conclusion.paragraphs.push(''); })}>
                <PlusIcon size={16} /> {t("Xatboshi qo'shish")}
              </button>
            </section>
          )}

          {key.startsWith('chapter:') && (() => {
            const ci = Number(key.slice(8));
            return (
              <>
                {current.sections.map((section, si) => (
                  <section key={si} className="card">
                    <div className="card__label">{ci + 1}.{si + 1}.</div>
                    <input className="field" maxLength={300} value={section.title} disabled={locked}
                      onChange={(e) => edit(area, (p) => { p.chapters[ci].sections[si].title = e.target.value; })} />
                    <span className="field-label">{t("Matn")}</span>
                    <Paragraphs list={section.paragraphs} disabled={locked} onAi={ai({ section: si })}
                      onChange={(fn) => edit(area, (p) => fn(p.chapters[ci].sections[si].paragraphs))} />
                    <button className="btn btn--soft btn--sm mt-12" disabled={locked} onClick={() => edit(area, (p) => { p.chapters[ci].sections[si].paragraphs.push(''); })}>
                      <PlusIcon size={16} /> {t("Xatboshi qo'shish")}
                    </button>
                  </section>
                ))}
                {current.figures.length > 0 && (
                  <section className="card">
                    <div className="card__label">{t("Rasm, sxema va jadvallar")}</div>
                    {current.figures.map((f) => (
                      <div key={f.id} className="figure-edit">
                        {f.kind === 'table' ? (
                          <div className="figure-table">
                            <table>
                              <thead><tr>{f.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
                              <tbody>{f.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
                            </table>
                          </div>
                        ) : f.file && (
                          <img src={`/api/diploma-media/${data.mediaToken}/${f.file}`} alt="" className="figure-edit__img" />
                        )}
                        <input className="field" maxLength={300} value={f.caption} disabled={locked}
                          onChange={(e) => edit(area, (p) => { p.chapters[ci].figures.find((x) => x.id === f.id).caption = e.target.value; })} />
                        <div className="figure-edit__meta">
                          <span>{f.kind === 'table' ? t("Jadval") : f.kind === 'scheme' ? t("Sxema") : t("Rasm")} · {current.sections[f.section]?.title ? t('{n}-paragrafda', { n: `${ci + 1}.${f.section + 1}` }) : ''} · {f.source}</span>
                          <span>
                            {f.kind !== 'table' && (
                              <button className="link-btn" disabled={locked} onClick={() => { figTarget.current = f.id; input.current.value = ''; input.current.click(); }}>{t("Almashtirish")}</button>
                            )}
                            <button className="link-btn" disabled={locked}
                              onClick={async () => { if (await confirmDialog(t("O'chirilsinmi?"))) edit(area, (p) => { p.chapters[ci].figures = p.chapters[ci].figures.filter((x) => x.id !== f.id); }); }}>
                              {t("O'chirish")}
                            </button>
                          </span>
                        </div>
                      </div>
                    ))}
                  </section>
                )}
                <section className="card">
                  <div className="card__label">{t("{n} bob bo'yicha xulosa", { n: ROMAN[ci] })}</div>
                  <Paragraphs list={current.summary} disabled={locked} onAi={ai({ summary: true })}
                    onChange={(fn) => edit(area, (p) => fn(p.chapters[ci].summary))} />
                </section>
              </>
            );
          })()}

          <div className="btn-grid">
            <button className="btn btn--white btn--sm" disabled={locked}
              onClick={async () => { if (await confirmDialog(t('{name} qaytadan yozilsinmi? Hozirgi matn (tahrirlaringiz bilan) almashtiriladi.', { name: partLabel(project, key) }))) runJob('generate', { part: key }); }}>
              {t("🔄 Qayta yozish")}
            </button>
            {current.status === 'approved' ? (
              <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => approve(false)}>{t("↩️ Qoralamaga qaytarish")}</button>
            ) : (
              <button className="btn btn--primary btn--sm" disabled={locked} onClick={() => approve(true)}>{t("✅ Tasdiqlash")}</button>
            )}
          </div>
    </>
  );
}

function SourcesPanel({ project, id, runJob, locked, reload }) {
  const { toast } = useApp();
  const [form, setForm] = useState(null);

  async function save(keep, add = []) {
    try {
      await api(`/diplomas/${id}/sources`, { method: 'PUT', body: { keep, add } });
      await reload();
      return true;
    } catch (err) {
      toast(err.message, 'error');
      return false;
    }
  }

  return (
    <section className="card">
      <div className="card__label">{t("Foydalanilgan adabiyotlar")}</div>
      <p className="card__hint">{t("✓ — OpenAlex/Crossref bazalarida haqiqatan mavjud ish (DOI yoki havola bilan). Qo'lda qo'shilganlari «tekshirilmagan» deb belgilanadi. Matndagi [n] iqtiboslar faylda avtomatik raqamlanadi.")}</p>
      {project.sources.map((s) => (
        <div key={s.n} className="source">
          <div>
            <span className={`badge ${s.verified ? '' : 'badge--warn'}`}>{s.verified ? t("✓ tekshirilgan") : t('tekshirilmagan')}</span>
            <b> [{s.n}]</b> {s.authors}. {s.title} ({s.year}){s.venue ? ` // ${s.venue}` : ''}
            {(s.doi || s.url) && <div className="source__link">{s.doi ? `DOI: ${s.doi}` : s.url}</div>}
          </div>
          <button className="icon-btn icon-btn--ghost" disabled={locked} aria-label={t("O'chirish")}
            onClick={async () => { if (await confirmDialog(t("Manba o'chirilsinmi? Matndagi unga havolalar faylda olib tashlanadi."))) save(project.sources.filter((x) => x.n !== s.n).map((x) => x.n)); }}>
            <CloseIcon size={18} />
          </button>
        </div>
      ))}
      {form ? (
        <div className="item-edit">
          {[['authors', 'Muallif(lar)'], ['title', 'Nomi'], ['year', 'Yili'], ['venue', 'Nashr (jurnal, nashriyot)'], ['url', 'Havola (ixtiyoriy)']].map(([k, label]) => (
            <input key={k} className="field mt-12" placeholder={t(label)} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          ))}
          <div className="btn-grid mt-12">
            <button className="btn btn--white btn--sm" onClick={() => setForm(null)}>{t("Bekor qilish")}</button>
            <button className="btn btn--primary btn--sm" disabled={locked}
              onClick={async () => { if (await save(project.sources.map((x) => x.n), [{ ...form, year: Number(form.year) }])) setForm(null); }}>
              {t("Qo'shish")}
            </button>
          </div>
        </div>
      ) : (
        <div className="btn-grid mt-12">
          <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => setForm({ authors: '', title: '', year: '', venue: '', url: '' })}>
            <PlusIcon size={16} /> {t("Qo'lda qo'shish")}
          </button>
          <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => runJob('sources')}>{t("🔎 Yana qidirish")}</button>
        </div>
      )}
    </section>
  );
}

// ===== 5. Fayl =====
function FileStep({ project, data, runJob, locked, setStep }) {
  const { toast } = useApp();
  const done = partKeys(project).every((k) => partOf(project, k).status === 'approved');
  const left = partKeys(project).filter((k) => partOf(project, k).status !== 'approved').map((k) => partLabel(project, k));

  async function get(fmt) {
    if (await runJob('export', { fmt })) {
      toast(t("Fayl Telegram chatga yuborildi 📩"));
    }
  }

  async function redesign(design) {
    if (await runJob('design', { design })) toast(t("Yangi dizayndagi fayl Telegram chatga yuborildi 🎨"));
  }

  return (
    <>
      <section className="card">
        <div className="card__label">{done ? `🎉 ${t('Diplom ishi tayyor')}` : t('Qoralama')}</div>
        {!done && <p className="note note--warn">{t('Hali tasdiqlanmagan: {list}. Faylni qoralama sifatida ham olish mumkin.', { list: left.join(', ') })}</p>}
        <p className="card__hint">
          {t("Fayl metodik talablar bo'yicha rasmiylashtiriladi: titul, avtomatik mundarija, bob va paragraf sarlavhalari, sahifa raqamlari, rasm va jadvallar raqami va izohlari, iqtiboslar va adabiyotlar ro'yxati. Word'da ochganda «maydonlarni yangilash» so'ralsa — «Ha» ni bosing.")}
        </p>
        <div className="btn-grid mt-12">
          <button className="btn btn--primary btn--sm" disabled={locked} onClick={() => get('docx')}>{t("📄 DOCX olish")}</button>
          {data.pdf && <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => get('pdf')}>{t("📕 PDF olish")}</button>}
        </div>
        {data.documentId && (
          <button className="btn btn--white btn--sm mt-12" disabled={locked}
            onClick={() => downloadFile('documents', data.documentId).catch((e) => toast(e.message, 'error'))}>
            <DownloadIcon size={18} /> {t("Oxirgi faylni yuklab olish")}
          </button>
        )}
      </section>
      <DocDesignPicker current={project.design} locked={locked} onPick={redesign} />
      <div className="note note--info">
        {t("⚠️ Matn — qoralama: raqamli ma'lumotlar, iqtiboslar va xulosalarni tekshirib, ilmiy rahbaringiz bilan kelishib oling. Haqiqiy ma'lumot bo'lmagan joylarda misollar «namunaviy» deb belgilangan.")}
      </div>
      {!done && <button className="btn btn--soft" onClick={() => setStep('write')}>{t("Yozishga qaytish")}</button>}
    </>
  );
}
