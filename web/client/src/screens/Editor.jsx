import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t } from '../lib/i18n.js';

import { useApp } from '../app/AppContext.jsx';
import { ChevronRight, CloseIcon, DownloadIcon, PlusIcon, SendIcon } from '../components/Icons.jsx';
import SlideView from '../components/SlideView.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api, apiUpload } from '../lib/api.js';
import { downloadFile } from '../lib/download.js';
import { clone, pollOrder } from '../lib/editing.js';
import { prepareImage, VIDEO_TYPES } from '../lib/media.js';
import { confirmDialog, haptic, setClosingConfirmation } from '../lib/telegram.js';

const KIND_NAMES = { bullets: "Ro'yxat", cards: 'Kartalar', stats: 'Raqamlar', timeline: 'Bosqichlar', quote: 'Iqtibos' };
const HEADING_HINT = {
  bullets: 'Sarlavha (ixtiyoriy)',
  cards: 'Karta sarlavhasi',
  stats: 'Raqam: 1991, 75%, 8 mln',
  timeline: 'Sana yoki bosqich nomi',
};
/** Slaydlar ro'yxati: muqova, mundarija, reja, kontent slaydlari, xulosa (builder.py tartibida). */
function flatten(content) {
  const list = [{ type: 'cover' }, { type: 'contents' }, { type: 'plan' }];
  content.plans.forEach((plan, pi) => plan.slides.forEach((_, si) => list.push({ type: 'slide', pi, si })));
  list.push({ type: 'conclusion' });
  return list;
}

const LABEL = { cover: 'Muqova', contents: 'Mundarija', plan: 'Reja', conclusion: 'Xulosa' };

