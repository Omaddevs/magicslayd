import { useCallback, useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { ImagePicker, LinkPicker } from '../components/News.jsx';
import NotifCard, { KindChip } from '../components/NotifCard.jsx';
import { Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { NOTIFY_KINDS, kindOf, timeAgo } from '../lib/notify.js';
import { confirmDialog, haptic } from '../lib/telegram.js';
import { DeliveryStats } from './NotificationDetail.jsx';

const TITLE_MAX = 120;
const BODY_MAX = 2000;
const POLL_MS = 3000;

/** Telegram'dagi ko'rinishi — bot yuboradigan xabar maketi. */
function TelegramPreview({ kind, title, body, image, link, button, botName }) {
  const meta = kindOf(kind);
  return (
    <div className="tg-preview">
      <div className="tg-preview__head">
        <span className="tg-preview__avatar">S</span>
        <b>{botName ? `@${botName}` : 'MagicSlayd'}</b>
      </div>
      <div className="tg-preview__bubble">
        {image && <img src={image} alt="" />}
        <div className="tg-preview__text">
          <b>{meta.icon} {title || t('Sarlavha')}</b>
          <p>{body || t('Xabar matni shu yerda chiqadi…')}</p>
          <span className="tg-preview__time">{t('hozir')}</span>
        </div>
      </div>
      {link?.startsWith('https://') && <div className="tg-preview__btn">{button || t('Batafsil')} ↗</div>}
      <div className="tg-preview__btn">📱 {t("Ilovada o'qish")}</div>
    </div>
  );
}

function Compose({ audience, onSent }) {
  const { boot, toast } = useApp();
  const [kind, setKind] = useState('yangilik');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [image, setImage] = useState(null);
  const [link, setLink] = useState('');
  const [button, setButton] = useState('');
  const [toBot, setToBot] = useState(true);
  const [view, setView] = useState('app');
  const [sending, setSending] = useState(false);

  const ready = title.trim().length > 0 && body.trim().length > 0;

  const send = async () => {
    if (!ready || sending) return;
    const question = toBot
      ? t('Xabar {n} ta foydalanuvchiga ilovada va Telegram botda yuboriladi. Davom etasizmi?', { n: audience ?? '…' })
      : t("Xabar ilovada barcha foydalanuvchilarga ko'rinadi (botga yuborilmaydi). Davom etasizmi?");
    if (!(await confirmDialog(question))) return;
    setSending(true);
    haptic('medium');
    try {
      await api('/admin/notifications', {
        method: 'POST',
        body: { kind, title, body, image: image?.name ?? '', link: link === 'https://' ? '' : link, button, toBot },
      });
      haptic('success');
      toast(t('Xabar yuborildi') + ' 🚀');
      setTitle('');
      setBody('');
      setImage(null);
      setLink('');
      setButton('');
      onSent();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setSending(false);
    }
  };

  const previewItem = { kind, title: title.trim(), preview: body.trim(), image: image?.url, read: false };

  return (
    <>
      <section className="bc-audience">
        <span className="bc-audience__icon" aria-hidden="true">👥</span>
        <span>
          <b>{audience == null ? '…' : t('{n} ta foydalanuvchi', { n: audience })}</b>
          <small>{t('Xabar hamma foydalanuvchilarga yuboriladi')}</small>
        </span>
      </section>

      <section className="card">
        <div className="card__label">{t('Xabar turi')}</div>
        <div className="bc-kinds" role="radiogroup">
          {Object.entries(NOTIFY_KINDS).map(([key, meta]) => (
            <button key={key} role="radio" aria-checked={kind === key}
              className={`bc-kind bc-kind--${meta.tone} ${kind === key ? 'bc-kind--on' : ''}`}
              onClick={() => { haptic('select'); setKind(key); }}>
              <span aria-hidden="true">{meta.icon}</span>
              {t(meta.label)}
            </button>
          ))}
        </div>

        <label className="field-label" htmlFor="bc-title">
          {t('Sarlavha')} <span className="bc-count">{title.length}/{TITLE_MAX}</span>
        </label>
        <input id="bc-title" className="field" maxLength={TITLE_MAX} value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder={t("Masalan: Yangi dizaynlar qo'shildi!")} />

        <label className="field-label" htmlFor="bc-body">
          {t('Xabar matni')} <span className="bc-count">{body.length}/{BODY_MAX}</span>
        </label>
        <textarea id="bc-body" className="field" rows={6} maxLength={BODY_MAX} value={body} onChange={(e) => setBody(e.target.value)}
          placeholder={t("To'liq matn. Havolalar (https://…) va @username bosiladigan bo'ladi.")} />

        <span className="field-label">{t('Rasm (ixtiyoriy)')}</span>
        <ImagePicker value={image} onChange={setImage} hint={t('Rasm tanlash — JPG yoki PNG')} />

        <LinkPicker link={link} setLink={setLink} button={button} setButton={setButton} />
      </section>

      <section className="card">
        <button type="button" className="bc-toggle" role="switch" aria-checked={toBot} onClick={() => { haptic('select'); setToBot((v) => !v); }}>
          <span className="bc-toggle__text">
            <b>✈️ {t('Telegram botga ham yuborish')}</b>
            <small>{toBot ? t('Har bir user bot chatida ham oladi') : t("Faqat ilovadagi qo'ng'iroqchada ko'rinadi")}</small>
          </span>
          <span className={`bc-switch ${toBot ? 'bc-switch--on' : ''}`}><span /></span>
        </button>
      </section>

      <div className="section-head">
        <h2>{t("Ko'rinishi")}</h2>
        <div className="bc-view" role="tablist">
          <button role="tab" aria-selected={view === 'app'} className={view === 'app' ? 'bc-view--on' : ''} onClick={() => setView('app')}>{t('Ilova')}</button>
          <button role="tab" aria-selected={view === 'bot'} className={view === 'bot' ? 'bc-view--on' : ''} onClick={() => setView('bot')}>Telegram</button>
        </div>
      </div>
      {view === 'app' ? (
        <NotifCard item={previewItem} preview />
      ) : (
        <TelegramPreview kind={kind} title={title.trim()} body={body.trim()} image={image?.url} link={link} button={button}
          botName={boot.settings.bot_username} />
      )}

      <div className="bottom-bar">
        <button className="btn btn--primary" disabled={!ready || sending} onClick={send}>
          {sending ? t('Yuborilmoqda...') : `🚀 ${t('Yuborish')}`}
        </button>
      </div>
    </>
  );
}

function History({ items, audience, reload }) {
  const { push, toast } = useApp();

  const stop = async (item) => {
    if (!(await confirmDialog(t("Botda tarqatish to'xtatilsinmi? Ilovada xabar qoladi.")))) return;
    try {
      await api(`/admin/notifications/${item.id}/stop`, { method: 'POST' });
      reload();
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  const remove = async (item) => {
    if (!(await confirmDialog(t("Xabar o'chirilsinmi? Ilovada hammadan o'chadi (botga yuborilganlari qoladi).")))) return;
    try {
      await api(`/admin/notifications/${item.id}`, { method: 'DELETE' });
      haptic('success');
      toast(t("O'chirildi"));
      reload();
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  if (items === null) return <Skeleton height={150} count={3} />;
  if (!items.length) {
    return (
      <div className="empty">
        <div className="empty__icon" style={{ fontSize: 30 }}>📭</div>
        <b>{t('Hali xabar yuborilmagan')}</b>
        <span>{t('«Yangi xabar» bo\'limida birinchi e\'loningizni yozing.')}</span>
      </div>
    );
  }
  return (
    <div className="bc-history">
      {items.map((item) => (
        <article key={item.id} className="card bc-item">
          <button className="bc-item__open" onClick={() => push('notification', { id: item.id })}>
            <span className="bc-item__top">
              <KindChip kind={item.kind} />
              {item.mode === 'forward' && <span className="badge">↪️ {t('Forward')}</span>}
              {!item.inApp && <span className="badge">🤖 {t('Faqat bot')}</span>}
              <span className="bc-item__time">{timeAgo(item.createdAt)}</span>
            </span>
            <b className="bc-item__title">{item.title}</b>
            <span className="bc-item__text">{item.body}</span>
          </button>
          <DeliveryStats item={item} audience={null} />
          <div className="bc-item__actions">
            {['queued', 'sending'].includes(item.bot.status) && (
              <button className="btn btn--soft btn--sm" onClick={() => stop(item)}>⏸ {t("To'xtatish")}</button>
            )}
            <button className="btn btn--sm bc-item__delete" onClick={() => remove(item)}>🗑 {t("O'chirish")}</button>
          </div>
        </article>
      ))}
      <p className="card__hint" style={{ textAlign: 'center' }}>{t('Jami foydalanuvchilar: {n}', { n: audience ?? '…' })}</p>
    </div>
  );
}

/** Admin: barcha userlarga bildirishnoma yuborish (ilova + Telegram bot). */
export default function Broadcast() {
  const [tab, setTab] = useState('new');
  const [items, setItems] = useState(null);
  const [audience, setAudience] = useState(null);

  const load = useCallback(() => {
    api('/admin/notifications')
      .then((data) => {
        setItems(data.items);
        setAudience(data.audience);
      })
      .catch(() => setItems([]));
  }, []);

  useEffect(load, [load]);

  // Bot tarqatayotgan paytda statistika jonli yangilanadi
  const active = (items || []).some((i) => ['queued', 'sending'].includes(i.bot.status));
  useEffect(() => {
    if (!active || tab !== 'history') return undefined;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [active, tab, load]);

  return (
    <main className="page" style={{ paddingBottom: tab === 'new' ? 'calc(110px + var(--safe-bottom))' : undefined }}>
      <TopBar title={t('Xabar yuborish')} />
      <div className="segment" role="tablist" style={{ marginBottom: 12 }}>
        <button role="tab" aria-selected={tab === 'new'} className={tab === 'new' ? 'segment--active' : ''} onClick={() => setTab('new')}>
          ✏️ {t('Yangi xabar')}
        </button>
        <button role="tab" aria-selected={tab === 'history'} className={tab === 'history' ? 'segment--active' : ''} onClick={() => setTab('history')}>
          📬 {t('Yuborilganlar')} {items?.length ? `(${items.length})` : ''}
        </button>
      </div>
      {tab === 'new' ? (
        <Compose audience={audience} onSent={() => { load(); setTab('history'); }} />
      ) : (
        <History items={items} audience={audience} reload={load} />
      )}
    </main>
  );
}
