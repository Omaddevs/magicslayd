import { useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { api } from '../lib/api.js';
import { money, shortDate } from '../lib/format.js';
import { t } from '../lib/i18n.js';
import { SERVICES } from '../lib/services.js';
import { haptic } from '../lib/telegram.js';
import { TileArt } from './Art.jsx';
import { AuthSheet } from './Auth.jsx';
import ImportCard from './ImportCard.jsx';
import { PlusIcon } from './Icons.jsx';
import LanguageSheet from './LanguageSheet.jsx';
import { AdSheet, StorySheet } from './News.jsx';
import { Sheet, Skeleton } from './ui.jsx';

// ===== «+» — yangi buyurtma =====
function CreateSheet({ close }) {
  const { push } = useApp();
  const go = (name, props) => {
    haptic('light');
    close();
    push(name, props);
  };
  return (
    <Sheet title={t('Nima yaratamiz?')} onClose={close}>
      <div className="create-grid">
        {['pres', 'referat', 'kurs', 'mustaqil'].map((kind) => (
          <button key={kind} className={`tile tile--${SERVICES[kind].color} pressable`} onClick={() => go('order', { kind })}>
            <TileArt kind={kind} />
            <span className="tile__title">{t(SERVICES[kind].title)}</span>
            <span className="tile__sub">{t(SERVICES[kind].sub)}</span>
          </button>
        ))}
        <button className={`tile tile--${SERVICES.maqola.color} pressable`} onClick={() => go('article-order')}>
          <TileArt kind="maqola" />
          <span className="tile__title">{t(SERVICES.maqola.title)}</span>
          <span className="tile__sub">{t(SERVICES.maqola.sub)}</span>
        </button>
      </div>
      <button className="btn btn--white mt-12" onClick={() => go('templates')}>
        🎨 {t('Dizayndan boshlash')}
      </button>
      <div className="mt-12">
        <ImportCard onDone={close} />
      </div>
    </Sheet>
  );
}

// ===== Hamyon (Pro) =====
const TX_LABELS = {
  topup: ["Hisob to'ldirildi", '💳'],
  charge: ['Buyurtma', '🧾'],
  refund: ['Qaytarildi', '↩️'],
  admin: ["Admin o'zgartirdi", '🛠'],
  bonus: ['Bonus', '🎁'],
};

const PAYMENT_STATUS = {
  pending: ['⏳ Tekshiruvda', 'badge--warn'],
  approved: ['✅ Tasdiqlandi', 'badge--ok'],
  rejected: ['❌ Rad etildi', 'badge--bad'],
};

function WalletSheet({ close }) {
  const { topup, setBoot } = useApp();
  const [data, setData] = useState(null);
  const [payments, setPayments] = useState([]);

  useEffect(() => {
    api('/transactions')
      .then((result) => {
        setData(result);
        setBoot({ balance: result.balance });
      })
      .catch(() => setData({ balance: 0, transactions: [], pending: { n: 0, sum: 0 } }));
    api('/payments').then((result) => setPayments(result.payments)).catch(() => {});
  }, [setBoot]);

  return (
    <Sheet title={t('Hamyon')} onClose={close}>
      <section className="wallet">
        <div className="wallet__label">{t('Balansingiz')}</div>
        <div className="wallet__amount">{data ? money(data.balance) : '…'}</div>
        <div className="wallet__row">
          <span className="wallet__label">
            {data?.pending.n
              ? t('⏳ Tekshiruvda: {n} ta chek ({sum})', { n: data.pending.n, sum: money(data.pending.sum) })
              : t("Pul faqat fayl tayyor bo'lganda yechiladi")}
          </span>
          <button className="btn btn--sm pressable" onClick={() => topup()}>
            <PlusIcon size={16} /> {t("To'ldirish")}
          </button>
        </div>
      </section>
      <p className="card__hint mt-12" style={{ padding: '0 4px' }}>
        {t("Summani tanlaysiz → kartaga o'tkazasiz → chekni shu yerga yuklaysiz. Admin tasdiqlagach balansga tushadi.")}
      </p>

      {payments.length > 0 && (
        <>
          <div className="section-head">
            <h2>{t('Cheklarim')}</h2>
          </div>
          <div className="card">
            {payments.map((payment) => {
              const [label, tone] = PAYMENT_STATUS[payment.status] ?? [payment.status, ''];
              return (
                <div key={payment.id} className="tx">
                  <div className="tx__icon" style={{ background: 'var(--chip)' }}>🧾</div>
                  <div className="tx__body">
                    <b>{t("To'lov")} #{payment.id} · {money(payment.amount)}</b>
                    <span>{shortDate(payment.created_at)}</span>
                  </div>
                  <span className={`badge ${tone}`}>{t(label)}</span>
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className="section-head">
        <h2>{t('Oxirgi amallar')}</h2>
      </div>
      {data === null ? (
        <Skeleton height={56} count={3} />
      ) : data.transactions.length ? (
        <div className="card">
          {data.transactions.map((tx) => {
            const [label, icon] = TX_LABELS[tx.kind] ?? [tx.kind, '•'];
            return (
              <div key={tx.id} className="tx">
                <div className="tx__icon" style={{ background: tx.amount > 0 ? 'var(--ok-bg)' : 'var(--chip)' }}>
                  {icon}
                </div>
                <div className="tx__body">
                  <b>{t(label)}</b>
                  <span>
                    {tx.note ? `${tx.note} · ` : ''}
                    {shortDate(tx.created_at)}
                  </span>
                </div>
                <div className={`tx__amount ${tx.amount > 0 ? 'plus' : 'minus'}`}>
                  {tx.amount > 0 ? '+' : '−'}
                  {money(Math.abs(tx.amount))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="card__hint" style={{ textAlign: 'center', padding: 20 }}>
          {t("Hali amallar yo'q.")}
        </p>
      )}
    </Sheet>
  );
}

// ===== Yordam va narxlar =====
function HelpSheet({ close }) {
  const { boot } = useApp();
  const s = boot.settings;
  const last = (list) => list[list.length - 1];
  const range = (kind) => `${s.pages[kind][0]}–${last(s.pages[kind])} ${t('bet')}`;
  const rows = [
    ['📊 ' + t('Taqdimot'), `${s.slides.options[0]}–${last(s.slides.options)} ${t('slayd')}`, `${money(s.slides.price)} / ${t('slayd')}`],
    ['📄 ' + t('Referat'), range('referat'), `${money(s.page_price.referat)} / ${t('bet')}`],
    ['✍️ ' + t('Mustaqil ish'), range('mustaqil'), `${money(s.page_price.mustaqil)} / ${t('bet')}`],
    ['📚 ' + t('Kurs ishi'), range('kurs'), `${money(s.page_price.kurs)} / ${t('bet')}`],
  ];
  return (
    <Sheet title={t('Yordam va narxlar')} onClose={close}>
      <div className="card">
        {rows.map(([name, size, price]) => (
          <div key={name} className="summary-row">
            <span>
              {name}
              <br />
              <small className="muted">{size}</small>
            </span>
            <b>{price}</b>
          </div>
        ))}
      </div>
      <div className="card">
        <div className="card__label">{t('Qanday ishlaydi?')}</div>
        <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, fontWeight: 600, color: 'var(--ink-2)' }}>
          <li>{t("Profil → «To'ldirish» orqali hisobni to'ldiring")}</li>
          <li>{t("Titul ma'lumotlarini bir marta kiriting")}</li>
          <li>{t('Xizmatni tanlang, mavzu va hajmni belgilang')}</li>
          <li>{t('Tayyor fayl Telegram chatga keladi va «Loyihalar»da turadi')}</li>
        </ol>
        <div className="note note--info">
          💡 {t("Pul faqat fayl tayyor bo'lganda yechiladi — xato bo'lsa, avtomatik qaytariladi.")}
        </div>
      </div>
    </Sheet>
  );
}

// story-new / ad-new — faqat admin uchun (bosh sahifadagi «Qo'shish» va «+ Reklama»)
const SHEETS = {
  create: CreateSheet, wallet: WalletSheet, help: HelpSheet, auth: AuthSheet, language: LanguageSheet,
  'story-new': StorySheet, 'ad-new': AdSheet,
};

export default function Sheets() {
  const { sheet, closeSheet } = useApp();
  if (!sheet) return null;
  const Component = SHEETS[sheet.name];
  return Component ? <Component close={closeSheet} {...sheet.props} /> : null;
}
