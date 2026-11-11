import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t } from '../lib/i18n.js';

import { useApp } from '../app/AppContext.jsx';
import DissertationArt from '../components/DissertationArt.jsx';
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

// Dissertatsiya: 11 bosqich. Matn va reja shu yerda tahrirlanadi va avtomatik saqlanadi;
// AI ishlari bot navbatida bajariladi (bot bilan bitta loyiha — botda boshlangan ishni shu yerda davom ettirish mumkin).

const STEPS = [
  ['type', 'Turi'], ['personal', 'Shaxsiy'], ['topic', 'Mavzu'], ['method', 'Metodika'], ['plan', 'Reja'],
  ['text', 'Matn'], ['visuals', 'Rasmlar'], ['quality', 'Tekshirish'], ['file', 'Yuklab olish'],
];
const HINTS = {
  type: 'Turiga qarab tuzilma (boblar soni), hajm va kirish talablari moslashadi.',
  personal: "Titul varag'i uchun. Hammasi ixtiyoriy — keyinroq to'ldirsa ham bo'ladi.",
  topic: "Yo'nalish va mavzu — majburiy. Mavzuni bilmasangiz, AI 5 ta variant taklif qiladi.",
  method: "Qo'llanmadan faqat unda yozilgan talablar olinadi. Excel/CSV ma'lumotlaringizdan grafik va statistika tuziladi.",
  plan: "Reja bepul. O'zgartiring, tartibini almashtiring yoki qayta tuzdiring, keyin tasdiqlang (shu payt pul yechiladi).",
  text: "Butun ish bir bosishda yoziladi va shu yerda bitta ustunda chiqadi: kirish, boblar, xulosa, annotatsiya. Istalgan joyni tahrirlang yoki AI bilan yaxshilang.",
  visuals: "Barcha rasm, sxema, grafik va jadvallar: almashtirish, o'chirish, yangi rasm yoki jadval qo'shish.",
  quality: "Takrorlar, iqtiboslar, manbalar, rasmlar, hajm, kirish va xulosa mosligi tekshiriladi.",
  file: 'DOCX/PDF — titul, annotatsiya, avtomatik mundarija, raqamlangan rasm va jadvallar bilan.',
};
const PERSONAL = [
  ['student', 'F.I.Sh.', 'Titul varag\'iga yoziladi', 'Aliyev Vali Karimovich', 200],
  ['university', 'Universitet yoki ilmiy muassasa', "Titul va mahalliy talablar uchun", 'Toshkent davlat iqtisodiyot universiteti', 250],
  ['faculty', 'Fakultet yoki ilmiy tashkilot', "Titul varag'i uchun", 'Iqtisodiyot fakulteti', 250],
  ['specialty', 'Mutaxassislik nomi', 'Reja va uslubga ta\'sir qiladi', 'Raqamli iqtisodiyot', 200],
  ['specialty_code', 'Mutaxassislik kodi', 'Titul va OAK talablari uchun', '08.00.16', 40],
  ['degree', 'Ilmiy daraja', 'Qaysi daraja uchun — titulga yoziladi', "Iqtisodiyot fanlari bo'yicha falsafa doktori (PhD)", 250],
  ['supervisor', 'Ilmiy rahbar yoki maslahatchi', "Titul varag'i uchun", 'i.f.d., prof. Karimov A.B.', 250],
];
const TOPIC = [
  ['direction', "Tadqiqot yo'nalishi", 'majburiy · reja, manbalar va mavzu takliflari shunga qarab', 'Raqamli iqtisodiyot, kichik biznes', 200, false],
  ['problem', "O'rganilayotgan muammo", 'ixtiyoriy · maqsad va vazifalar aniqroq bo\'ladi', 'Kichik korxonalarda raqamli texnologiyalar sekin joriy etilmoqda', 600, true],
  ['topic', 'Dissertatsiya mavzusi', 'majburiy · butun ish shu mavzu atrofida quriladi', 'Kichik biznesni raqamli transformatsiya qilish mexanizmlarini takomillashtirish', 300, true],
  ['existing', "Mavzu bo'yicha mavjud ma'lumotlaringiz", "ixtiyoriy · natijalar, maqolalar, to'plangan ma'lumotlar. Yo'q bo'lsa — AI o'ylab topmaydi", '2024-yilda 40 ta korxonada so\'rovnoma o\'tkazdim', 1500, true],
  ['extra', "Qo'shimcha talablar", 'ixtiyoriy · rahbar yoki kafedra talablari', 'Amaliy qism Toshkent viloyati misolida', 1000, true],
];
const LANGS = { uz: "O'zbekcha", ru: 'Русский', en: 'English' };
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'];
const AI_OPS = [['expand', 'Kengaytirish'], ['shorten', 'Qisqartirish'], ['fix', 'Imloni tuzatish'], ['style', 'Ilmiy uslubga keltirish'], ['regenerate', 'Qayta yozish']];
const JOB_TEXT = {
  topics: 'Mavzu takliflari tayyorlanmoqda…', analyze: "Metodik qo'llanma tahlil qilinmoqda…",
  plan: 'Reja tuzilmoqda… odatda 10–40 soniya.', approve_plan: 'Reja tasdiqlanmoqda, haqiqiy ilmiy manbalar qidirilmoqda…',
  generate: 'Matn yozilmoqda… bob uchun odatda 40–120 soniya.', rewrite: 'Xatboshi qayta ishlanmoqda…',
  write_all: 'Dissertatsiya yozilmoqda…',
  sources: 'Ilmiy manbalar qidirilmoqda…', quality: 'Dissertatsiya tekshirilmoqda…',
  export: 'Fayl tayyorlanmoqda, tekshirilmoqda va Telegram chatga yuborilmoqda…',
  design: 'Fayl yangi dizaynda yig\'ilmoqda va Telegram chatga yuborilmoqda…',
};
const STAGE_LABEL = { type: 'Turi', info: "Ma'lumotlar", plan: 'Reja', writing: 'Yozilmoqda', done: '✅ Tayyor' };
const SAVE_DELAY = 1200;
const STATUS_ICON = { ok: '✅', warn: '⚠️', error: '❌', skip: '➖' };

const partKeys = (p) => ['intro', ...p.chapters.map((_, i) => `chapter:${i}`), 'conclusion', 'annotation'];
const partOf = (p, key) => (['intro', 'conclusion', 'annotation'].includes(key) ? p[key] : p.chapters[Number(key.slice(8))]);
const partLabel = (key) => ({ intro: 1, conclusion: 1, annotation: 1 }[key] ? t({ intro: 'Kirish#qism', conclusion: 'Umumiy xulosa', annotation: 'Annotatsiya' }[key]) : t('{n} bob', { n: ROMAN[Number(key.slice(8))] }));
function hasText(p, key) {
  const part = partOf(p, key);
  if (!part) return false;
  if (key === 'intro') return part.items.length > 0;
  if (key === 'conclusion' || key === 'annotation') return part.paragraphs.length > 0;
  return part.sections.some((s) => s.paragraphs.length);
}
const rowsFor = (text) => Math.min(14, Math.max(3, Math.ceil((text?.length ?? 0) / 42)));
function stepOf(p) {
  if (!p.kind) return 'type';
  if (!p.plan.chapters.length) return (p.info.topic?.length ?? 0) >= 5 ? 'method' : 'topic';
  if (!p.plan.approved) return 'plan';
  const open = partKeys(p).find((k) => partOf(p, k).status !== 'approved');
  return open ? 'text' : 'quality';
}

