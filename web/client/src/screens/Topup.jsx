import { useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { CheckIcon, CloseIcon } from '../components/Icons.jsx';
import { TopBar } from '../components/ui.jsx';
import { api, apiUpload } from '../lib/api.js';
import { copyText } from '../lib/clipboard.js';
import { money } from '../lib/format.js';
import { prepareImage } from '../lib/media.js';
import { SERVICES, orderSize } from '../lib/services.js';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';

const STEPS = ['Summa', "To'lov", 'Chek'];
const STATUS_POLL_MS = 8000;

const groupDigits = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
const lastDigits = (number) => number.replace(/\s/g, '').slice(-4);

const ORDER_PAY_MIN = 1000; // bot va server bilan bir xil

/** Hisobni to'ldirish: summa → karta raqami → chek. Chek bot orqali adminga boradi (botdagi bilan bitta tizim).
 *  order berilsa — shu buyurtma uchun to'lov: summa aniq, admin tasdiqlagach buyurtma o'zi tayyorlanadi. */
export default function Topup({ need = 0, order = null, price = 0 }) {
  const { boot, setBoot, toast, pop, replace, topupViaBot } = useApp();
  const pay = boot.settings.payment;
  const suggested = need > 0 ? Math.min(Math.max(Math.ceil(need / 1000) * 1000, pay?.min ?? 0), pay?.max ?? need) : null;
  const orderAmount = order ? Math.max(need, ORDER_PAY_MIN) : 0;

  const [step, setStep] = useState(order ? 1 : 0);
  const [amount, setAmount] = useState(suggested ?? pay?.options?.[1] ?? 20000);
  const [custom, setCustom] = useState('');
  const [receipt, setReceipt] = useState(null); // { blob, url, name, pdf }
  const [sending, setSending] = useState(false);
  const [paymentId, setPaymentId] = useState(null);
  const [status, setStatus] = useState(null); // pending | approved | rejected
  const [pending, setPending] = useState(0);
  const fileInput = useRef();

  useEffect(() => {
    api('/payments').then((data) => setPending(data.pending)).catch(() => {});
  }, []);

  // Yuborilgan chek holatini kuzatish — admin tasdiqlasa, balans darhol yangilanadi
  useEffect(() => {
    if (!paymentId || status !== 'pending') return undefined;
    const timer = setInterval(async () => {
      try {
        const data = await api('/payments');
        const payment = data.payments.find((p) => p.id === paymentId);
        if (payment && payment.status !== 'pending') {
          setStatus(payment.status);
          setBoot({ balance: data.balance });
          haptic(payment.status === 'approved' ? 'success' : 'error');
        }
      } catch {
        // tarmoq uzilsa — keyingi urinishda
      }
    }, STATUS_POLL_MS);
    return () => clearInterval(timer);
  }, [paymentId, status, setBoot]);

  useEffect(() => () => receipt?.url && URL.revokeObjectURL(receipt.url), [receipt]);

  const title = order ? t("Buyurtma uchun to'lov") : t("Hisobni to'ldirish");
  if (!pay?.enabled) {
    return (
      <main className="page">
        <TopBar title={title} />
        <div className="note note--warn">{t("To'lov hozircha sozlanmagan. Birozdan so'ng urinib ko'ring yoki admin bilan bog'laning.")}</div>
      </main>
    );
  }

  const value = order ? orderAmount : custom ? Number(custom) : amount;
  const valid = order ? true : Number.isInteger(value) && value >= pay.min && value <= pay.max;
  const steps = order ? STEPS.slice(1) : STEPS;
  const stepIndex = order ? step - 1 : step;
  const blocked = pending >= pay.pending_max;
  const amounts = [...new Set([suggested, ...pay.options].filter(Boolean))];

  async function copy(text, label) {
    if (await copyText(text)) {
      haptic('success');
      toast(`${t(label)} — ${t('nusxalandi')} 📋`);
    } else {
      toast(t("Nusxalab bo'lmadi — qo'lda belgilang"), 'error');
    }
  }

  async function onFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const pdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
    try {
      const blob = pdf ? file : await prepareImage(file);
      if (blob.size > 10 * 1048576) throw new Error(t('Fayl {n} MB dan oshmasin.', { n: 10 }));
      setReceipt({ blob, pdf, name: file.name, url: pdf ? null : URL.createObjectURL(blob) });
      haptic('light');
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function send() {
    setSending(true);
    haptic('medium');
    try {
      if (order) {
        // Buyurtma + chek bitta so'rovda. Keyingi holat (tekshiruv → tayyorlanish → tayyor) — buyurtma sahifasida
        const { id } = await apiUpload('/orders/checkout', receipt.blob, { 'X-Order': encodeURIComponent(JSON.stringify(order)) });
        haptic('success');
        replace('progress', { orderId: id, kind: order.kind, payload: order });
        return;
      }
      const { orderId } = await apiUpload('/payments', receipt.blob, { 'X-Amount': String(value) });
      // Bot chekni qabul qilib, adminga yuboradi (odatda 2–5 soniya)
      for (;;) {
        const order = await api(`/orders/${orderId}`);
        if (order.status === 'done') {
          setPaymentId(order.document_id);
          setStatus('pending');
          haptic('success');
          return;
        }
        if (order.status === 'failed') throw new Error(t(order.error || t("Chekni yuborib bo'lmadi.")));
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setSending(false);
    }
  }

  // ===== Yuborildi: holat =====
  if (paymentId) {
    const done = status === 'approved';
    const rejected = status === 'rejected';
    return (
      <main className="page">
        <TopBar title={title} />
        <div className="progress">
          <div className={`result-icon ${rejected ? 'result-icon--fail' : 'result-icon--ok'}`} style={!done && !rejected ? { background: 'var(--grad-purple)' } : undefined}>
            {rejected ? <CloseIcon size={54} /> : done ? <CheckIcon size={58} /> : <span style={{ fontSize: 52 }}>⏳</span>}
          </div>
          <h2>{done ? `${t("Balans to'ldirildi!")} 🎉` : rejected ? t('Chek tasdiqlanmadi') : t('Chek yuborildi!')}</h2>
          <p>{t("To'lov")} #{paymentId} · {money(value)}</p>

          {done && (
            <div className="note note--info" style={{ width: '100%' }}>
              ✅ {t('{sum} hisobingizga tushdi.', { sum: money(value) })} {t('Balans')}: <b>&nbsp;{money(boot.balance)}</b>
            </div>
          )}
          {rejected && (
            <div className="note note--error" style={{ width: '100%' }}>
              {t("Chek noto'g'ri yoki pul kartaga kelib tushmagan bo'lishi mumkin. Tekshirib, qayta yuboring.")}
              {boot.settings.support && ` ${t('Savollar uchun')}: @${boot.settings.support}`}
            </div>
          )}
          {!done && !rejected && (
            <div className="card steps">
              <div className="step step--done"><span className="step__dot"><CheckIcon size={14} /></span>{t('Chek qabul qilindi')}</div>
              <div className="step step--current"><span className="step__dot" />{t('Admin tekshirmoqda')}</div>
              <div className="step"><span className="step__dot" />{t('Balansga tushadi')}</div>
              <p className="card__hint mt-12">
                {t("Odatda 5–30 daqiqa. Ilovani yopsangiz ham bo'ladi — tasdiqlanganda bot xabar beradi, bu sahifa ham o'zi yangilanadi.")}
              </p>
            </div>
          )}

          {rejected ? (
            <button className="btn btn--primary mt-16" onClick={() => { setPaymentId(null); setStatus(null); setReceipt(null); setStep(2); }}>
              {t('Chekni qayta yuborish')}
            </button>
          ) : (
            <button className="btn btn--primary mt-16" onClick={pop}>
              {done ? t('Davom etish') : t('Yopish')}
            </button>
          )}
        </div>
      </main>
    );
  }

  return (
    <main className="page" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar title={title} />

      <div className="stepper" style={{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }}>
        {steps.map((name, i) => (
          <div key={name} className={`stepper__item ${i === stepIndex ? 'stepper__item--active' : ''} ${i < stepIndex ? 'stepper__item--done' : ''}`}>
            <span>{i < stepIndex ? '✓' : i + 1}</span>
            {t(name)}
          </div>
        ))}
      </div>

      {order && (
        <section className="card order-summary">
          <div className="card__label">📦 {t('Buyurtmangiz')}</div>
          <div className="order-summary__title">
            {t(SERVICES[order.kind]?.label ?? '')} · {orderSize(order.kind, order)}
          </div>
          <div className="card__hint">«{order.topic}»</div>
          <div className="summary-row mt-12">{t('Narxi')} <b>{money(price)}</b></div>
          {price - need > 0 && <div className="summary-row">{t('Balansingizdan')} <b>−{money(price - need)}</b></div>}
          <div className="summary-row summary-row--total">{t("To'lanadi")} <b>{money(value)}</b></div>
          {value > need && <p className="card__hint">💡 {t("Eng kam to'lov {min} — ortgan {rest} balansda qoladi.", { min: money(ORDER_PAY_MIN), rest: money(value - need) })}</p>}
        </section>
      )}
      {order && blocked && (
        <div className="note note--warn">⏳ {t('Sizda {n} ta chek tekshiruvda turibdi. Admin tasdiqlashini kuting.', { n: pending })}</div>
      )}

      {/* ===== 1. Summa ===== */}
      {step === 0 && (
        <>
          <section className="card">
            <div className="summary-row" style={{ paddingTop: 0 }}>
              {t('Hozirgi balans')} <b>{money(boot.balance)}</b>
            </div>
            {need > 0 && <div className="note note--warn" style={{ marginTop: 6 }}>⭐ {t('Buyurtma uchun yana {sum} kerak.', { sum: money(need) })}</div>}
          </section>

          <section className="card">
            <div className="card__label">{t("Qancha to'ldirasiz?")}</div>
            <div className="options">
              {amounts.map((n) => (
                <button
                  key={n}
                  className={`option ${!custom && amount === n ? 'option--active' : ''}`}
                  onClick={() => {
                    haptic('select');
                    setCustom('');
                    setAmount(n);
                  }}
                >
                  <b>{money(n)}</b>
                  <span>{n === suggested ? `⭐ ${t('Buyurtma uchun')}` : n >= 50000 ? t("Ko'p buyurtma uchun") : t("Tez to'ldirish")}</span>
                </button>
              ))}
            </div>
            <label className="field-label" htmlFor="custom-amount">{t("Yoki o'zingiz yozing")}</label>
            <div className="amount-input">
              <input
                id="custom-amount"
                className="field"
                inputMode="numeric"
                placeholder={t('Masalan: 15 000')}
                value={custom ? groupDigits(custom) : ''}
                onChange={(e) => setCustom(e.target.value.replace(/\D/g, '').slice(0, 9))}
              />
              <span>{t("so'm")}</span>
            </div>
            <p className={`card__hint mt-12 ${custom && !valid ? 'text-danger' : ''}`}>
              {t('{min} dan {max} gacha', { min: money(pay.min), max: money(pay.max) })}
            </p>
          </section>

          {blocked && (
            <div className="note note--warn">
              ⏳ {t("Sizda {n} ta chek tekshiruvda turibdi. Admin tasdiqlashini kuting — keyin yana to'ldira olasiz.", { n: pending })}
            </div>
          )}
          <button className="link-btn mt-16" style={{ width: '100%', justifyContent: 'center' }} onClick={() => topupViaBot(need)}>
            {t("Yoki bot chatida to'lash")} →
          </button>

          <div className="bottom-bar">
            <button className="btn btn--primary" disabled={!valid || blocked} onClick={() => { haptic('light'); setStep(1); }}>
              {valid ? `${money(value)} — ${t('davom etish')}` : t('Summani tanlang')}
            </button>
          </div>
        </>
      )}

      {/* ===== 2. Karta va yo'riqnoma ===== */}
      {step === 1 && (
        <>
          <section className="pay-amount">
            <span>{t("O'tkaziladigan summa")}</span>
            <b>{money(value)}</b>
            <button className="chip chip--pill" onClick={() => copy(String(value), 'Summa')}>📋 {t('Nusxalash')}</button>
          </section>

          {pay.cards.map((card) => (
            <section key={card.number} className="bank-card">
              <div className="bank-card__top">
                <span className="bank-card__chip" />
                <span className="bank-card__brand">{/^9860/.test(card.number.replace(/\s/g, '')) ? 'HUMO' : /^8600|^5614/.test(card.number.replace(/\s/g, '')) ? 'UZCARD' : 'KARTA'}</span>
              </div>
              <div className="bank-card__number">{card.number}</div>
              <div className="bank-card__bottom">
                <span>{card.holder || t('Karta egasi')}</span>
                <button className="bank-card__copy" onClick={() => copy(card.number.replace(/\s/g, ''), 'Karta raqami')}>
                  📋 {t('Nusxalash')}
                </button>
              </div>
            </section>
          ))}

          <section className="card">
            <div className="card__label">{t("Qanday to'lash kerak?")}</div>
            <ol className="howto">
              <li>{t('Click, Payme, Uzum yoki bank ilovangizni oching')}</li>
              <li>{t("Yuqoridagi kartaga aynan {sum} o'tkazing", { sum: money(value) })}</li>
              <li>{t("To'lov chekini skrinshot qiling (yoki PDF saqlang)")}</li>
              <li>{t("«To'ladim» ni bosib, chekni yuklang")}</li>
              {order && <li>{t('Admin tasdiqlagach, buyurtmangiz avtomatik tayyorlanadi')} ✨</li>}
            </ol>
          </section>

          {!order && (
            <button className="link-btn mt-16" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setStep(0)}>
              ← {t("Summani o'zgartirish")}
            </button>
          )}
          <div className="bottom-bar">
            <button className="btn btn--primary" disabled={order && blocked} onClick={() => { haptic('light'); setStep(2); }}>
              ✅ {t("To'ladim — chekni yuklash")}
            </button>
          </div>
        </>
      )}

      {/* ===== 3. Chek ===== */}
      {step === 2 && (
        <>
          <input ref={fileInput} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
          <section className="card">
            <div className="card__label">{t("To'lov cheki")}</div>
            {receipt ? (
              <div className="receipt">
                {receipt.pdf ? (
                  <div className="receipt__pdf">📄 {receipt.name}</div>
                ) : (
                  <img className="receipt__image" src={receipt.url} alt={t('Chek')} />
                )}
                <button className="btn btn--soft btn--sm" onClick={() => fileInput.current.click()}>
                  {t('Boshqasini tanlash')}
                </button>
              </div>
            ) : (
              <button className="upload-box pressable" onClick={() => fileInput.current.click()}>
                <span className="upload-box__icon">📸</span>
                <b>{t('Chekni yuklang')}</b>
                <small>{t('Skrinshot yoki PDF · 10 MB gacha')}</small>
              </button>
            )}
            <p className="card__hint mt-12">{t("Chekda summa, sana va qabul qiluvchi karta ko'rinib tursin — tekshiruv tezroq bo'ladi.")}</p>
          </section>

          <section className="card">
            <div className="summary-row">{t('Summa')} <b>{money(value)}</b></div>
            <div className="summary-row">
              {t('Karta')} <b>•••• {lastDigits(pay.cards[0].number)}</b>
            </div>
          </section>

          <button className="link-btn mt-16" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setStep(1)}>
            ← {t("Karta raqamini ko'rish")}
          </button>
          <div className="bottom-bar">
            <button className="btn btn--primary" disabled={!receipt || sending || (order && blocked)} onClick={send}>
              {sending ? t('Yuborilmoqda…') : order ? t('Chekni yuborish va buyurtma berish') : t('Chekni yuborish')}
            </button>
          </div>
        </>
      )}
    </main>
  );
}
