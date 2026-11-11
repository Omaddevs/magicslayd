import { useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { TileArt } from '../components/Art.jsx';
import Flag from '../components/Flag.jsx';
import { SparkIcon } from '../components/Icons.jsx';
import { TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { ARTICLE_TYPES, SIZE_NAMES, STYLE_NAMES, TYPE_BY_KEY, articlePrice, targetWords } from '../lib/article.js';
import { money, splitEmoji } from '../lib/format.js';
import { getLang, t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';

const TOPIC_MIN = 3;
const TOPIC_MAX = 200;
const PURPOSE_MAX = 200;
const NOTES_MAX = 600;
const AUTHOR_MAX = 200;
const WITH_AUTHOR = ['scientific', 'review'];
const WITH_SOURCES = ['scientific', 'review', 'analytical'];
const TOPIC_EXAMPLES = {
  general: "Masalan: Kitob o'qishning inson hayotidagi ahamiyati",
  scientific: "Masalan: Sun'iy intellektning tibbiy diagnostikadagi samaradorligi",
  analytical: "Masalan: Yoshlar ishsizligining sabablari va yechimlari",
  journalistic: "Masalan: Shahrimizdagi ekologik muammolar — kim javobgar?",
  review: "Masalan: Masofaviy ta'lim samaradorligi bo'yicha tadqiqotlar sharhi",
};

/** Maqola buyurtmasi: tur → mavzu → til → hajm → qo'shimcha talablar → yaratish. */
export default function ArticleOrder({ initial = {} }) {
  const { boot, push, replace, toast, topup, refreshBalance } = useApp();
  const { settings, balance } = boot;
  const isAdmin = Boolean(boot.freeOrders); // admin «🎁 bepul buyurtma» huquqi bilan
  const cfg = settings.article;

  const [type, setType] = useState(initial.type ?? null);
  const [topic, setTopic] = useState(initial.topic ?? '');
  const [lang, setLang] = useState(initial.lang ?? (settings.languages[getLang()] ? getLang() : 'uz'));
  const initialSize = Object.entries(cfg.sizes).find(([, range]) => targetWords(range) === initial.words)?.[0];
  const [size, setSize] = useState(initial.words ? initialSize ?? 'custom' : 'medium');
  const [customWords, setCustomWords] = useState(initial.words && !initialSize ? String(initial.words) : '');
  const [style, setStyle] = useState(initial.style ?? 'auto');
  const [purpose, setPurpose] = useState(initial.purpose ?? '');
  const [notes, setNotes] = useState(initial.notes ?? '');
  const [author, setAuthor] = useState(initial.author ?? boot.user.fullName ?? '');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    refreshBalance().catch(() => {});
  }, [refreshBalance]);

  const custom = Number(customWords);
  const customOk = custom >= cfg.words_min && custom <= cfg.words_max;
  const words = size === 'custom' ? (customOk ? custom : null) : targetWords(cfg.sizes[size]);
  const fullPrice = words ? articlePrice(words, cfg) : 0;
  const price = isAdmin ? 0 : fullPrice;
  const enough = balance >= price;

  const cleanTopic = topic.trim().replace(/\s+/g, ' ');
  const topicOk = cleanTopic.length >= TOPIC_MIN && cleanTopic.length <= TOPIC_MAX;

  const payload = {
    kind: 'maqola', type, topic: cleanTopic, lang, words, style,
    purpose: purpose.trim(), notes: notes.trim(), author: WITH_AUTHOR.includes(type) ? author.trim() : '', ui: getLang(),
  };

  const priceText = (n) => (isAdmin
    ? <><s className="price-old">{money(articlePrice(n, cfg))}</s> {t('bepul')}</>
    : money(articlePrice(n, cfg)));

  async function submit() {
    if (!type) {
      toast(t('Maqola turini tanlang.'), 'error');
      return;
    }
    if (!topicOk) {
      toast(t("Mavzu {min}–{max} belgi oralig'ida bo'lsin", { min: TOPIC_MIN, max: TOPIC_MAX }), 'error');
      return;
    }
    if (!words) {
      toast(t('{min} dan {max} gacha son kiriting.', { min: cfg.words_min, max: cfg.words_max }), 'error');
      return;
    }
    if (!enough) {
      haptic('medium');
      push('topup', { need: price - balance, order: payload, price });
      return;
    }
    setSending(true);
    haptic('medium');
    try {
      const { id } = await api('/orders', { method: 'POST', body: payload });
      replace('progress', { orderId: id, kind: 'maqola', payload });
    } catch (error) {
      if (error.status === 409 && error.data.orderId) {
        toast(error.message);
        replace('progress', { orderId: error.data.orderId, kind: 'maqola' });
      } else {
        toast(error.message, 'error');
        if (error.status === 402) refreshBalance().catch(() => {});
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="page" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar title={t('Maqola')} />

      <div className="order-hero tile--green">
        <TileArt kind="maqola" className="order-hero__art" />
        <div>
          <b>{t('{title} yaratish', { title: t('Maqola') })}</b>
          <span>{t("Mavzu bo'yicha tayyor maqola — keyin ilovada bemalol tahrirlab, Word yoki PDF qilib olasiz")}</span>
        </div>
      </div>

      {/* 1. Turi */}
      <section className="card">
        <div className="card__label">{t('Maqola turi')}</div>
        <div className="art-types">
          {ARTICLE_TYPES.map((item) => (
            <button
              key={item.key}
              className={`art-type pressable ${type === item.key ? 'art-type--active' : ''}`}
              onClick={() => { haptic('select'); setType(item.key); }}
              aria-pressed={type === item.key}
            >
              <span className="art-type__icon" aria-hidden="true">{item.icon}</span>
              <span className="art-type__text">
                <b>{t(item.title)}</b>
                <span>{t(item.about)}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* 2. Mavzu */}
      <section className="card">
        <div className="card__label">{t('Mavzu')}</div>
        <textarea
          className="field"
          rows={3}
          maxLength={TOPIC_MAX}
          placeholder={t(TOPIC_EXAMPLES[type ?? 'general'])}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <div className="counter">{cleanTopic.length}/{TOPIC_MAX}</div>
      </section>

      {/* 3. Til */}
      <section className="card">
        <div className="card__label">{t('Maqola tili')}</div>
        <div className="segment">
          {Object.entries(settings.languages).map(([key, label]) => {
            const [, name] = splitEmoji(label);
            return (
              <button key={key} className={lang === key ? 'segment--active' : ''} onClick={() => { haptic('select'); setLang(key); }}>
                <Flag lang={key} /> {name}
              </button>
            );
          })}
        </div>
      </section>

      {/* 4. Hajmi */}
      <section className="card">
        <div className="card__label">
          {t('Hajmi')} <span className="card__hint">{t("har 100 so'z {price}", { price: money(cfg.price_per_100) })}</span>
        </div>
        <div className="options options--col">
          {Object.entries(cfg.sizes).map(([key, range]) => (
            <button
              key={key}
              className={`option option--row ${size === key ? 'option--active' : ''}`}
              onClick={() => { haptic('select'); setSize(key); }}
            >
              <b>{t(SIZE_NAMES[key])} <small>· {range[0]}–{range[1]} {t("so'z")}</small></b>
              <span>{priceText(targetWords(range))}</span>
            </button>
          ))}
          <button
            className={`option option--row ${size === 'custom' ? 'option--active' : ''}`}
            onClick={() => { haptic('select'); setSize('custom'); }}
          >
            <b>{t("O'zim kiritaman")}</b>
            <span>{size === 'custom' && customOk ? priceText(custom) : `${cfg.words_min}–${cfg.words_max}`}</span>
          </button>
        </div>
        {size === 'custom' && (
          <label className="editor-field">
            <span className="field-label">{t("So'zlar soni ({min}–{max})", { min: cfg.words_min, max: cfg.words_max })}</span>
            <input
              className="field"
              inputMode="numeric"
              maxLength={4}
              placeholder={t('Masalan: 1800')}
              value={customWords}
              autoFocus
              onChange={(e) => setCustomWords(e.target.value.replace(/\D/g, ''))}
            />
          </label>
        )}
        {size === 'custom' && customWords && !customOk && (
          <p className="note note--warn">{t('{min} dan {max} gacha son kiriting.', { min: cfg.words_min, max: cfg.words_max })}</p>
        )}
      </section>

      {/* 5. Qo'shimcha talablar */}
      <section className="card">
        <div className="card__label">
          {t("Qo'shimcha talablar")} <span className="card__hint">{t('ixtiyoriy')}</span>
        </div>
        <span className="field-label">{t('Uslub')}</span>
        <div className="chips">
          {Object.entries(STYLE_NAMES).map(([key, name]) => (
            <button key={key} className={`chip ${style === key ? 'chip--active' : ''}`} onClick={() => { haptic('select'); setStyle(key); }}>
              {t(name)}
            </button>
          ))}
        </div>
        <label className="editor-field">
          <span className="field-label">{t('Maqsad')}</span>
          <input
            className="field"
            maxLength={PURPOSE_MAX}
            placeholder={t('Masalan: jurnalga topshirish, konferensiya, blog')}
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
        </label>
        <label className="editor-field">
          <span className="field-label">{t('Izoh va talablar')}</span>
          <textarea
            className="field"
            rows={3}
            maxLength={NOTES_MAX}
            placeholder={t("Masalan: O'zbekiston misolida yozing, jadval qo'shing")}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        {WITH_AUTHOR.includes(type) && (
          <label className="editor-field">
            <span className="field-label">{t('Muallif')}</span>
            <input
              className="field"
              maxLength={AUTHOR_MAX}
              placeholder={t('Masalan: Aliyev Vali, TDIU magistranti')}
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </label>
        )}
        {WITH_SOURCES.includes(type) && (
          <p className="note note--info mt-12">
            🔎 {t("Manbalar faqat haqiqiy ilmiy bazalardan (OpenAlex, Crossref) olinadi. Topilmasa — buni ochiq aytamiz, soxta manba yoki statistika qo'shilmaydi.")}
          </p>
        )}
      </section>

      {/* Hisob-kitob */}
      <section className="card">
        {type && (
          <div className="summary-row">
            {t('Turi')} <b>{TYPE_BY_KEY[type].icon} {t(TYPE_BY_KEY[type].title)}</b>
          </div>
        )}
        {words && (
          <div className="summary-row">
            {t('Hajmi')} <b>~{words} {t("so'z")}</b>
          </div>
        )}
        <div className="summary-row">
          {t('Narxi')} <b>{isAdmin ? <><s className="price-old">{money(fullPrice)}</s> {t('bepul')}</> : money(price)}</b>
        </div>
        {isAdmin && <div className="note note--info">🛠 {t("Siz admin hisobidasiz — o'zingizning buyurtmalaringiz bepul. Oddiy foydalanuvchilar ko'rsatilgan narxni to'laydi.")}</div>}
        <div className="summary-row">
          {t('Balansingiz')} <b>{money(balance)}</b>
        </div>
        {!enough && (
          <>
            <div className="summary-row summary-row--total">
              {t("To'lanadi")} <b>{money(price - balance)}</b>
            </div>
            <div className="note note--info">
              💳 {t("«To'lash va olish» ni bosing: summani kartaga o'tkazasiz va chekni yuklaysiz. Admin tasdiqlagach, buyurtmangiz avtomatik tayyorlanadi — shu yerda ham, Telegram chatda ham olasiz.")}
            </div>
            <button className="link-btn mt-12" style={{ width: '100%', justifyContent: 'center' }} onClick={() => topup(price - balance)}>
              {t("Yoki avval faqat hisobni to'ldirish")} →
            </button>
          </>
        )}
        {enough && (
          <div className="note note--info">
            💡 {t("Pul faqat fayl tayyor bo'lganda yechiladi. Xato bo'lsa — avtomatik qaytariladi. Tayyor fayl Telegram chatga keladi.")}
          </div>
        )}
      </section>

      <div className="bottom-bar">
        <button className="btn btn--primary" onClick={submit} disabled={sending}>
          {enough ? <SparkIcon size={20} /> : <span aria-hidden="true">💳</span>}
          {sending ? t('Yuborilmoqda...') : enough ? `${t('Yaratish')}${price ? ` — ${money(price)}` : ''}` : `${t("To'lash va olish")} — ${money(price - balance)}`}
        </button>
      </div>
    </main>
  );
}
