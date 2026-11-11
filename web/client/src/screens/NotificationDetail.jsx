import { Fragment, useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { ChevronRight } from '../components/Icons.jsx';
import { useOpenTarget } from '../components/News.jsx';
import { KindChip } from '../components/NotifCard.jsx';
import { Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { fullDate } from '../lib/notify.js';
import { haptic, openLink } from '../lib/telegram.js';

const URL_RE = /(https:\/\/[^\s]+|@[A-Za-z][\w]{3,31})/g;

/** Matndagi https://… va @username bosiladigan havolaga aylanadi. */
function RichText({ text }) {
  return text.split(/\n{2,}/).map((para, i) => (
    <p key={i}>
      {para.split('\n').map((line, j) => (
        <Fragment key={j}>
          {j > 0 && <br />}
          {line.split(URL_RE).map((part, k) => {
            if (k % 2 === 0) return part;
            const href = part.startsWith('@') ? `https://t.me/${part.slice(1)}` : part.replace(/[.,!?)]+$/, '');
            return (
              <a key={k} href={href} onClick={(e) => { e.preventDefault(); openLink(href); }}>
                {part}
              </a>
            );
          })}
        </Fragment>
      ))}
    </p>
  ));
}

/** Admin uchun: bot orqali yetkazish va ilovada o'qilish statistikasi. */
export function DeliveryStats({ item, audience }) {
  const bot = item.bot;
  const total = bot.total || 0;
  const done = bot.sent + bot.failed;
  const pct = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const STATUS = {
    none: [t('Faqat ilovada'), 'muted'],
    queued: [t('Navbatda'), 'warn'],
    sending: [t('Yuborilmoqda… {p}%', { p: pct }), 'warn'],
    done: [t('Yuborildi'), 'ok'],
    cancelled: [t("To'xtatildi"), 'bad'],
  };
  const [label, tone] = STATUS[bot.status] ?? STATUS.none;
  return (
    <div className="dstats">
      <div className="dstats__head">
        <span>{t('Botda yetkazish')}</span>
        <span className={`dstats__status dstats__status--${tone}`}>{label}</span>
      </div>
      {item.toBot && (
        <div className="dstats__bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="dstats__grid">
        <div><b>{item.toBot ? bot.sent : '—'}</b><span>✅ {t('Yetkazildi')}</span></div>
        <div><b>{item.toBot ? bot.failed : '—'}</b><span>⛔ {t('Yetkazilmadi')}</span></div>
        <div><b>{item.reads}</b><span>👁 {t("Ilovada o'qidi")}</span></div>
      </div>
      {item.toBot && bot.failed > 0 && <p className="dstats__hint">{t("Yetkazilmadi — botni bloklagan yoki hisobini o'chirgan userlar.")}</p>}
      {audience != null && <p className="dstats__hint">{t('Jami foydalanuvchilar: {n}', { n: audience })}</p>}
    </div>
  );
}

export default function NotificationDetail({ id }) {
  const { boot, setUnread, toast, pop } = useApp();
  const openTarget = useOpenTarget();
  const [item, setItem] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [read, setRead] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    api(`/notifications/${id}`)
      .then((data) => {
        setItem(data.item);
        setUnread(data.unread);
      })
      .catch((error) => {
        if (error.status === 404) setMissing(true);
        else toast(error.message, 'error');
      });
    if (boot.adminPerms?.includes('broadcast')) api(`/admin/notifications/${id}`).then(setAdmin).catch(() => {});
  }, [id, boot.adminPerms, setUnread, toast]);

  const toggleRead = async () => {
    haptic('select');
    const next = !read;
    setRead(next);
    try {
      const { unread } = await api(`/notifications/${id}/read`, { method: 'POST', body: { read: next } });
      setUnread(unread);
      toast(next ? t("O'qilgan deb belgilandi") : t("O'qilmagan deb belgilandi"));
    } catch (error) {
      setRead(!next);
      toast(error.message, 'error');
    }
  };

  if (missing) {
    return (
      <main className="page">
        <TopBar title={t('Xabar')} />
        <div className="empty">
          <div className="empty__icon" style={{ fontSize: 30 }}>🗑</div>
          <b>{t("Xabar topilmadi yoki o'chirilgan.")}</b>
          <button className="btn btn--soft btn--sm mt-12" onClick={pop}>{t('Orqaga')}</button>
        </div>
      </main>
    );
  }

  return (
    <main className="page notif-detail">
      <TopBar title={t('Xabar')} />
      {item === null ? (
        <Skeleton height={120} count={3} />
      ) : (
        <article className="notif-article">
          {item.image && <img className="notif-article__image" src={item.image} alt="" />}
          <div className="notif-article__meta">
            <KindChip kind={item.kind} />
            <time>{fullDate(item.createdAt)}</time>
          </div>
          <h1 className="notif-article__title">{item.title}</h1>
          <div className="notif-article__body">
            <RichText text={item.body} />
          </div>
          {item.link && (
            <button className="btn btn--primary notif-article__cta" onClick={() => openTarget(item.link)}>
              {item.button || t('Batafsil')} <ChevronRight size={18} />
            </button>
          )}
          <div className="notif-article__actions">
            <button className="notif-action pressable" onClick={toggleRead}>
              <span className={`notif-action__dot ${read ? '' : 'notif-action__dot--on'}`} />
              {read ? t("O'qilmagan deb belgilash") : t("O'qilgan deb belgilash")}
            </button>
          </div>
          {admin && (
            <section className="card mt-16">
              <div className="card__label">📊 {t('Statistika (faqat admin)')}</div>
              <DeliveryStats item={admin.item} audience={admin.audience} />
            </section>
          )}
        </article>
      )}
    </main>
  );
}
