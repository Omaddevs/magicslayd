import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { t } from '../lib/i18n.js';

import { useApp } from '../app/AppContext.jsx';
import { CloseIcon, DownloadIcon, PlusIcon, SendIcon } from '../components/Icons.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api, apiUpload } from '../lib/api.js';
import { downloadFile } from '../lib/download.js';
import { clone, pollOrder } from '../lib/editing.js';
import { prepareImage } from '../lib/media.js';
import { KIND_LABEL } from '../lib/services.js';
import { confirmDialog, haptic, setClosingConfirmation } from '../lib/telegram.js';

// Referat / mustaqil ish / kurs ishi muharriri. Tuzilma bot yozgani bilan bir xil (documents/builder.py):
// titul → mundarija (avtomatik) → kirish → boblar (bo'limlar, xatboshilar, rasm) → xulosa → adabiyotlar.
// Muharrirda hammasi bitta varaqda, Word'dagidek yuqoridan pastga (bo'limlarga bo'linmaydi).
const TITLE_FIELDS = [
  ['university', "O'quv muassasasi", 'Masalan: Toshkent davlat iqtisodiyot universiteti'],
  ['faculty', 'Fakultet / kafedra', 'Masalan: Iqtisodiyot fakulteti'],
  ['subject', 'Fan nomi', 'Masalan: Makroiqtisodiyot'],
  ['student', 'Talaba (F.I.Sh.)', 'Masalan: Aliyev Vali Karimovich'],
  ['group', 'Guruh / sinf', 'Masalan: IQ-21-01'],
  ['teacher', "O'qituvchi", 'Masalan: i.f.n., dots. Karimov A.B.'],
  ['city', 'Shahar', 'Masalan: Toshkent'],
];