// ===== Boshlang'ich sahifa =====
export default function Dissertation({ dissId, documentId }) {
  const { toast } = useApp();
  const [id, setId] = useState(dissId ?? null);
  useEffect(() => {
    if (!id && documentId) api(`/dissertations/by-document/${documentId}`).then((d) => setId(d.id)).catch((e) => toast(e.message, 'error'));
  }, [id, documentId, toast]);
  if (id) return <Project id={id} onBack={dissId ? null : () => setId(null)} />;
  if (documentId) return <main className="page"><TopBar title={t("Dissertatsiya")} /><Skeleton height={80} count={3} /></main>;
  return <Start onOpen={setId} />;
}

function Hero({ compact }) {
  return (
    <div className={`diploma-hero diss-hero ${compact ? 'diploma-hero--compact' : ''}`}>
      <div className="diploma-hero__text">
        <b>{t("Dissertatsiya yaratish")}</b>
        <span>{compact ? t("Magistrlik, PhD, DSc — bosqichma-bosqich") : t("Ilmiy mavzuingizni kiriting va AI yordamida dissertatsiya tayyorlash jarayonini boshlang")}</span>
      </div>
      <DissertationArt className="diploma-hero__art" />
    </div>
  );
}

function Start({ onOpen }) {
  const { boot, toast } = useApp();
  const cfg = boot.settings.dissertation;
  const [items, setItems] = useState(null);
  const [guide, setGuide] = useState(false);
  const [busy, setBusy] = useState(false);
  const typesRef = useRef();

  useEffect(() => {
    api('/dissertations').then((d) => setItems(d.items)).catch(() => setItems([]));
  }, []);

  async function create(kind) {
    setBusy(true);
    try {
      const { id } = await api('/dissertations', { method: 'POST', body: { kind } });
      haptic('success');
      onOpen(id);
    } catch (error) {
      toast(error.message, 'error');
      setBusy(false);
    }
  }

  const types = cfg?.types ?? {};
  return (
    <main className="page">
      <TopBar title={t("Dissertatsiya")} />
      <Hero />
      <div className="btn-grid">
        <button className="btn btn--primary btn--sm" onClick={() => typesRef.current?.scrollIntoView({ behavior: 'smooth' })}><PlusIcon size={16} /> {t("Yangi dissertatsiya")}</button>
        <button className="btn btn--soft btn--sm" disabled={!items?.length} onClick={() => items?.[0] && onOpen(items[0].id)}>{t("▶️ Ishni davom ettirish")}</button>
        <button className="btn btn--soft btn--sm" onClick={() => setGuide(!guide)}>{t("📖 Yo'riqnoma")}</button>
        <button className="btn btn--soft btn--sm" onClick={() => toast(t("Avval dissertatsiya turini tanlang — qo'llanma 4-bosqichda yuklanadi"))}>{t("📘 Metodik qo'llanma")}</button>
      </div>
      {guide && (
        <section className="card">
          <div className="card__label">{t("Yo'riqnoma")}</div>
          <ol className="guide">
            {STEPS.map(([key, label]) => <li key={key}><b>{t(label)}.</b> {t(HINTS[key])}</li>)}
          </ol>
          <p className="note note--warn">{t("Manbalar — faqat OpenAlex/Crossref'dagi haqiqiy ishlar. Raqamlar, so'rovnomalar va natijalar o'ylab topilmaydi. Matnni ilmiy rahbaringiz bilan tekshiring.")}</p>
        </section>
      )}
      <div className="section-head" ref={typesRef}><h2>{t("Dissertatsiya turi")}</h2></div>
      <div className="list">
        {Object.entries(types).map(([key, dt]) => (
          <button key={key} className="item item--button pressable" disabled={busy} onClick={() => create(key)}>
            <span className="diploma-badge">{{ master: '🎓', phd: '🔬', dsc: '🏛', other: '📑' }[key]}</span>
            <div className="item__body">
              <div className="item__title">{t(dt.name)}</div>
              <div className="item__meta">~{dt.pages} {t('bet')} · {dt.chapters} {t('bob')} · {money(dt.pages * cfg.page_price)}</div>
            </div>
            <ChevronRight size={20} />
          </button>
        ))}
      </div>
      <p className="card__hint" style={{ margin: '10px 4px' }}>{t("Narxi — har bir bet {price}. Betlar sonini o'zingiz tanlaysiz. Pul faqat reja tasdiqlanganda bir marta yechiladi.", { price: money(cfg?.page_price ?? 800) })}</p>
      {items?.length > 0 && (
        <>
          <div className="section-head"><h2>{t("Saqlangan dissertatsiyalarim")}</h2></div>
          <div className="list">
            {items.map((d) => (
              <button key={d.id} className="item item--button pressable" onClick={() => onOpen(d.id)}>
                <span className="diploma-badge">🔬</span>
                <div className="item__body">
                  <div className="item__title">{d.title || t("Mavzu hali yozilmagan")}</div>
                  <div className="item__meta">{t(types[d.kind]?.name ?? '')} · {t(STAGE_LABEL[d.stage] ?? '')} · {d.pages} {t('bet')} · {shortDate(d.updated_at)}</div>
                </div>
                <ChevronRight size={20} />
              </button>
            ))}
          </div>
        </>
      )}
      {items === null && <Skeleton height={64} count={2} />}
    </main>
  );
}