export default function Editor({ docId }) {
  const { boot, toast, setLeaveGuard } = useApp();
  const themes = boot.settings.themes;
  const [deck, setDeck] = useState(null);
  const [error, setError] = useState(null);
  const [content, setContent] = useState(null);
  const [theme, setTheme] = useState(null);
  const [author, setAuthor] = useState('');
  const [current, setCurrent] = useState(-1); // ochilgan (to'liq tahrirlanayotgan) slayd, -1 — hech biri
  const [version, setVersion] = useState(0); // har bir o'zgarishda +1
  const [savedVersion, setSavedVersion] = useState(0);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const fileInput = useRef();
  const pendingUpload = useRef(null);

  const dirty = version !== savedVersion;

  // ===== Yuklash. Loyihasi yo'q (eski yoki yuklangan fayl) — avval bot uni fayldan tiklaydi =====
  useEffect(() => {
    let alive = true;
    async function load(retry = true) {
      try {
        const data = await api(`/decks/${docId}`);
        if (!alive) return;
        setDeck(data);
        setContent(data.content);
        setTheme(data.theme);
        setAuthor(data.author);
        if (data.pendingOrder) waitOrder(data.pendingOrder).catch((err) => toast(err.message, 'error'));
      } catch (err) {
        if (!(err.status === 404 && err.data.importable && retry)) throw err;
        setPreparing(true);
        const orderId = err.data.pendingImport ?? (await api(`/decks/${docId}/import`, { method: 'POST' })).orderId;
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

  const slides = useMemo(() => (content ? flatten(content) : []), [content]);

  const media = useCallback(
    (name) => (name && deck ? `/api/media/${deck.mediaToken}/${name}` : null),
    [deck],
  );

  /** O'zgartirish: fn kontent nusxasini o'zgartiradi. */
  const edit = useCallback((fn) => {
    setContent((prev) => {
      const next = clone(prev);
      fn(next);
      return next;
    });
    setVersion((v) => v + 1);
  }, []);

  // ===== Saqlash: loyiha serverga, bot AI'siz qayta yig'adi =====
  async function waitOrder(orderId) {
    setSaving(true);
    try {
      return await pollOrder(orderId);
    } finally {
      setSaving(false);
    }
  }

  async function save({ quiet = false } = {}) {
    // Saqlash paytida qilingan o'zgarishlar «saqlanmagan» bo'lib qoladi
    const snapshot = version;
    setSaving(true);
    try {
      const { orderId } = await api(`/decks/${docId}`, { method: 'PUT', body: { content, theme, author } });
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

  // ===== Rasm / video yuklash =====
  function pickFile(kind, apply, key) {
    pendingUpload.current = { kind, apply, key };
    fileInput.current.accept = kind === 'video' ? VIDEO_TYPES.join(',') : 'image/*';
    fileInput.current.value = '';
    fileInput.current.click();
  }

  async function onFile(event) {
    const file = event.target.files?.[0];
    const target = pendingUpload.current;
    if (!file || !target) return;
    setUploading({ kind: target.kind, key: target.key });
    try {
      let blob = file;
      if (target.kind === 'image') {
        blob = await prepareImage(file);
      } else if (file.size > deck.limits.videoMax) {
        throw new Error(t('Video {n} MB dan oshmasin. Qisqaroq video tanlang.', { n: Math.round(deck.limits.videoMax / 1048576) }));
      }
      const { name, kind } = await apiUpload(`/decks/${docId}/media`, blob);
      if (kind !== target.kind) throw new Error(target.kind === 'video' ? t("Bu fayl video emas (MP4 yoki MOV tanlang).") : t("Bu fayl rasm emas."));
      edit((draft) => target.apply(draft, name));
      haptic('success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setUploading(null);
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
  if (!deck || !content) {
    return (
      <main className="page">
        <TopBar title={t("Tahrirlash")} />
        {preparing && (
          <div className="card preparing">
            <div className="spinner" />
            <b>{t("Fayl tahrirlashga tayyorlanmoqda…")}</b>
            <span className="card__hint">{t("Slaydlardagi matn, rasmlar va reja olinmoqda. Odatda 5–20 soniya.")}</span>
          </div>
        )}
        <div className="skeleton mt-12" style={{ aspectRatio: '16 / 9', minHeight: 120 }} />
        <div className="mt-16">
          <Skeleton height={60} count={3} />
        </div>
      </main>
    );
  }

  const view = { content, theme: themes[theme] ?? Object.values(themes)[0], lang: deck.lang, author };
  const total = slides.length;
  const imageCount = content.plans.reduce((sum, p) => sum + p.slides.filter((s) => s.image || s.video).length, 0);
  const busyKind = (key) => (uploading && uploading.key === key ? uploading.kind : null);

  return (
    <main className="page editor" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar
        title={t("Tahrirlash")}
        right={<span className={`badge ${dirty ? 'badge--warn' : ''}`}>{saving ? t("Saqlanmoqda…") : dirty ? t("Saqlanmagan") : t("Saqlangan ✓")}</span>}
      />
      <input ref={fileInput} type="file" hidden onChange={onFile} />
      {deck.imported && !dirty && savedVersion === 0 && (
        <div className="note note--info" style={{ marginTop: 0, marginBottom: 12 }}>
          {t("📥 Fayldan tiklandi: matn va rasmlar olindi, dizayn quyidagi mavzulardan biriga o'tkazildi. Slaydlarni ko'zdan kechirib, keyin «Saqlash» ni bosing.")}
        </div>
      )}

      {/* Dizayn */}
      <section className="card">
        <div className="card__label">{t("Dizayn")}</div>
        <div className="chips chips--scroll">
          {Object.entries(themes).map(([key, value]) => (
            <button
              key={key}
              className={`chip chip--pill ${theme === key ? 'chip--active' : ''}`}
              onClick={() => {
                haptic('select');
                setTheme(key);
                setVersion((v) => v + 1);
              }}
            >
              <span className="theme-dot" style={{ background: `linear-gradient(135deg, #${value.bg}, #${value.accent})` }} />
              {t(value.name)}
            </button>
          ))}
        </div>
      </section>

      <div className="deck-summary">
        <span>📑 {t('{n} ta slayd', { n: total })}</span>
        <span>🖼 {t('{n} ta rasm', { n: imageCount })}</span>
      </div>

      {/* Barcha slaydlar — bitta ustunda, har birining tagida tezkor tahrir */}
      <div className="deck-list">
        {slides.map((s, i) => {
          const key = `${s.type}-${s.pi}-${s.si}`;
          const open = current === i;
          const toggle = () => {
            haptic('select');
            setCurrent(open ? -1 : i);
          };
          const slide = s.type === 'slide' ? content.plans[s.pi].slides[s.si] : null;
          const label = s.type === 'slide' ? `${s.pi + 1}. ${content.plans[s.pi].title}` : t(LABEL[s.type]);
          return (
            <article key={key} className={`slide-card ${open ? 'slide-card--open' : ''}`}>
              <header className="slide-card__head">
                <span className="slide-card__num">{i + 1}</span>
                <span className="slide-card__label">{label}</span>
              </header>
              <SlideView deck={view} item={s} index={i + 1} total={total} media={media} />

              {s.type === 'cover' && (
                <div className="slide-card__quick">
                  <QuickTitle value={content.title} max={200} onChange={(v) => edit((d) => { d.title = v; })} />
                  <ImageButtons
                    image={content.cover_image} busy={busyKind(key)} locked={Boolean(uploading)}
                    onPick={() => pickFile('image', (d, name) => { d.cover_image = name; }, key)}
                    onRemove={() => edit((d) => { d.cover_image = null; })}
                  />
                </div>
              )}
              {s.type === 'slide' && (
                <div className="slide-card__quick">
                  <QuickTitle value={slide.title} max={150}
                    onChange={(v) => edit((d) => { d.plans[s.pi].slides[s.si].title = v; })} />
                  <ImageButtons
                    image={slide.image || slide.video} busy={busyKind(key)} locked={Boolean(uploading)}
                    onPick={() => pickFile('image', (d, name) => { Object.assign(d.plans[s.pi].slides[s.si], { image: name, video: null }); }, key)}
                    onRemove={() => edit((d) => { Object.assign(d.plans[s.pi].slides[s.si], { image: null, video: null }); })}
                  />
                </div>
              )}
              {s.type === 'contents' && (
                <p className="card__hint slide-card__hint">{t("Mundarija reja nomlari va slaydlar sonidan avtomatik tuziladi — alohida tahrirlash shart emas.")}</p>
              )}

              {s.type !== 'contents' && (
                <button className="slide-card__more pressable" onClick={toggle} aria-expanded={open}>
                  <span>{open ? t("Yopish") : s.type === 'slide' ? t("✏️ Matn va maketni tahrirlash") : s.type === 'cover' ? t("✏️ Kichik sarlavha va muallif") : t("✏️ Tahrirlash")}</span>
                  <ChevronRight size={18} className={open ? 'rot-90' : ''} />
                </button>
              )}

              {open && (
                <div className="slide-card__body">
                  {s.type === 'cover' && (
                    <CoverPanel content={content} author={author} edit={edit} compact
                      setAuthor={(value) => { setAuthor(value); setVersion((v) => v + 1); }} />
                  )}
                  {s.type === 'plan' && <PlanPanel content={content} edit={edit} />}
                  {s.type === 'conclusion' && <ConclusionPanel content={content} edit={edit} limit={deck.limits.conclusion} />}
                  {s.type === 'slide' && (
                    <SlidePanel
                      content={content} pi={s.pi} si={s.si} edit={edit} media={media} limits={deck.limits}
                      uploading={busyKind(key)} locked={Boolean(uploading)} pickFile={(kind, apply) => pickFile(kind, apply, key)}
                      current={current} setCurrent={setCurrent}
                    />
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>

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

// ===== Panellar =====
function Field({ label, value, onChange, max, rows, placeholder }) {
  const Tag = rows ? 'textarea' : 'input';
  return (
    <label className="editor-field">
      {label && <span className="field-label">{label}</span>}
      <Tag className="field" rows={rows} maxLength={max} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/** Slayd tagidagi sarlavha maydoni — bosib darhol yozish mumkin. */
function QuickTitle({ value, max, onChange }) {
  return (
    <label className="quick-title">
      <span className="field-label">{t("Sarlavha")}</span>
      <textarea className="field" rows={1} maxLength={max} value={value} placeholder={t("Sarlavha")}
        onChange={(e) => onChange(e.target.value)}
        onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = `${e.target.scrollHeight}px`; }} />
    </label>
  );
}

/** Slayd tagidagi rasm tugmalari: almashtirish (yoki qo'shish) va olib tashlash. */
function ImageButtons({ image, busy, locked, onPick, onRemove }) {
  return (
    <div className="quick-image">
      <button className="btn btn--soft btn--sm" onClick={onPick} disabled={locked}>
        {busy ? t("Yuklanmoqda…") : image ? t("🖼 Rasmni almashtirish") : t("🖼 Rasm qo'shish")}
      </button>
      {image && (
        <button className="quick-image__remove pressable" onClick={onRemove} disabled={locked}
          aria-label={t("Rasmni olib tashlash")} title={t("Rasmni olib tashlash")}>
          <CloseIcon size={18} />
        </button>
      )}
    </div>
  );
}

function MediaControl({ video, media, uploading, locked, onVideo, onRemove }) {
  return (
    <div className="media-box">
      {video && <video className="media-box__preview" src={media(video)} controls playsInline preload="metadata" />}
      <div className="media-box__actions">
        <button className="btn btn--soft btn--sm" onClick={onVideo} disabled={locked}>
          {uploading === 'video' ? t("Yuklanmoqda…") : video ? t("🎬 Videoni almashtirish") : t("🎬 Video qo'shish")}
        </button>
        {video && (
          <button className="btn btn--white btn--sm" onClick={onRemove} disabled={locked}>
            <CloseIcon size={14} /> {t("Olib tashlash")}
          </button>
        )}
      </div>
      <p className="card__hint">{t("Video: MP4 yoki MOV, 25 MB gacha. PowerPoint'da slayd ochilganda o'ynaydi.")}</p>
    </div>
  );
}

function CoverPanel({ content, author, setAuthor, edit }) {
  return (
    <>
      <Field label={t("Kichik sarlavha")} rows={2} max={300} value={content.subtitle} onChange={(v) => edit((d) => { d.subtitle = v; })} />
      <Field label={t("Muallif")} max={70} value={author} onChange={setAuthor} placeholder={t("Masalan: Aliyev Vali, 10-«A» sinf")} />
    </>
  );
}

function PlanPanel({ content, edit }) {
  return (
    <section className="card">
      <div className="card__label">{t("Reja bandlari")}</div>
      {content.plans.map((plan, i) => (
        <Field key={i} label={`${i + 1}-reja`} max={120} value={plan.title} onChange={(v) => edit((d) => { d.plans[i].title = v; })} />
      ))}
      <p className="card__hint mt-12">{t("Reja nomlari mundarija va slaydlar tepasidagi belgida ham yangilanadi.")}</p>
    </section>
  );
}

function ConclusionPanel({ content, edit, limit }) {
  const points = content.conclusion;
  return (
    <section className="card">
      <div className="card__label">{t("Xulosa")}</div>
      {points.map((point, i) => (
        <div key={i} className="item-row">
          <Field rows={2} max={300} value={point} onChange={(v) => edit((d) => { d.conclusion[i] = v; })} />
          {points.length > 1 && (
            <button className="icon-btn icon-btn--ghost" onClick={() => edit((d) => { d.conclusion.splice(i, 1); })} aria-label={t("O'chirish")}>
              <CloseIcon size={18} />
            </button>
          )}
        </div>
      ))}
      {points.length < limit && (
        <button className="btn btn--soft btn--sm mt-12" onClick={() => edit((d) => { d.conclusion.push(''); })}>
          <PlusIcon size={16} /> {t("Band qo'shish")}
        </button>
      )}
    </section>
  );
}

function SlidePanel({ content, pi, si, edit, media, limits, uploading, locked, pickFile, current, setCurrent }) {
  const plan = content.plans[pi];
  const slide = plan.slides[si];
  const [min, max] = limits.items[slide.kind];
  const isQuote = slide.kind === 'quote';
  const total = content.plans.reduce((sum, p) => sum + p.slides.length, 0);
  const set = (fn) => edit((d) => fn(d.plans[pi].slides[si], d));

  const move = (delta) => {
    edit((d) => {
      const list = d.plans[pi].slides;
      [list[si], list[si + delta]] = [list[si + delta], list[si]];
    });
    setCurrent(current + delta);
  };

  return (
    <>
      <section className="card">
        <span className="field-label">{t("Ko'rinishi")}</span>
        <div className="chips">
          {Object.entries(KIND_NAMES).map(([kind, name]) => (
            <button
              key={kind}
              className={`chip ${slide.kind === kind ? 'chip--active' : ''}`}
              onClick={() => {
                haptic('select');
                set((s) => {
                  s.kind = kind;
                  if (kind === 'quote' && !s.items.length) s.items = [{ heading: '', text: '' }];
                });
              }}
            >
              {t(name)}
            </button>
          ))}
        </div>
        {slide.items.length < min && (
          <p className="note note--warn">{t("«{kind}» uchun kamida {n} ta band kerak — aks holda ro'yxat ko'rinishida saqlanadi.", { kind: t(KIND_NAMES[slide.kind]), n: min })}</p>
        )}

        <Field
          label={isQuote ? t("Iqtibos matni") : t("Kirish jumlasi (ixtiyoriy)")}
          rows={isQuote ? 4 : 2} max={600} value={slide.text}
          onChange={(v) => set((s) => { s.text = v; })}
        />

        {isQuote ? (
          <Field
            label={t("Muallif (ixtiyoriy)")} max={80} value={slide.items[0]?.heading ?? ''}
            onChange={(v) => set((s) => { s.items = [{ heading: v, text: v }]; })}
          />
        ) : (
          <>
            <span className="field-label">{t('Bandlar ({n}/{max})', { n: slide.items.length, max })}</span>
            {slide.items.map((entry, i) => (
              <div key={i} className="item-edit">
                <div className="item-edit__head">
                  <b>{i + 1}</b>
                  <input className="field" maxLength={80} placeholder={t(HEADING_HINT[slide.kind] ?? '')} value={entry.heading}
                    onChange={(e) => set((s) => { s.items[i].heading = e.target.value; })} />
                  <button className="icon-btn icon-btn--ghost" aria-label={t("Bandni o'chirish")}
                    onClick={() => set((s) => { s.items.splice(i, 1); })}>
                    <CloseIcon size={18} />
                  </button>
                </div>
                <textarea className="field" rows={2} maxLength={400} placeholder={t("Matn")} value={entry.text}
                  onChange={(e) => set((s) => { s.items[i].text = e.target.value; })} />
              </div>
            ))}
            {slide.items.length < max && (
              <button className="btn btn--soft btn--sm mt-12" onClick={() => set((s) => { s.items.push({ heading: '', text: '' }); })}>
                <PlusIcon size={16} /> {t("Band qo'shish")}
              </button>
            )}
          </>
        )}
      </section>

      <section className="card">
        <div className="card__label">{t("Video")}</div>
        <MediaControl
          video={slide.video} media={media} uploading={uploading} locked={locked}
          onVideo={() => pickFile('video', (d, name) => { Object.assign(d.plans[pi].slides[si], { video: name, image: null }); })}
          onRemove={() => set((s) => { s.video = null; })}
        />
      </section>

      <section className="card">
        <div className="card__label">{t("Slayd amallari")}</div>
        <div className="btn-grid">
          <button className="btn btn--soft btn--sm" disabled={si === 0} onClick={() => move(-1)}>{t("⬅️ Oldinga")}</button>
          <button className="btn btn--soft btn--sm" disabled={si === plan.slides.length - 1} onClick={() => move(1)}>{t("Keyinga ➡️")}</button>
          <button
            className="btn btn--soft btn--sm"
            disabled={plan.slides.length >= limits.slidesPerPlan || total >= limits.slides}
            onClick={() => {
              edit((d) => {
                d.plans[pi].slides.splice(si + 1, 0, {
                  title: t('Yangi slayd'), kind: 'bullets', text: '', image: null, video: null,
                  items: [{ heading: '', text: t('Matnni shu yerga yozing') }],
                });
              });
              setCurrent(current + 1);
            }}
          >
            {t("➕ Yangi slayd")}
          </button>
          <button
            className="btn btn--white btn--sm"
            disabled={plan.slides.length <= 1}
            onClick={async () => {
              if (!(await confirmDialog(t("Bu slaydni o'chirasizmi?")))) return;
              edit((d) => { d.plans[pi].slides.splice(si, 1); });
              setCurrent(Math.max(0, si === plan.slides.length - 1 ? current - 1 : current));
            }}
          >
            {t("🗑 O'chirish")}
          </button>
        </div>
        {plan.slides.length <= 1 && <p className="card__hint mt-12">{t("Har bir rejada kamida bitta slayd qoladi.")}</p>}
      </section>
    </>
  );
}