export default function PaperEditor({ docId }) {
  const { toast, setLeaveGuard } = useApp();
  const [paper, setPaper] = useState(null);
  const [error, setError] = useState(null);
  const [content, setContent] = useState(null);
  const [titlePage, setTitlePage] = useState({});
  const [version, setVersion] = useState(0); // har bir o'zgarishda +1
  const [savedVersion, setSavedVersion] = useState(0);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const fileInput = useRef();
  const pendingUpload = useRef(null);

  const dirty = version !== savedVersion;

  // ===== Yuklash. Loyihasi yo'q (eski ish) — avval bot uni DOCX/PDF fayldan tiklaydi =====
  useEffect(() => {
    let alive = true;
    async function load(retry = true) {
      try {
        const data = await api(`/papers/${docId}`);
        if (!alive) return;
        setPaper(data);
        setContent(data.content);
        setTitlePage(data.titlePage);
        if (data.pendingOrder) waitOrder(data.pendingOrder).catch((err) => toast(err.message, 'error'));
      } catch (err) {
        if (!(err.status === 404 && err.data.importable && retry)) throw err;
        setPreparing(true);
        const orderId = err.data.pendingImport ?? (await api(`/papers/${docId}/import`, { method: 'POST' })).orderId;
        if (orderId) await pollOrder(orderId);
        if (alive) await load(false);
      }
    }
    load()
      .catch((err) => alive && setError(err))
      .finally(() => alive && setPreparing(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  // Saqlanmagan o'zgarish bilan chiqib ketishdan himoya
  useEffect(() => {
    setClosingConfirmation(dirty);
    setLeaveGuard(dirty ? () => confirmDialog(t("O'zgarishlar saqlanmagan. Chiqib ketasizmi?")) : null);
  }, [dirty, setLeaveGuard]);
  useEffect(() => () => {
    setClosingConfirmation(false);
    setLeaveGuard(null);
  }, [setLeaveGuard]);

  const media = useCallback((name) => (name && paper ? `/api/paper-media/${paper.mediaToken}/${name}` : null), [paper]);

  /** O'zgartirish: fn kontent nusxasini o'zgartiradi. */
  const edit = useCallback((fn) => {
    setContent((prev) => {
      const next = clone(prev);
      fn(next);
      return next;
    });
    setVersion((v) => v + 1);
  }, []);

  // ===== Saqlash: loyiha serverga, bot faylni AI'siz qayta yasaydi =====
  async function waitOrder(orderId) {
    setSaving(true);
    try {
      return await pollOrder(orderId);
    } finally {
      setSaving(false);
    }
  }

  async function save({ quiet = false } = {}) {
    const snapshot = version;
    setSaving(true);
    try {
      const { orderId } = await api(`/papers/${docId}`, { method: 'PUT', body: { content, titlePage } });
      await waitOrder(orderId);
      setSavedVersion(snapshot);
      haptic('success');
      if (!quiet) toast(t("Saqlandi ✅ Yangi faylni yuklab olishingiz mumkin"));
      return true;
    } catch (err) {
      setSaving(false);
      toast(err.message, 'error');
      return false;
    }
  }

  async function download() {
    if (dirty && !(await save({ quiet: true }))) return;
    try {
      await downloadFile('documents', docId);
      toast(t("Yuklab olinmoqda ⬇️"));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function sendToChat() {
    if (dirty && !(await save({ quiet: true }))) return;
    try {
      await api(`/documents/${docId}/send`, { method: 'POST' });
      haptic('success');
      toast(t("Yangi fayl Telegram chatga yuborildi 📩"));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  // ===== Bob rasmi =====
  function pickImage(apply) {
    pendingUpload.current = apply;
    fileInput.current.value = '';
    fileInput.current.click();
  }

  async function onFile(event) {
    const file = event.target.files?.[0];
    const apply = pendingUpload.current;
    if (!file || !apply) return;
    setUploading(true);
    try {
      const { name } = await apiUpload(`/papers/${docId}/media`, await prepareImage(file));
      edit((draft) => apply(draft, name));
      haptic('success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(false);
    }
  }

  // ===== Ko'rinish =====
  if (error) {
    return (
      <main className="page">
        <TopBar title={t("Tahrirlash")} />
        <Empty icon="✏️" title={t("Tahrirlab bo'lmaydi")} text={error.message}>
          <button className="btn btn--primary btn--sm mt-12" onClick={() => downloadFile('documents', docId).catch((e) => toast(e.message, 'error'))}>
            <DownloadIcon size={18} /> {t("Yuklab olish")}
          </button>
        </Empty>
      </main>
    );
  }
  if (!paper || !content) {
    return (
      <main className="page">
        <TopBar title={t("Tahrirlash")} />
        {preparing && (
          <div className="card preparing">
            <div className="spinner" />
            <b>{t("Fayl tahrirlashga tayyorlanmoqda…")}</b>
            <span className="card__hint">{t("Titul, boblar, matn va rasmlar olinmoqda. Odatda 5–20 soniya.")}</span>
          </div>
        )}
        <div className="mt-12">
          <Skeleton height={60} count={4} />
        </div>
      </main>
    );
  }

  const words = countWords(content);

  return (
    <main className="page editor" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar
        title={t("Tahrirlash")}
        right={<span className={`badge ${dirty ? 'badge--warn' : ''}`}>{saving ? t("Saqlanmoqda…") : dirty ? t("Saqlanmagan") : t("Saqlangan ✓")}</span>}
      />
      <input ref={fileInput} type="file" accept="image/*" hidden onChange={onFile} />
      {paper.imported && !dirty && savedVersion === 0 && (
        <div className="note note--info" style={{ marginTop: 0, marginBottom: 12 }}>
          {t("📥 Fayldan tiklandi: titul, boblar va matn olindi. Ko'zdan kechirib, keyin «Saqlash» ni bosing — fayl standart talablar bo'yicha (Times New Roman 14, 1.5 interval) qayta yasaladi.")}
        </div>
      )}

      <div className="doc-meta">
        <span className="badge">{KIND_LABEL(paper.kind)}</span>
        <span className="badge">{paper.fmt.toUpperCase()}</span>
        <span className="doc-meta__stat">{content.chapters.length} bob · ~{Math.max(1, Math.round(words / 280) + 3)} bet · {words} so'z</span>
      </div>

      {/* Butun ish bitta varaqda — Word'dagidek yuqoridan pastga */}
      <article className="doc">
        <AutoText className="doc__title" max={paper.limits.title} value={content.title} placeholder={t("Ish mavzusi")}
          onChange={(v) => edit((d) => { d.title = v; })} />

        <TitleDetails titlePage={titlePage} limits={paper.limits}
          setField={(key, value) => { setTitlePage((prev) => ({ ...prev, [key]: value })); setVersion((v) => v + 1); }} />

        <h2 className="doc__h1">{t("Kirish")}</h2>
        <Paragraphs list={content.intro} max={paper.limits.intro} each={paper.limits.paragraph}
          change={(fn) => edit((d) => fn(d.intro))} />

        {content.chapters.map((chapter, ci) => (
          <Chapter key={ci} content={content} ci={ci} edit={edit} limits={paper.limits} media={media}
            uploading={uploading} pickImage={pickImage} />
        ))}

        <h2 className="doc__h1">{t("Xulosa")}</h2>
        <Paragraphs list={content.conclusion} max={paper.limits.conclusion} each={paper.limits.paragraph}
          change={(fn) => edit((d) => fn(d.conclusion))} />

        <h2 className="doc__h1">{t("Foydalanilgan adabiyotlar")}</h2>
        <References content={content} edit={edit} limits={paper.limits} />

        <p className="doc__note">{t("Mundarija, sahifa raqamlari va bob/bo'lim raqamlari faylda avtomatik tuziladi.")}</p>
      </article>

      <div className="bottom-bar editor-bar">
        <button className="btn btn--primary" onClick={() => save()} disabled={saving || !dirty}>
          {saving ? t("Saqlanmoqda…") : dirty ? t("Saqlash") : t("Saqlangan ✓")}
        </button>
        <button className="icon-btn icon-btn--lg pressable" onClick={download} disabled={saving} aria-label={t("Yuklab olish")}>
          <DownloadIcon size={24} />
        </button>
        <button className="icon-btn icon-btn--lg pressable" onClick={sendToChat} disabled={saving} aria-label={t("Telegram chatga yuborish")}>
          <SendIcon size={22} />
        </button>
      </div>
    </main>
  );
}

function countWords(content) {
  const all = [...content.intro, ...content.conclusion, ...content.chapters.flatMap((c) => c.sections.flatMap((s) => s.paragraphs))];
  return all.reduce((sum, text) => sum + (text.trim() ? text.trim().split(/\s+/).length : 0), 0);
}

// ===== Hujjat qismlari (hammasi bitta varaqda) =====

/** Matn uzunligiga qarab o'zi o'sadigan maydon — ichida aylantirish (scroll) bo'lmaydi. */
function AutoText({ value, onChange, className = '', max, placeholder, onFocus }) {
  const ref = useRef(null);
  const fit = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);
  useLayoutEffect(fit, [value, fit]);
  useEffect(() => {
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [fit]);
  return (
    <textarea ref={ref} rows={1} className={`doc-input ${className}`} maxLength={max} placeholder={placeholder}
      value={value ?? ''} onChange={(e) => onChange(e.target.value)} onFocus={onFocus} />
  );
}

/** Titul (muqova) ma'lumotlari — yig'ilgan holda; kerak bo'lsa ochiladi. */
function TitleDetails({ titlePage, setField, limits }) {
  const filled = TITLE_FIELDS.filter(([key]) => titlePage[key]?.trim()).length;
  return (
    <details className="doc-cover">
      <summary>
        <span>{t("📄 Titul ma'lumotlari")}</span>
        <span className="doc-cover__count">{filled}/{TITLE_FIELDS.length}</span>
      </summary>
      <div className="doc-cover__grid">
        {TITLE_FIELDS.map(([key, label, hint]) => (
          <label key={key} className="editor-field">
            <span className="field-label">{t(label)}</span>
            <input className="field" maxLength={limits.titleField} placeholder={hint.replace('Masalan:', t('Masalan:'))} value={titlePage[key] ?? ''}
              onChange={(e) => setField(key, e.target.value)} />
          </label>
        ))}
      </div>
      <p className="card__hint mt-8">{t("Bo'sh qoldirilgan maydonlar muqovaga yozilmaydi.")}</p>
    </details>
  );
}

/** Xatboshilar: oddiy matn kabi; amallar (↑ ↓ ✕) faqat xatboshi tanlanganda ko'rinadi. */
function Paragraphs({ list, max, each, change }) {
  return (
    <div className="doc-paras">
      {list.map((text, i) => (
        <div key={i} className="doc-para">
          <AutoText className="doc-para__text" max={each} value={text} placeholder={t("Matnni shu yerga yozing")}
            onChange={(v) => change((l) => { l[i] = v; })} />
          <div className="doc-para__tools">
            <button className="doc-tool" aria-label={t("Yuqoriga")} disabled={i === 0}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => change((l) => { [l[i - 1], l[i]] = [l[i], l[i - 1]]; })}>↑</button>
            <button className="doc-tool" aria-label={t("Pastga")} disabled={i === list.length - 1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => change((l) => { [l[i], l[i + 1]] = [l[i + 1], l[i]]; })}>↓</button>
            <button className="doc-tool doc-tool--danger" aria-label={t("Xatboshini o'chirish")} disabled={list.length <= 1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={async () => {
                if (text.trim() && !(await confirmDialog(t("Bu xatboshini o'chirasizmi?")))) return;
                change((l) => { l.splice(i, 1); });
              }}>
              <CloseIcon size={14} />
            </button>
          </div>
        </div>
      ))}
      {list.length < max && (
        <button className="doc-add" onClick={() => change((l) => { l.push(''); })}>
          <PlusIcon size={14} /> {t("Xatboshi")}
        </button>
      )}
    </div>
  );
}

function Figure({ image, media, uploading, hint, onPick, onRemove }) {
  return (
    <div className={`doc-figure ${image ? '' : 'doc-figure--empty'}`}>
      {image && <img src={media(image)} alt="" />}
      <div className="doc-figure__bar">
        <span className="card__hint">{image ? t("Rasm") : hint}</span>
        <button className="doc-add" disabled={uploading} onClick={onPick}>
          {uploading ? t("Yuklanmoqda…") : image ? t("🖼 Almashtirish") : t("🖼 Rasm qo'shish")}
        </button>
        {image && (
          <button className="doc-add" disabled={uploading} onClick={onRemove}>
            <CloseIcon size={12} /> {t("Olib tashlash")}
          </button>
        )}
      </div>
    </div>
  );
}

function Chapter({ content, ci, edit, limits, media, uploading, pickImage }) {
  const chapter = content.chapters[ci];
  const set = (fn) => edit((d) => fn(d.chapters[ci]));

  return (
    <section className="doc-chapter">
      <div className="doc__h1 doc__h1--chapter">
        <span className="doc__num">{ci + 1}-BOB.</span>
        <AutoText className="doc__h1-input" max={limits.heading} value={chapter.title} placeholder={t("Bob nomi")}
          onChange={(v) => set((c) => { c.title = v; })} />
      </div>

      {chapter.sections.map((section, si) => (
        <div key={si} className="doc-section">
          <div className="doc__h2">
            <span className="doc__num">{ci + 1}.{si + 1}.</span>
            <AutoText className="doc__h2-input" max={limits.heading} value={section.title} placeholder={t("Bo'lim nomi")}
              onChange={(v) => set((c) => { c.sections[si].title = v; })} />
            {chapter.sections.length > 1 && (
              <button className="doc-tool doc-tool--danger" aria-label={t("{n}-bo'limni o'chirish", { n: `${ci + 1}.${si + 1}` })}
                onClick={async () => {
                  if (!(await confirmDialog(t("{n}-bo'limni o'chirasizmi?", { n: `${ci + 1}.${si + 1}` })))) return;
                  set((c) => { c.sections.splice(si, 1); });
                }}>
                <CloseIcon size={14} />
              </button>
            )}
          </div>
          <Paragraphs list={section.paragraphs} max={limits.paragraphs} each={limits.paragraph}
            change={(fn) => set((c) => fn(c.sections[si].paragraphs))} />
          {/* Rasm faylda bo'limning birinchi xatboshisidan keyin turadi — muharrirda ham shu joyda.
              Birinchi bo'limda — bob rasmi, qolganlarida — bo'lim rasmi */}
          <Figure
            image={si === 0 ? chapter.image : section.image}
            media={media}
            uploading={uploading}
            hint={si === 0 ? t("Bob rasmi (ixtiyoriy)") : t("Bo'lim rasmi (ixtiyoriy)")}
            onPick={() => pickImage((d, name) => {
              if (si === 0) d.chapters[ci].image = name;
              else d.chapters[ci].sections[si].image = name;
            })}
            onRemove={() => set((c) => { if (si === 0) c.image = null; else c.sections[si].image = null; })}
          />
        </div>
      ))}

      <div className="doc-chapter__actions">
        <button className="doc-add" disabled={chapter.sections.length >= limits.sections}
          onClick={() => set((c) => { c.sections.push({ title: t("Yangi bo'lim"), paragraphs: [''] }); })}>
          <PlusIcon size={14} /> {t("Bo'lim")}
        </button>
        <button className="doc-add" disabled={content.chapters.length >= limits.chapters}
          onClick={() => edit((d) => {
            d.chapters.splice(ci + 1, 0, { title: t('Yangi bob'), image: null, sections: [{ title: t("Yangi bo'lim"), paragraphs: [''] }] });
          })}>
          <PlusIcon size={14} /> {t("Yangi bob")}
        </button>
        <button className="doc-add doc-add--danger" disabled={content.chapters.length <= 1}
          onClick={async () => {
            if (!(await confirmDialog(t("{n}-bobni butunlay o'chirasizmi?", { n: ci + 1 })))) return;
            edit((d) => { d.chapters.splice(ci, 1); });
          }}>
          {t("🗑 Bobni o'chirish")}
        </button>
      </div>
    </section>
  );
}

function References({ content, edit, limits }) {
  const list = content.references;
  return (
    <div className="doc-refs">
      {list.map((ref, i) => (
        <div key={i} className="doc-ref">
          <span className="doc__num">{i + 1}.</span>
          <AutoText className="doc-ref__text" max={limits.reference} value={ref} placeholder={t("Muallif. Kitob nomi. — Shahar: Nashriyot, Yil.")}
            onChange={(v) => edit((d) => { d.references[i] = v; })} />
          <button className="doc-tool doc-tool--danger" onClick={() => edit((d) => { d.references.splice(i, 1); })} aria-label={t("O'chirish")}>
            <CloseIcon size={14} />
          </button>
        </div>
      ))}
      {list.length < limits.references && (
        <button className="doc-add" onClick={() => edit((d) => { d.references.push(''); })}>
          <PlusIcon size={14} /> {t("Adabiyot")}
        </button>
      )}
    </div>
  );
}
