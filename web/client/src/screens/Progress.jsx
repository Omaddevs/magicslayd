import { useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { TileArt } from '../components/Art.jsx';
import { CheckIcon, CloseIcon, DownloadIcon, EditIcon, SendIcon } from '../components/Icons.jsx';
import { TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { downloadFile } from '../lib/download.js';
import { money } from '../lib/format.js';
import { downloadArticle } from '../lib/article.js';
import { PROGRESS_STEPS, SERVICES, orderSize } from '../lib/services.js';
import { t } from '../lib/i18n.js';
import { haptic, openBotChat } from '../lib/telegram.js';

const POLL_MS = 2500;
const PAYMENT_POLL_MS = 6000;
const STEP_MS = 5000; // bot ham har 5 soniyada keyingi bosqichni ko'rsatadi

export default function Progress({ orderId, kind: initialKind, payload }) {
  const { boot, setBoot, refreshBalance, replace, setTab, toast } = useApp();
  const [order, setOrder] = useState(null);
  const [step, setStep] = useState(0);
  const finished = useRef(false);

  const kind = order?.kind ?? initialKind;
  const service = SERVICES[kind] ?? SERVICES.referat;
  const isArticle = kind === 'maqola';
  const steps = PROGRESS_STEPS[kind === 'pres' ? 'pres' : isArticle ? 'article' : 'doc'];
  const status = order?.status ?? 'pending';

  // Holatni so'rab turish (bot web_orders jadvalini yangilaydi)
  useEffect(() => {
    let timer;
    let alive = true;
    async function poll() {
      let delay = POLL_MS;
      try {
        const data = await api(`/orders/${orderId}`);
        // Admin chekni tekshirguncha (daqiqalar) tez-tez so'rash shart emas
        if (data.status === 'awaiting_payment') delay = PAYMENT_POLL_MS;
        if (!alive) return;
        setOrder(data);
        if (data.status === 'done' || data.status === 'failed') {
          if (!finished.current) {
            finished.current = true;
            haptic(data.status === 'done' ? 'success' : 'error');
            refreshBalance().catch(() => {});
            if (data.status === 'done') setBoot({ documents: boot.documents + 1, activeOrder: null });
            else setBoot({ activeOrder: null });
          }
          return;
        }
      } catch (error) {
        if (error.status === 404) {
          toast(error.message, 'error');
          return;
        }
      }
      timer = setTimeout(poll, delay);
    }
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  // Bosqichlarni jonlantirish
  useEffect(() => {
    if (status !== 'working') return undefined;
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), STEP_MS);
    return () => clearInterval(timer);
  }, [status, steps.length]);

  const [downloading, setDownloading] = useState(false);
  async function download(fmt) {
    setDownloading(fmt || true);
    try {
      if (isArticle) await downloadArticle(order.document_id, fmt);
      else await downloadFile('documents', order.document_id);
      toast(t('Yuklab olinmoqda') + ' ⬇️');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setDownloading(false);
    }
  }

  const params = order?.params ?? payload ?? {};
  const size = orderSize(kind, params);
  const label = t(service.label);

  if (status === 'done') {
    return (
      <main className="page">
        <TopBar title={t('Tayyor!')} />
        <div className="progress">
          <div className="result-icon result-icon--ok">
            <CheckIcon size={58} />
          </div>
          <h2>{t('{name} tayyor!', { name: label })} 🎉</h2>
          <p>{order.document_title || params.topic}</p>
          <div className="note note--info" style={{ width: '100%' }}>
            📩 {t("Fayl Telegram chatingizga ham yuborildi va «Loyihalar» bo'limida turadi.")}
            {kind === 'pres' && ` ${t("PowerPoint, WPS yoki Google Slides'da ochib, istalgan joyini tahrirlashingiz mumkin.")}`}
          </div>
          {order.document_id && kind === 'pres' && (
            <button className="btn btn--primary mt-16" onClick={() => replace('editor', { docId: order.document_id })}>
              <EditIcon size={20} /> {t('Ochish va tahrirlash')}
            </button>
          )}
          {order.document_id && isArticle && (
            <>
              <button className="btn btn--primary mt-16" onClick={() => replace('article', { docId: order.document_id })}>
                <EditIcon size={20} /> {t('Ochish va tahrirlash')}
              </button>
              <div className="btn-row" style={{ width: '100%' }}>
                <button className="btn btn--white" onClick={() => download('docx')} disabled={Boolean(downloading)}>
                  <DownloadIcon size={20} /> {downloading === 'docx' ? t('Tayyorlanmoqda...') : 'Word'}
                </button>
                <button className="btn btn--white" onClick={() => download('pdf')} disabled={Boolean(downloading)}>
                  <DownloadIcon size={20} /> {downloading === 'pdf' ? t('Tayyorlanmoqda...') : 'PDF'}
                </button>
              </div>
            </>
          )}
          {order.document_id && !isArticle && (
            <button
              className={`btn ${kind === 'pres' ? 'btn--white mt-12' : 'btn--primary mt-16'}`}
              onClick={() => download()}
              disabled={Boolean(downloading)}
            >
              <DownloadIcon size={20} /> {downloading ? t('Tayyorlanmoqda...') : t('Yuklab olish')}
            </button>
          )}
          <button className="btn btn--soft mt-12" onClick={() => openBotChat(boot.settings.bot_username)}>
            <SendIcon size={20} /> {t('Chatda ochish')}
          </button>
          <div className="btn-row" style={{ width: '100%' }}>
            <button className="btn btn--soft" onClick={() => setTab('saved')}>
              {t('Loyihalar')}
            </button>
            <button className="btn btn--soft" onClick={() => (isArticle ? replace('article-order') : replace('order', { kind }))}>
              {t('Yana yaratish')}
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (status === 'failed') {
    return (
      <main className="page">
        <TopBar title={t('Xatolik')} />
        <div className="progress">
          <div className="result-icon result-icon--fail">
            <CloseIcon size={54} />
          </div>
          <h2>{t("Tayyorlab bo'lmadi")} 😕</h2>
          <div className="note note--error" style={{ width: '100%' }}>
            {t(order.error || 'Kutilmagan xato yuz berdi.')}
          </div>
          <button className="btn btn--primary mt-16" onClick={() => replace(isArticle ? 'article-order' : 'order', { kind, initial: params })}>
            {t('Qayta urinish')}
          </button>
          <button className="btn btn--soft mt-12" onClick={() => setTab('home')}>
            {t('Bosh sahifa')}
          </button>
        </div>
      </main>
    );
  }

  if (status === 'awaiting_payment') {
    return (
      <main className="page">
        <TopBar title={t("To'lov tekshirilmoqda")} />
        <div className="progress">
          <div className={`progress__badge tile--${service.color}`}>
            <TileArt kind={kind} />
          </div>
          <h2>{t('Chekingiz admin tekshiruvida')} ⏳</h2>
          <p>
            «{params.topic}» · {size}
          </p>
          <div className="card steps">
            <div className="step step--done"><span className="step__dot"><CheckIcon size={14} /></span>{t('Chek qabul qilindi')}</div>
            <div className="step step--current"><span className="step__dot" />{t("Admin to'lovni tasdiqlaydi")}</div>
            <div className="step"><span className="step__dot" />{t('{name} tayyorlanadi', { name: label })}</div>
            <div className="step"><span className="step__dot" />{t('Fayl sizga yuboriladi')}</div>
          </div>
          <div className="note note--info" style={{ width: '100%' }}>
            {t("Odatda 5–30 daqiqa. Ilovani yopsangiz ham bo'ladi — tasdiqlangach buyurtma avtomatik tayyorlanadi va fayl Telegram chatga keladi. Bu sahifa ham o'zi yangilanadi.")}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="page">
      <TopBar title={t('{name} tayyorlanmoqda', { name: label })} />
      <div className="progress">
        <div className="progress__ring">
          <svg className="spin" viewBox="0 0 168 168" aria-hidden="true">
            <circle cx="84" cy="84" r="76" fill="none" stroke="#ECE9F6" strokeWidth="8" />
            <circle cx="84" cy="84" r="76" fill="none" stroke="url(#ring)" strokeWidth="8" strokeLinecap="round" strokeDasharray="120 360" />
            <defs>
              <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#8B6BFF" />
                <stop offset="1" stopColor="#5E3FEA" />
              </linearGradient>
            </defs>
          </svg>
          <div className={`progress__badge tile--${service.color}`}>
            <TileArt kind={kind} />
          </div>
        </div>
        <h2>{status === 'pending' ? t('Navbatda turibdi...') : t("Sun'iy intellekt ishlamoqda...")}</h2>
        <p>
          {params.topic && <>«{params.topic}» · </>}
          {size}
          {order?.price ? ` · ${money(order.price)}` : ''}
        </p>
        {status === 'pending' && order?.ahead > 0 && (
          <div className="note note--info" style={{ width: '100%' }}>
            ⏳ {t('Sizdan oldin {n} ta buyurtma bor. Bir necha soniyada boshlanadi.', { n: order.ahead })}
          </div>
        )}

        <div className="card steps">
          {steps.map((text, i) => {
            const state = status !== 'working' ? '' : i < step ? 'step--done' : i === step ? 'step--current' : '';
            return (
              <div key={text} className={`step ${state}`}>
                <span className="step__dot">{state === 'step--done' && <CheckIcon size={14} />}</span>
                {t(text)}
              </div>
            );
          })}
        </div>
        <p className="mt-16">
          {t('Odatda 20–60 soniya vaqt oladi. Ilovani yopsangiz ham fayl Telegram chatga keladi.')}
        </p>
      </div>
    </main>
  );
}