// ===== Loyiha =====
function Project({ id, onBack }) {
  const { boot, toast, topup, setLeaveGuard } = useApp();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [project, setProject] = useState(null);
  const [step, setStep] = useState(null);
  const [job, setJob] = useState(null);
  const timers = useRef({});
  const pending = useRef({});
  const projectRef = useRef(null);
  const strip = useRef();
  projectRef.current = project;

  const apply = useCallback((view) => {
    setData(view);
    setProject(view.project);
    return view;
  }, []);
  const reload = useCallback(() => api(`/dissertations/${id}`).then(apply), [id, apply]);

  const saveNow = useCallback(async (area) => {
    clearTimeout(timers.current[area]);
    delete pending.current[area];
    const p = projectRef.current;
    try {
      let view;
      if (area === 'info') view = await api(`/dissertations/${id}/info`, { method: 'PUT', body: { ...p.info, kind: p.kind } });
      else if (area === 'plan') view = await api(`/dissertations/${id}/plan`, { method: 'PUT', body: { chapters: p.plan.chapters } });
      else {
        const key = area.slice(5);
        const part = partOf(p, key);
        const body = key === 'intro' ? { items: part.items } : key === 'conclusion' ? { paragraphs: part.paragraphs }
          : key === 'annotation' ? { paragraphs: part.paragraphs, keywords: part.keywords }
            : { sections: part.sections, summary: part.summary, figures: part.figures };
        view = await api(`/dissertations/${id}/part`, { method: 'PUT', body: { part: key, data: body } });
      }
      setData((d) => ({ ...d, ...view, project: d.project }));
    } catch (err) {
      toast(err.message, 'error');
    }
  }, [id, toast]);

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

  const waitJob = useCallback(async (orderId, action) => {
    setJob({ id: orderId, action });
    try {
      await pollOrder(orderId);
      haptic('success');
      if (action === 'write_all') toast(t("🎉 Dissertatsiya tayyor! DOCX fayl Telegram chatga yuborildi."));
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
      const { orderId } = await api(`/dissertations/${id}/jobs`, { method: 'POST', body: { action, ...extra } });
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

  // Bir martalik amallar (rasm qo'shish, versiyani qaytarish, tasdiqlash) — natija serverdan qaytadi
  const call = useCallback(async (path, body) => {
    await flush();
    try {
      apply(await api(`/dissertations/${id}${path}`, { method: 'POST', body }));
      haptic('success');
      return true;
    } catch (err) {
      toast(err.message, 'error');
      return false;
    }
  }, [apply, flush, id, toast]);

  useEffect(() => {
    let alive = true;
    api(`/dissertations/${id}`).then((view) => {
      if (!alive) return;
      apply(view);
      setStep(stepOf(view.project));
      if (view.jobs[0]) waitJob(view.jobs[0].id, view.jobs[0].action);
    }).catch((err) => alive && setError(err));
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

  useEffect(() => {
    const index = STEPS.findIndex(([k]) => k === step);
    strip.current?.children[index]?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [step]);

  if (error) return <main className="page"><TopBar title={t("Dissertatsiya")} /><Empty icon="🔬" title={t("Ochib bo'lmadi")} text={error.message} /></main>;
  if (!project) return <main className="page"><TopBar title={t("Dissertatsiya")} /><Skeleton height={90} count={4} /></main>;

  const locked = Boolean(job);
  const approved = project.plan.approved;
  const reach = {
    type: true, personal: Boolean(project.kind), topic: Boolean(project.kind), method: Boolean(project.kind), plan: Boolean(project.kind),
    text: approved, visuals: approved, quality: approved, file: approved && hasText(project, 'intro'),
  };
  const go = (key) => {
    if (!reach[key]) {
      toast(approved ? t("Avval kirish qismini yozing") : t("Avval rejani tasdiqlang"));
      return;
    }
    haptic('select');
    flush();
    setStep(key);
    window.scrollTo(0, 0);
  };
  const next = (key) => () => go(key);
  const props = { project, data, edit, runJob, call, locked, go, next, flush, reload, id, settings: boot.settings };

  return (
    <main className="page diploma" style={{ paddingBottom: 'calc(40px + var(--safe-bottom))' }}>
      <TopBar title={t("Dissertatsiya")} right={onBack && <button className="link-btn" onClick={onBack}>{t("Ro'yxat")}</button>} />
      <Hero compact />
      <div className="stepper stepper--scroll" ref={strip} role="tablist">
        {STEPS.map(([key, label], i) => (
          <button key={key} role="tab" onClick={() => go(key)}
            className={`stepper__item ${step === key ? 'stepper__item--active' : ''} ${reach[key] ? '' : 'stepper__item--off'}`}>
            <span className="stepper__num">{i + 1}</span>
            {t(label)}
          </button>
        ))}
      </div>
      <p className="step-hint">💡 {t(HINTS[step])}</p>
      {job && <JobCard job={job} progress={project.progress} text={JOB_TEXT} />}
      {step === 'type' && <TypeStep {...props} />}
      {step === 'personal' && <PersonalStep {...props} />}
      {step === 'topic' && <TopicStep {...props} />}
      {step === 'method' && <MethodStep {...props} />}
      {step === 'plan' && <PlanStep {...props} />}
      {step === 'text' && <PartsStep {...props} keys={partKeys(project)} nextStep="visuals" />}
      {step === 'visuals' && <VisualsStep {...props} />}
      {step === 'quality' && <QualityStep {...props} />}
      {step === 'file' && <FileStep {...props} />}
    </main>
  );
}

// ===== 1–3. Turi, shaxsiy ma'lumotlar, mavzu =====
function TypeStep({ project, edit, locked, next, settings }) {
  const types = settings.dissertation?.types ?? {};
  return (
    <>
      <div className="list">
        {Object.entries(types).map(([key, dt]) => (
          <button key={key} disabled={locked || project.plan.approved}
            className={`item item--button pressable ${project.kind === key ? 'item--active' : ''}`}
            onClick={() => edit('info', (p) => { if (p.kind !== key) p.info.pages = dt.pages; p.kind = key; })}>
            <span className="diploma-badge">{{ master: '🎓', phd: '🔬', dsc: '🏛', other: '📑' }[key]}</span>
            <div className="item__body">
              <div className="item__title">{t(dt.name)}</div>
              <div className="item__meta">~{dt.pages} {t('bet')} · {dt.chapters} {t('bob')}</div>
            </div>
            {project.kind === key && <span className="badge">{t("Tanlangan")}</span>}
          </button>
        ))}
      </div>
      {project.plan.approved && <p className="card__hint mt-12">{t("Reja tasdiqlangan — turi endi o'zgarmaydi.")}</p>}
      <button className="btn btn--primary mt-12" onClick={next('personal')}>{t("Davom etish")} <ChevronRight size={18} /></button>
    </>
  );
}

function Field({ label, hint, value, onChange, max, rows, placeholder, disabled }) {
  const Tag = rows ? 'textarea' : 'input';
  return (
    <label className="editor-field">
      <span className="field-label">{label}{hint && <span className="field-why">{hint}</span>}</span>
      <Tag className="field" rows={rows} maxLength={max} placeholder={placeholder} value={value ?? ''} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function PersonalStep({ project, edit, locked, next }) {
  const set = (key, value) => edit('info', (p) => { p.info[key] = value; });
  return (
    <>
      <section className="card">
        <div className="card__label">{t("Shaxsiy va ta'lim ma'lumotlari")} <span className="card__hint">{t("hammasi ixtiyoriy")}</span></div>
        {PERSONAL.map(([key, label, why, example, max]) => (
          <Field key={key} label={t(label)} hint={t(why)} max={max} placeholder={t(example)} value={project.info[key]} disabled={locked} onChange={(v) => set(key, v)} />
        ))}
      </section>
      <section className="card">
        <div className="card__label">{t("Dissertatsiya tili")} <span className="card__hint">{t("butun matn shu tilda")}</span></div>
        <div className="segment">
          {Object.entries(LANGS).map(([key, label]) => (
            <button key={key} className={project.info.lang === key ? 'segment--active' : ''} disabled={locked || project.plan.approved}
              onClick={() => { haptic('select'); set('lang', key); }}><Flag lang={key} /> {label}</button>
          ))}
        </div>
      </section>
      <button className="btn btn--primary" onClick={next('topic')}>{t("Davom etish")} <ChevronRight size={18} /></button>
    </>
  );
}

function TopicStep({ project, edit, runJob, locked, next, settings }) {
  const cfg = settings.dissertation ?? { page_price: 800, min: 50, max: 300, types: {} };
  const kind = cfg.types?.[project.kind] ?? { options: [80], pages: 80 };
  const info = project.info;
  const [custom, setCustom] = useState(kind.options.includes(info.pages) ? '' : String(info.pages));
  const set = (key, value) => edit('info', (p) => { p.info[key] = value; });
  const fixed = project.plan.approved;
  return (
    <>
      <section className="card">
        <div className="card__label">{t("Ilmiy mavzu")}</div>
        {TOPIC.map(([key, label, hint, example, max, rows]) => (
          <div key={key}>
            <Field label={t(label)} hint={t(hint)} max={max} rows={rows ? 2 : undefined} placeholder={t(example)} value={info[key]} disabled={locked} onChange={(v) => set(key, v)} />
            {key === 'topic' && (
              <button className="btn btn--soft btn--sm mt-12" disabled={locked || (info.direction?.trim().length ?? 0) < 5} onClick={() => runJob('topics')}>
                {t("💡 Mavzu taklif qilish")}
              </button>
            )}
            {key === 'topic' && project.suggestions.length > 0 && (
              <div className="suggestions">
                {project.suggestions.map((s, i) => (
                  <button key={i} className={`suggestion pressable ${info.topic === s.title ? 'suggestion--active' : ''}`} disabled={locked}
                    onClick={() => { haptic('select'); set('topic', s.title); }}>
                    <b>{s.title}</b>
                    <span>{s.why}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </section>
      <section className="card">
        <div className="card__label">{t("Hajmi")} <span className="card__hint">{t('har bir bet {price}', { price: money(cfg.page_price) })}</span></div>
        <div className="options">
          {kind.options.map((n) => (
            <button key={n} className={`option ${info.pages === n ? 'option--active' : ''}`} disabled={locked || fixed}
              onClick={() => { haptic('select'); setCustom(''); set('pages', n); }}>
              <b>{n} {t('bet')}</b><span>{money(n * cfg.page_price)}</span>
            </button>
          ))}
        </div>
        <Field label={t("Yoki o'zingiz kiriting ({min}–{max} bet)", { min: cfg.min, max: cfg.max })} max={3} placeholder={t("Masalan: 135")} value={custom} disabled={locked || fixed}
          onChange={(v) => { const value = v.replace(/\D/g, ''); setCustom(value); const n = Number(value); if (n >= cfg.min && n <= cfg.max) set('pages', n); }} />
        {custom && (Number(custom) < cfg.min || Number(custom) > cfg.max) && <p className="note note--warn">{cfg.min} dan {cfg.max} gacha son kiriting.</p>}
      </section>
      <button className="btn btn--primary" onClick={next('method')}>{t("Davom etish")} <ChevronRight size={18} /></button>
    </>
  );
}

// ===== 4. Metodika va materiallar =====
function MethodStep({ project, id, runJob, locked, next, reload }) {
  const { toast } = useApp();
  const [uploading, setUploading] = useState(null);
  const input = useRef();
  const target = useRef('method');
  const method = project.method;

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
      await apiUpload(`/dissertations/${id}/upload?purpose=${target.current}`, file, { 'X-File-Name': encodeURIComponent(file.name) });
      haptic('success');
      await reload();
      if (target.current === 'method') await runJob('analyze');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(null);
    }
  }
  async function remove(file) {
    try {
      await api(`/dissertations/${id}/material/${file}`, { method: 'DELETE' });
      await reload();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return (
    <>
      <input ref={input} type="file" hidden onChange={onFile} />
      <section className="card">
        <div className="card__label">{t("Metodik qo'llanma")} <span className="card__hint">{t("PDF yoki DOCX · ixtiyoriy")}</span></div>
        <p className="card__hint">{method.file
          ? `📘 ${method.name} — ${method.status === 'analyzed' ? t('tahlil qilingan, {n} ta talab topildi', { n: method.found.length }) : method.status === 'uploaded' ? t("yuklangan, tahlil qilinmagan") : t("aniq talablar topilmadi")}`
          : t("Yuklanmasa — tanlangan tur uchun keng tarqalgan namunaviy talablar ishlatiladi (rejada alohida ko'rsatiladi).")}</p>
        <div className="btn-grid mt-12">
          <button className="btn btn--soft btn--sm" disabled={locked || Boolean(uploading) || project.plan.approved} onClick={() => pick('method')}>
            {uploading === 'method' ? t("Yuklanmoqda…") : method.file ? t("📘 Boshqa fayl") : t("📘 Qo'llanmani yuklash")}
          </button>
          {method.status === 'uploaded' && <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => runJob('analyze')}>{t("🔍 Tahlil qilish")}</button>}
        </div>
        {method.found.length > 0 && (
          <div className="rules">
            {method.found.map((rule, i) => (
              <details key={i} className="rule">
                <summary><b>{rule.label}:</b> {rule.value}</summary>
                <blockquote>«{rule.quote}»</blockquote>
              </details>
            ))}
            <p className="card__hint">{t("Faqat qo'llanmada yozilgan talablar — har biri asl matndan iqtibos bilan.")}</p>
          </div>
        )}
        {method.notes && <p className="note note--info">{method.notes}</p>}
      </section>
      <section className="card">
        <div className="card__label">{t("Qo'shimcha materiallar")} <span className="card__hint">{t('ixtiyoriy')}</span></div>
        <p className="card__hint">{t("Excel/CSV — grafik va statistika FAQAT shulardan (raqamlarni dastur hisoblaydi, AI o'ylab topmaydi). PDF/DOCX — matnli materiallar. Rasmlarni 8-bosqichda bobga qo'shasiz.")}</p>
        {project.materials.map((m) => (
          <div key={m.file} className="item-row">
            <span className="material">{['csv', 'xlsx'].includes(m.kind) ? '📊' : '📎'} {m.name}</span>
            <button className="icon-btn icon-btn--ghost" disabled={locked} onClick={() => remove(m.file)} aria-label={t("O'chirish")}><CloseIcon size={18} /></button>
          </div>
        ))}
        <button className="btn btn--soft btn--sm mt-12" disabled={locked || Boolean(uploading)} onClick={() => pick('material')}>
          {uploading === 'material' ? t("Yuklanmoqda…") : t("📎 Material qo'shish")}
        </button>
      </section>
      <button className="btn btn--primary" onClick={next('plan')}>{t("Rejaga o'tish")} <ChevronRight size={18} /></button>
    </>
  );
}

// ===== 5. Reja =====
function PlanStep({ project, data, edit, runJob, locked, go }) {
  const plan = project.plan;
  const fixed = locked || plan.approved;
  const set = (fn) => edit('plan', (p) => fn(p.plan.chapters));
  const ready = (project.info.topic?.trim().length ?? 0) >= 5 && (project.info.direction?.trim().length ?? 0) >= 5;
  if (!plan.chapters.length) {
    return (
      <section className="card">
        <div className="card__label">{t("Reja")}</div>
        <p className="card__hint">{t("AI mavzu, tur va metodik talablarni birga tahlil qilib, individual reja tuzadi. Bepul.")}</p>
        {!ready && <p className="note note--warn">{t("Avval 3-bosqichda yo'nalish va mavzuni yozing.")}</p>}
        <button className="btn btn--primary mt-12" disabled={locked || !ready} onClick={() => runJob('plan')}>{t("📋 Reja tuzish (bepul)")}</button>
      </section>
    );
  }
  const move = (ci, si, delta) => set((c) => { const s = c[ci].sections; [s[si], s[si + delta]] = [s[si + delta], s[si]]; });
  return (
    <>
      <div className={`note ${project.method.status === 'analyzed' ? 'note--info' : 'note--warn'}`} style={{ marginTop: 0 }}>
        {project.method.status === 'analyzed' ? t("✅ Reja metodik qo'llanma talablari asosida tuzildi.") : t("ℹ️ Qo'llanma yuklanmagan — bu namunaviy tuzilma (tanlangan tur uchun).")}
      </div>
      <section className="card">
        <div className="card__label">{t("Annotatsiya · Kirish")}</div>
        {plan.chapters.map((chapter, ci) => (
          <div key={ci} className="plan-chapter">
            <div className="item-edit__head">
              <b>{ROMAN[ci]}</b>
              <input className="field" maxLength={300} value={chapter.title} disabled={fixed} onChange={(e) => set((c) => { c[ci].title = e.target.value; })} />
              {!fixed && plan.chapters.length > 1 && (
                <button className="icon-btn icon-btn--ghost" aria-label={t("Bobni o'chirish")}
                  onClick={async () => { if (await confirmDialog(t("{n} bobni o'chirasizmi?", { n: ROMAN[ci] }))) set((c) => { c.splice(ci, 1); }); }}><CloseIcon size={18} /></button>
              )}
            </div>
            {chapter.sections.map((section, si) => (
              <div key={si} className="plan-section">
                <span>{ci + 1}.{si + 1}.</span>
                <input className="field" maxLength={300} value={section.title} disabled={fixed} onChange={(e) => set((c) => { c[ci].sections[si].title = e.target.value; })} />
                {!fixed && (
                  <span className="plan-tools">
                    <button className="icon-btn icon-btn--ghost" aria-label={t("Yuqoriga")} disabled={si === 0} onClick={() => move(ci, si, -1)}>↑</button>
                    <button className="icon-btn icon-btn--ghost" aria-label={t("Pastga")} disabled={si === chapter.sections.length - 1} onClick={() => move(ci, si, 1)}>↓</button>
                    {chapter.sections.length > 1 && <button className="icon-btn icon-btn--ghost" aria-label={t("O'chirish")} onClick={() => set((c) => { c[ci].sections.splice(si, 1); })}><CloseIcon size={16} /></button>}
                  </span>
                )}
              </div>
            ))}
            {!fixed && chapter.sections.length < 8 && (
              <button className="link-btn" onClick={() => set((c) => { c[ci].sections.push({ title: t('Yangi paragraf') }); })}><PlusIcon size={14} /> {t("Paragraf qo'shish")}</button>
            )}
          </div>
        ))}
        {!fixed && plan.chapters.length < 7 && (
          <button className="btn btn--soft btn--sm mt-12" onClick={() => set((c) => { c.push({ title: t('Yangi bob'), sections: [{ title: t('Yangi paragraf') }] }); })}><PlusIcon size={16} /> {t("Bob qo'shish")}</button>
        )}
        <div className="card__label mt-12">{t("Umumiy xulosa · Adabiyotlar · Ilovalar")}</div>
      </section>
      {plan.approved ? (
        <button className="btn btn--primary" onClick={() => go('text')}>{t("Yozishga o'tish")} <ChevronRight size={18} /></button>
      ) : (
        <section className="card">
          <div className="summary-row">{t("Narxi")} <b>{data.price ? money(data.price) : 'bepul'}</b></div>
          <div className="summary-row">{t("Balansingiz")} <b>{money(data.balance)}</b></div>
          <p className="card__hint">{t("Tasdiqlagach pul bir marta yechiladi, haqiqiy manbalar qidiriladi va yozish boshlanadi. Reja tuzilmasi shundan keyin o'zgarmaydi.")}</p>
          <div className="btn-grid mt-12">
            <button className="btn btn--soft btn--sm" disabled={locked} onClick={async () => { if (await confirmDialog(t("Reja qaytadan tuzilsinmi? Hozirgi o'zgarishlar almashtiriladi."))) runJob('plan'); }}>{t("🔄 Qayta tuzish")}</button>
            <button className="btn btn--primary btn--sm" disabled={locked}
              onClick={async () => { if (!(await confirmDialog(t('Rejani tasdiqlaysizmi? {pay} Keyin butun ish avtomatik yoziladi.', { pay: data.price ? t('{sum} yechiladi.', { sum: money(data.price) }) : '' })))) return; if (await runJob('approve_plan')) { go('text'); runJob('write_all'); } }}>{t("✅ Tasdiqlash")}</button>
          </div>
        </section>
      )}
    </>
  );
}

// ===== 6, 7, 9. Qismlar (kirish, boblar, xulosa va annotatsiya) =====
function Paragraphs({ list, onChange, disabled, onAi }) {
  return list.map((text, i) => (
    <div key={i} className="item-edit">
      <div className="item-edit__head">
        <b>{i + 1}</b>
        <span className="paper-para__hint">{t('xatboshi')}</span>
        {onAi && (
          <select className="ai-select" disabled={disabled} value="" aria-label={t("AI amali")} onChange={(e) => e.target.value && onAi(i, e.target.value)}>
            <option value="">{t("✨ AI")}</option>
            {AI_OPS.map(([op, label]) => <option key={op} value={op}>{t(label)}</option>)}
          </select>
        )}
        <button className="icon-btn icon-btn--ghost" aria-label={t("O'chirish")} disabled={disabled || list.length <= 1}
          onClick={async () => { if (await confirmDialog(t("Bu xatboshini o'chirasizmi?"))) onChange((l) => { l.splice(i, 1); }); }}><CloseIcon size={18} /></button>
      </div>
      <textarea className="field" rows={rowsFor(text)} maxLength={6000} value={text} disabled={disabled} onChange={(e) => onChange((l) => { l[i] = e.target.value; })} />
    </div>
  ));
}

const partAnchor = (key) => `spart-${key.replace(':', '-')}`;
const scrollToPart = (key) => document.getElementById(partAnchor(key))?.scrollIntoView({ behavior: 'smooth', block: 'start' });

/** Matn: butun ish (kirish, barcha boblar, umumiy xulosa, annotatsiya) bitta ustunda — har bir bobga alohida kirish shart emas.
 *  Yuqoridagi chiplar faqat kerakli joyga tez o'tish uchun. */
function PartsStep({ project, keys, nextStep, edit, runJob, call, locked, go, data }) {
  const anyWritten = keys.some((k) => hasText(project, k));
  const allApproved = keys.every((k) => partOf(project, k).status === 'approved');

  function afterApprove(key) {
    const nextKey = keys.find((k) => k !== key && partOf(project, k).status !== 'approved');
    if (nextKey) setTimeout(() => scrollToPart(nextKey), 50);
    else go(nextStep);
  }

  if (!anyWritten) {
    return (
      <WriteAllCard
        parts={partKeys(project).map((k) => ({ key: k, label: partLabel(k), done: hasText(project, k) }))}
        about="Kirish, barcha boblar (mavzuga mos rasm, sxema, grafik va jadvallar bilan), umumiy xulosa va annotatsiya ketma-ket yoziladi, sifat nazorati o'tkaziladi. Tayyor DOCX fayl Telegram chatga keladi."
        locked={locked} onWrite={() => runJob('write_all')} />
    );
  }

  return (
    <>
      <div className="chips chips--scroll part-nav">
        {keys.map((k) => (
          <button key={k} className="chip chip--pill" onClick={() => { haptic('select'); scrollToPart(k); }}>
            {partOf(project, k).status === 'approved' ? '✅ ' : hasText(project, k) ? '✏️ ' : ''}{partLabel(k)}
          </button>
        ))}
      </div>
      <section className="card">
        <p className="card__hint">{t("Butun ish shu yerda — yuqoridan pastga. Bevosita tahrirlang (avtomatik saqlanadi) yoki «✨ AI»: kengaytirish, qisqartirish, imlo, ilmiy uslub, qayta yozish. Tasdiqlangan matn roziligingizsiz o'zgarmaydi.")}</p>
      </section>
      {keys.map((k) => (
        <DissPart key={k} partKey={k} project={project} data={data} edit={edit} runJob={runJob} call={call}
          locked={locked} go={go} onApproved={afterApprove} />
      ))}
      {allApproved && (
        <button className="btn btn--primary mt-12" onClick={() => go(nextStep)}>{t("Keyingi bosqich")} <ChevronRight size={18} /></button>
      )}
    </>
  );
}

/** Bitta qism — umumiy ustunning bir bo'lagi. */
function DissPart({ partKey: key, project, data, edit, runJob, call, locked, go, onApproved }) {
  const current = partOf(project, key);
  const written = hasText(project, key);
  const area = `part:${key}`;
  const ai = (address) => (i, op) => runJob('rewrite', { part: key, op, address: { ...address, paragraph: i } });
  const history = project.history?.[key] ?? [];

  async function approve(value) {
    if (await call('/approve-part', { part: key, approved: value }) && value) onApproved(key);
  }

  const head = (
    <div className="part-head" id={partAnchor(key)}>
      <h2>{partLabel(key)}{key.startsWith('chapter:') && current.title ? `. ${current.title}` : ''}</h2>
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
      <>
          {key === 'intro' && current.items.map((item, ii) => (
            <section key={ii} className="card">
              <div className="card__label">{item.label}</div>
              <Paragraphs list={item.paragraphs} disabled={locked} onAi={ai({ item: ii })} onChange={(fn) => edit(area, (p) => fn(p.intro.items[ii].paragraphs))} />
            </section>
          ))}
          {(key === 'conclusion' || key === 'annotation') && (
            <section className="card">
              <Paragraphs list={current.paragraphs} disabled={locked} onAi={ai({})} onChange={(fn) => edit(area, (p) => fn(p[key].paragraphs))} />
              <button className="btn btn--soft btn--sm mt-12" disabled={locked} onClick={() => edit(area, (p) => { p[key].paragraphs.push(''); })}><PlusIcon size={16} /> {t("Xatboshi qo'shish")}</button>
              {key === 'annotation' && (
                <Field label={t("Kalit so'zlar")} hint={t("vergul bilan")} max={600} value={current.keywords.join(', ')} disabled={locked}
                  onChange={(v) => edit(area, (p) => { p.annotation.keywords = v.split(',').map((x) => x.trim()).filter(Boolean); })} />
              )}
            </section>
          )}
          {key.startsWith('chapter:') && (() => {
            const ci = Number(key.slice(8));
            return (
              <>
                {current.sections.map((section, si) => (
                  <section key={si} className="card">
                    <div className="card__label">{ci + 1}.{si + 1}.</div>
                    <input className="field" maxLength={300} value={section.title} disabled={locked} onChange={(e) => edit(area, (p) => { p.chapters[ci].sections[si].title = e.target.value; })} />
                    <span className="field-label">{t("Matn")}</span>
                    <Paragraphs list={section.paragraphs} disabled={locked} onAi={ai({ section: si })} onChange={(fn) => edit(area, (p) => fn(p.chapters[ci].sections[si].paragraphs))} />
                    <button className="btn btn--soft btn--sm mt-12" disabled={locked} onClick={() => edit(area, (p) => { p.chapters[ci].sections[si].paragraphs.push(''); })}><PlusIcon size={16} /> {t("Xatboshi qo'shish")}</button>
                  </section>
                ))}
                {current.figures.length > 0 && (
                  <section className="card">
                    <div className="card__label">{t("Bobdagi rasm va jadvallar")}</div>
                    {current.figures.map((f) => <FigureView key={f.id} f={f} data={data} section={current.sections[f.section]?.title} />)}
                    <button className="link-btn mt-12" onClick={() => go('visuals')}>{t("Rasmlar bosqichida tahrirlash →")}</button>
                  </section>
                )}
                <section className="card">
                  <div className="card__label">{t("{n} bob bo'yicha xulosalar", { n: ROMAN[ci] })}</div>
                  <Paragraphs list={current.summary} disabled={locked} onAi={ai({ summary: true })} onChange={(fn) => edit(area, (p) => fn(p.chapters[ci].summary))} />
                </section>
              </>
            );
          })()}
          {history.length > 0 && (
            <details className="card history">
              <summary className="card__label">🕘 {t('Oldingi versiyalar ({n})', { n: history.length })}</summary>
              {history.map((h, i) => (
                <div key={i} className="history__row">
                  <span>{h.at} · {h.reason}</span>
                  <button className="link-btn" disabled={locked}
                    onClick={async () => { if (await confirmDialog(t("Shu versiya qaytarilsinmi? Hozirgi matn ham tarixga saqlanadi."))) call('/restore', { part: key, index: i }); }}>{t("Qaytarish")}</button>
                </div>
              ))}
            </details>
          )}
          <div className="btn-grid">
            <button className="btn btn--white btn--sm" disabled={locked}
              onClick={async () => { if (await confirmDialog(t('{name} qaytadan yozilsinmi? Hozirgi matn tarixga saqlanadi.', { name: partLabel(key) }))) runJob('generate', { part: key }); }}>{t("🔄 Qayta yaratish")}</button>
            {current.status === 'approved'
              ? <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => approve(false)}>{t("↩️ Qoralamaga qaytarish")}</button>
              : <button className="btn btn--primary btn--sm" disabled={locked} onClick={() => approve(true)}>{t("✅ Tasdiqlash")}</button>}
          </div>
      </>
    </>
  );
}

function FigureView({ f, data, section }) {
  return (
    <div className="figure-edit">
      {f.kind === 'table' ? (
        <div className="figure-table">
          <table>
            <thead><tr>{f.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
            <tbody>{f.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : f.file && <img src={`/api/diss-media/${data.mediaToken}/${f.file}`} alt="" className="figure-edit__img" />}
      <div className="figure-edit__meta">
        <b>{f.caption}</b>
        <span>{t({ table: 'Jadval', scheme: 'Sxema', illustration: 'Rasm', chart: 'Grafik' }[f.kind] ?? f.kind)}{section ? ` · «${section}»` : ''} · {t('Manba')}: {f.source}</span>
      </div>
    </div>
  );
}

// ===== 8. Rasmlar va jadvallar =====
function VisualsStep({ project, data, edit, call, locked, id, next }) {
  const { toast } = useApp();
  const input = useRef();
  const target = useRef(null);
  const [adding, setAdding] = useState(null); // { ci, section, kind, caption, source, columns, rows }

  async function onFile(e) {
    const file = e.target.files?.[0];
    const tg = target.current;
    if (!file || !tg) return;
    try {
      const { file: name } = await apiUpload(`/dissertations/${id}/upload?purpose=figure`, await prepareImage(file));
      if (tg.replace) {
        edit(`part:chapter:${tg.ci}`, (p) => { const f = p.chapters[tg.ci].figures.find((x) => x.id === tg.replace); if (f) f.file = name; });
      } else {
        setAdding({ ...tg, file: name });
      }
      haptic('success');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function saveNew() {
    const a = adding;
    const body = { part: `chapter:${a.ci}`, kind: a.kind, caption: a.caption, source: a.source, section: a.section };
    if (a.kind === 'table') {
      body.columns = a.columns.split('|').map((x) => x.trim()).filter(Boolean);
      body.rows = a.rows.split('\n').map((r) => r.split('|').map((x) => x.trim())).filter((r) => r.some(Boolean));
    } else {
      body.file = a.file;
    }
    if (await call('/figure', body)) setAdding(null);
  }

  return (
    <>
      <input ref={input} type="file" accept="image/*" hidden onChange={onFile} />
      {project.chapters.map((chapter, ci) => (
        <section key={ci} className="card">
          <div className="card__label">{t('{n} bob', { n: ROMAN[ci] })}: {chapter.title}</div>
          {!chapter.figures.length && <p className="card__hint">{t("Vizual materiallar yo'q")}{chapter.sections.some((s) => s.paragraphs.length) ? '' : t(" — bob hali yozilmagan")}.</p>}
          {chapter.figures.map((f) => (
            <div key={f.id}>
              <FigureView f={f} data={data} section={chapter.sections[f.section]?.title} />
              <input className="field" maxLength={300} value={f.caption} disabled={locked}
                onChange={(e) => edit(`part:chapter:${ci}`, (p) => { p.chapters[ci].figures.find((x) => x.id === f.id).caption = e.target.value; })} />
              <div className="figure-edit__actions">
                {f.kind !== 'table' && <button className="link-btn" disabled={locked} onClick={() => { target.current = { ci, replace: f.id }; input.current.value = ''; input.current.click(); }}>{t("Almashtirish")}</button>}
                <button className="link-btn" disabled={locked}
                  onClick={async () => { if (await confirmDialog(t("O'chirilsinmi?"))) edit(`part:chapter:${ci}`, (p) => { p.chapters[ci].figures = p.chapters[ci].figures.filter((x) => x.id !== f.id); }); }}>{t("O'chirish")}</button>
              </div>
            </div>
          ))}
          {chapter.sections.some((s) => s.paragraphs.length) && (
            <div className="btn-grid mt-12">
              <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => { target.current = { ci, kind: 'image', section: 0, caption: '', source: '' }; input.current.value = ''; input.current.click(); }}>{t("🖼 Rasm qo'shish")}</button>
              <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => setAdding({ ci, kind: 'table', section: 0, caption: '', source: '', columns: '', rows: '' })}>{t("📋 Jadval qo'shish")}</button>
            </div>
          )}
          {adding && adding.ci === ci && (
            <div className="item-edit">
              {adding.kind === 'image' && adding.file && <img src={`/api/diss-media/${data.mediaToken}/${adding.file}`} alt="" className="figure-edit__img" />}
              <label className="editor-field">
                <span className="field-label">{t("Qaysi paragrafga")}</span>
                <select className="field" value={adding.section} onChange={(e) => setAdding({ ...adding, section: Number(e.target.value) })}>
                  {chapter.sections.map((s, si) => <option key={si} value={si}>{ci + 1}.{si + 1}. {s.title}</option>)}
                </select>
              </label>
              <Field label={t("Nomi (izoh)")} max={300} value={adding.caption} onChange={(v) => setAdding({ ...adding, caption: v })} placeholder={t("Masalan: Tadqiqot modeli")} />
              <Field label={t("Manba")} hint={t('ixtiyoriy')} max={300} value={adding.source} onChange={(v) => setAdding({ ...adding, source: v })} placeholder={t("Muallif tomonidan tuzilgan")} />
              {adding.kind === 'table' && (
                <>
                  <Field label={t("Ustunlar")} hint={t("| bilan ajrating")} max={600} value={adding.columns} onChange={(v) => setAdding({ ...adding, columns: v })} placeholder={t("Ko'rsatkich | 2023 | 2024")} />
                  <Field label={t("Qatorlar")} hint={t("har qator — yangi satr, kataklar | bilan")} rows={4} max={6000} value={adding.rows} onChange={(v) => setAdding({ ...adding, rows: v })} placeholder={t('Korxonalar soni | 120 | 140')} />
                  <p className="card__hint">{t("Jadvalga faqat o'zingiz tekshirgan haqiqiy ma'lumotlarni yozing.")}</p>
                </>
              )}
              <div className="btn-grid mt-12">
                <button className="btn btn--white btn--sm" onClick={() => setAdding(null)}>{t("Bekor qilish")}</button>
                <button className="btn btn--primary btn--sm" disabled={locked} onClick={saveNew}>{t("Qo'shish")}</button>
              </div>
            </div>
          )}
        </section>
      ))}
      <button className="btn btn--primary" onClick={next('quality')}>{t("Tekshirishga o'tish")} <ChevronRight size={18} /></button>
    </>
  );
}

// ===== 10. Tekshirish =====
function QualityStep({ project, runJob, locked, next, id, reload }) {
  const q = project.quality;
  return (
    <>
      <section className="card">
        <div className="card__label">{t('Avtomatik sifat nazorati')} {q.at && <span className="card__hint">{q.at}</span>}</div>
        {!q.checks.length && <p className="card__hint">{t("Faylni olishdan oldin tekshiring: reja va matn, takrorlar, iqtiboslar, manbalar, rasmlar, hajm, kirish va xulosa mosligi.")}</p>}
        {q.checks.map((c) => (
          <div key={c.key} className={`check check--${c.status}`}>
            <span>{STATUS_ICON[c.status]}</span>
            <div><b>{c.label}</b><p>{c.detail}</p></div>
          </div>
        ))}
        {q.at && (
          <>
            <div className="card__label mt-12">{t("Mazmuniy muvofiqlik (AI taqrizi)")}</div>
            {q.review.length ? q.review.map((r, i) => (
              <div key={i} className="check check--warn">
                <span>⚠️</span>
                <div><b>{r.part}</b><p>{r.problem}</p>{r.suggestion && <p className="card__hint">💡 {r.suggestion}</p>}</div>
              </div>
            )) : <p className="card__hint">{project.conclusion.paragraphs.length ? t("Jiddiy nomuvofiqlik topilmadi.") : t("Umumiy xulosa yozilgach tekshiriladi.")}</p>}
          </>
        )}
        <button className="btn btn--primary mt-12" disabled={locked} onClick={() => runJob('quality')}>{q.at ? t("🔄 Qayta tekshirish") : t("🔍 Tekshirish")}</button>
      </section>
      <SourcesPanel project={project} id={id} runJob={runJob} locked={locked} reload={reload} />
      <button className="btn btn--primary" onClick={next('file')}>{t("Yuklab olishga o'tish")} <ChevronRight size={18} /></button>
    </>
  );
}

function SourcesPanel({ project, id, runJob, locked, reload }) {
  const { toast } = useApp();
  const [form, setForm] = useState(null);
  const [open, setOpen] = useState(false);
  async function save(keep, add = []) {
    try {
      await api(`/dissertations/${id}/sources`, { method: 'PUT', body: { keep, add } });
      await reload();
      return true;
    } catch (err) {
      toast(err.message, 'error');
      return false;
    }
  }
  const verified = useMemo(() => project.sources.filter((s) => s.verified).length, [project.sources]);
  return (
    <section className="card">
      <button className="card__label link-btn" onClick={() => setOpen(!open)}>📚 {t('Foydalanilgan adabiyotlar ({n}, tekshirilgan: {v})', { n: project.sources.length, v: verified })} {open ? '▲' : '▼'}</button>
      {open && (
        <>
          <p className="card__hint">{t("✓ — OpenAlex/Crossref bazasida haqiqatan mavjud ish (DOI yoki havola bilan). Qo'lda qo'shilganlari «tekshirilmagan» deb ko'rsatiladi.")}</p>
          {project.sources.map((s) => (
            <div key={s.n} className="source">
              <div>
                <span className={`badge ${s.verified ? '' : 'badge--warn'}`}>{s.verified ? t("✓ tekshirilgan") : t('tekshirilmagan')}</span>
                <b> [{s.n}]</b> {s.authors}. {s.title} ({s.year}){s.venue ? ` // ${s.venue}` : ''}
                {(s.doi || s.url) && <div className="source__link">{s.doi ? `DOI: ${s.doi}` : s.url}</div>}
              </div>
              <button className="icon-btn icon-btn--ghost" disabled={locked} aria-label={t("O'chirish")}
                onClick={async () => { if (await confirmDialog(t("Manba o'chirilsinmi? Unga havolalar faylda olib tashlanadi."))) save(project.sources.filter((x) => x.n !== s.n).map((x) => x.n)); }}><CloseIcon size={18} /></button>
            </div>
          ))}
          {form ? (
            <div className="item-edit">
              {[['authors', 'Muallif(lar)'], ['title', 'Nomi'], ['year', 'Yili'], ['venue', 'Nashr'], ['url', 'Havola (ixtiyoriy)']].map(([k, label]) => (
                <input key={k} className="field mt-12" placeholder={t(label)} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              ))}
              <div className="btn-grid mt-12">
                <button className="btn btn--white btn--sm" onClick={() => setForm(null)}>{t("Bekor qilish")}</button>
                <button className="btn btn--primary btn--sm" disabled={locked}
                  onClick={async () => { if (await save(project.sources.map((x) => x.n), [{ ...form, year: Number(form.year) }])) setForm(null); }}>{t("Qo'shish")}</button>
              </div>
            </div>
          ) : (
            <div className="btn-grid mt-12">
              <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => setForm({ authors: '', title: '', year: '', venue: '', url: '' })}><PlusIcon size={16} /> {t("Qo'lda qo'shish")}</button>
              <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => runJob('sources')}>{t("🔎 Yana qidirish")}</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// ===== 11. Yuklab olish =====
function FileStep({ project, data, runJob, locked, go }) {
  const { toast } = useApp();
  const left = partKeys(project).filter((k) => partOf(project, k).status !== 'approved').map(partLabel);
  const errors = project.quality.checks.filter((c) => c.status === 'error');
  async function get(fmt) {
    if (await runJob('export', { fmt })) toast(t("Fayl tekshirildi va Telegram chatga yuborildi 📩"));
  }
  async function redesign(design) {
    if (await runJob('design', { design })) toast(t("Yangi dizayndagi fayl Telegram chatga yuborildi 🎨"));
  }
  return (
    <>
      <section className="card">
        <div className="card__label">{left.length ? t("Qoralama") : t("🎉 Dissertatsiya tayyor")}</div>
        {left.length > 0 && <p className="note note--warn">{t('Hali tasdiqlanmagan: {list}. Faylni qoralama sifatida ham olish mumkin.', { list: left.join(', ') })}</p>}
        {!project.quality.at && <p className="note note--info">{t("Avval sifat nazoratini o'tkazish tavsiya etiladi.")}</p>}
        {errors.length > 0 && <p className="note note--warn">{t('Sifat nazoratida {n} ta muhim kamchilik bor', { n: errors.length })} — <button className="link-btn" onClick={() => go('quality')}>{t("ko'rish")}</button></p>}
        <p className="card__hint">{t("Fayl: titul → annotatsiya va kalit so'zlar → avtomatik mundarija → kirish → boblar (xulosalari bilan) → umumiy xulosa → adabiyotlar → ilovalar (sizning ma'lumotlaringiz). Fayl yuborishdan oldin ochilishi tekshiriladi.")}</p>
        <div className="btn-grid mt-12">
          <button className="btn btn--primary btn--sm" disabled={locked} onClick={() => get('docx')}>{t("📄 DOCX olish")}</button>
          {data.pdf ? <button className="btn btn--soft btn--sm" disabled={locked} onClick={() => get('pdf')}>{t("📕 PDF olish")}</button>
            : <button className="btn btn--soft btn--sm" disabled title={t("Serverda LibreOffice o'rnatilmagan")}>{t("📕 PDF (mavjud emas)")}</button>}
        </div>
        {data.documentId && (
          <button className="btn btn--white btn--sm mt-12" disabled={locked} onClick={() => downloadFile('documents', data.documentId).catch((e) => toast(e.message, 'error'))}>
            <DownloadIcon size={18} /> {t("Oxirgi faylni yuklab olish")}
          </button>
        )}
      </section>
      <DocDesignPicker current={project.design} locked={locked} onPick={redesign} />
      <div className="note note--info">{t("⚠️ Matn — qoralama: raqamlar, iqtiboslar va xulosalarni tekshiring va ilmiy rahbaringiz bilan kelishing. Haqiqiy ma'lumot bo'lmagan joylarda misollar «namunaviy» deb belgilangan.")}</div>
    </>
  );
}
