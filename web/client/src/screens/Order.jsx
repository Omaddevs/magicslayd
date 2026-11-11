import { useEffect, useMemo, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { TileArt } from '../components/Art.jsx';
import Flag from '../components/Flag.jsx';
import { ChevronRight, IdCardIcon, SparkIcon } from '../components/Icons.jsx';
import SlidePreview from '../components/SlidePreview.jsx';
import { TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { money, splitEmoji } from '../lib/format.js';
import { SERVICES } from '../lib/services.js';
import { getLang, t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';

const TOPIC_MIN = 3;
const TOPIC_MAX = 200;
const AUTHOR_MAX = 70;
const TOPIC_EXAMPLES = {
  pres: "Masalan: Sun'iy intellektning ta'limdagi o'rni",
  referat: "Masalan: O'zbekistonda raqamli iqtisodiyotning rivojlanishi",
  mustaqil: 'Masalan: Ekologik muammolar va ularning yechimlari',
  kurs: 'Masalan: Kichik biznesda marketing strategiyalari',
};
const FORMATS = {
  pptx: { label: 'PowerPoint', hint: 'Tahrirlash mumkin' },
  docx: { label: 'Word', hint: 'Tahrirlash mumkin' },
  pdf: { label: 'PDF', hint: 'Har joyda bir xil' },
};

/** Dizayn tanlash.
 *  - Shablonlar sahifasidan kelinsa (fromTemplate): faqat tanlangan shablon, «O'zgartirish» — shablonlarga qaytadi.
 *  - To'g'ridan-to'g'ri kelinsa: joriy dizayn, «Boshqa dizayn» — soha bo'yicha filtrli ixcham tanlov. */
function DesignPicker({ settings, themeKeys, theme, setTheme, fromTemplate, onChangeTemplate }) {
  const current = settings.themes[theme] ?? settings.themes[themeKeys[0]];
  const categories = settings.theme_categories ?? [];
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState(current?.category ?? categories[0]?.key);
  const counts = useMemo(() => {
    const out = {};
    for (const key of themeKeys) out[settings.themes[key].category] = (out[settings.themes[key].category] ?? 0) + 1;
    return out;
  }, [settings.themes, themeKeys]);
  const visible = themeKeys.filter((key) => !categories.length || settings.themes[key].category === category
    || (!counts[category] && key === theme));

  return (
    <section className="card design-pick">
      <div className="card__label">{t('Dizayn')}</div>
      <div className="design-pick__current">
        <div className="design-pick__preview"><SlidePreview theme={current} /></div>
        <div className="design-pick__info">
          <b>{t(current.name)}</b>
          {current.about && <span>{t(current.about)}</span>}
          {fromTemplate ? (
            <button className="btn btn--soft btn--sm" onClick={() => { haptic('light'); onChangeTemplate(); }}>
              {t("O'zgartirish")}
            </button>
          ) : (
            <button className="btn btn--soft btn--sm" onClick={() => { haptic('light'); setOpen((v) => !v); }} aria-expanded={open}>
              {open ? t('Yopish') : t('Boshqa dizayn')}
            </button>
          )}
        </div>
      </div>

      {!fromTemplate && open && (
        <>
          {categories.length > 0 && (
            <div className="chips chips--scroll design-pick__cats" role="tablist">
              {categories.filter((c) => counts[c.key]).map((c) => (
                <button key={c.key} role="tab" aria-selected={category === c.key}
                  className={`chip chip--pill ${category === c.key ? 'chip--active' : ''}`}
                  onClick={() => { haptic('select'); setCategory(c.key); }}>
                  {c.emoji} {t(c.short || c.name)} <span className="design-pick__n">{counts[c.key]}</span>
                </button>
              ))}
            </div>
          )}
          <div className="themes">
            {visible.map((key) => (
              <button
                key={key}
                className={`theme ${theme === key ? 'theme--active' : ''}`}
                onClick={() => { haptic('select'); setTheme(key); setOpen(false); }}
              >
                <SlidePreview theme={settings.themes[key]} />
                <span className="theme__name">{t(settings.themes[key].name)}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export default function Order({ kind, theme: presetTheme, initial = {} }) {
  const { boot, push, pop, replace, toast, topup, refreshBalance } = useApp();
  const { settings, balance } = boot;
  const isAdmin = Boolean(boot.freeOrders); // admin «🎁 bepul buyurtma» huquqi bilan
  const service = SERVICES[kind];
  const isPres = kind === 'pres';
  const slideCfg = settings.slides;
  const themeKeys = Object.keys(settings.themes);

  const [topic, setTopic] = useState(initial.topic ?? '');
  const [plans, setPlans] = useState(initial.plans ?? 4);
  const [slides, setSlides] = useState(initial.slides ?? 15);
  const [customSlides, setCustomSlides] = useState('');
  const [pages, setPages] = useState(initial.pages ?? settings.pages[kind]?.[1] ?? settings.pages[kind]?.[0]);
  // Betlar sonini o'zi yozishi mumkin — oraliq bot bilan bir xil (config.PAGE_RANGE)
  const [pageMin, pageMax] = settings.page_range?.[kind] ?? [settings.pages[kind]?.[0], settings.pages[kind]?.at(-1)];
  const [customPages, setCustomPages] = useState(
    initial.pages && !settings.pages[kind]?.includes(initial.pages) ? String(initial.pages) : '',
  );
  const customPagesBad = customPages !== '' && (Number(customPages) < pageMin || Number(customPages) > pageMax);
  // Hujjat tili — standart bo'yicha ilova tili (bot qo'llasa)
  const [lang, setLang] = useState(initial.lang ?? (settings.languages[getLang()] ? getLang() : 'uz'));
  const [theme, setTheme] = useState(initial.theme ?? presetTheme ?? themeKeys[0]);
  const [author, setAuthor] = useState(initial.author ?? boot.user.fullName ?? '');
  const [fmt, setFmt] = useState(initial.fmt ?? (isPres ? 'pptx' : 'docx'));
  const [title, setTitle] = useState(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    refreshBalance().catch(() => {});
    if (!isPres) api('/title').then((data) => setTitle(data.title)).catch(() => setTitle({}));
  }, [isPres, refreshBalance]);

  // Reja ko'paysa, slaydlar soni «reja + 4» dan kam qolmasin (bot qoidasi)
  const minSlides = plans + slideCfg.fixed;
  const slideOptions = slideCfg.options.filter((n) => n >= minSlides);
  // Hamma variant ko'rinadi (5, 8 ham): kichigi tanlansa — reja soni o'zi kamayadi
  const allSlideOptions = slideCfg.options.filter((n) => n >= slideCfg.plan_min + slideCfg.fixed);

  function chooseSlides(n) {
    haptic('select');
    if (n < minSlides) {
      const fitted = n - slideCfg.fixed;
      setPlans(fitted);
      toast(t('{n} slayd uchun reja soni {m} taga tushirildi', { n, m: fitted }));
    }
    setSlides(n);
  }
  useEffect(() => {
    if (isPres && slides < minSlides) setSlides(slideOptions[0]);
  }, [isPres, minSlides, slides, slideOptions]);

  // To'liq narx (sahifa/slayd soniga qarab) — admin uchun ham ko'rinadi, lekin to'lanmaydi
  const fullPrice = isPres ? slides * slideCfg.price : pages * settings.page_price[kind];
  const price = isAdmin ? 0 : fullPrice;

  const cleanTopic = topic.trim().replace(/\s+/g, ' ');
  const topicOk = cleanTopic.length >= TOPIC_MIN && cleanTopic.length <= TOPIC_MAX;
  const enough = balance >= price;
  const titleFilled = title ? Object.keys(title).length : 0;

  const payload = isPres
    ? { kind, topic: cleanTopic, plans, slides, lang, theme, author, fmt }
    : { kind, topic: cleanTopic, pages, lang, fmt };

  async function submit() {
    if (!isPres && customPagesBad) {
      toast(t('{min} dan {max} gacha son kiriting.', { min: pageMin, max: pageMax }), 'error');
      return;
    }
    if (!topicOk) {
      toast(t("Mavzu {min}–{max} belgi oralig'ida bo'lsin", { min: TOPIC_MIN, max: TOPIC_MAX }), 'error');
      return;
    }
    if (!enough) {
      // Shu buyurtma uchun to'lov: karta → chek → admin tasdiqlaydi → buyurtma o'zi tayyorlanadi
      haptic('medium');
      push('topup', { need: price - balance, order: payload, price });
      return;
    }
    setSending(true);
    haptic('medium');
    try {
      const { id } = await api('/orders', { method: 'POST', body: payload });
      replace('progress', { orderId: id, kind, payload });
    } catch (error) {
      if (error.status === 409 && error.data.orderId) {
        toast(error.message);
        replace('progress', { orderId: error.data.orderId, kind });
      } else {
        toast(error.message, 'error');
        if (error.status === 402) refreshBalance().catch(() => {});
      }
    } finally {
      setSending(false);
    }
  }

  const unitPrice = isPres ? slideCfg.price : settings.page_price[kind];

  return (
    <main className="page" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar title={t(service.title)} />

      <div className={`order-hero tile--${service.color}`}>
        <TileArt kind={kind} className="order-hero__art" />
        <div>
          <b>{t('{title} yaratish', { title: t(service.title) })}</b>
          <span>{t(service.about)}</span>
        </div>
      </div>

      {/* Mavzu */}
      <section className="card">
        <div className="card__label">{t('Mavzu')}</div>
        <textarea
          className="field"
          rows={3}
          maxLength={TOPIC_MAX}
          placeholder={t(TOPIC_EXAMPLES[kind])}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />
        <div className="counter">
          {cleanTopic.length}/{TOPIC_MAX}
        </div>
      </section>

      {isPres ? (
        <>
          <section className="card">
            <div className="card__label">
              {t('Rejalar soni')} <span className="card__hint">{t('{n} ta', { n: plans })}</span>
            </div>
            <div className="chips">
              {Array.from({ length: slideCfg.plan_max - slideCfg.plan_min + 1 }, (_, i) => slideCfg.plan_min + i).map((n) => (
                <button
                  key={n}
                  className={`chip ${plans === n ? 'chip--active' : ''}`}
                  onClick={() => {
                    haptic('select');
                    setPlans(n);
                  }}
                >
                  {n}
                </button>
              ))}
            </div>
          </section>

          <section className="card">
            <div className="card__label">
              {t('Slaydlar soni')} <span className="card__hint">{t('har biri {price}', { price: money(unitPrice) })}</span>
            </div>
            <div className="options">
              {allSlideOptions.map((n) => (
                <button
                  key={n}
                  className={`option ${slides === n ? 'option--active' : ''}`}
                  onClick={() => {
                    setCustomSlides('');
                    chooseSlides(n);
                  }}
                >
                  <b>{n} {t('slayd')}</b>
                  <span>{isAdmin ? <><s className="price-old">{money(n * unitPrice)}</s> {t('bepul')}</> : money(n * unitPrice)}</span>
                </button>
              ))}
            </div>
            <label className="editor-field">
              <span className="field-label">
                {t("Yoki o'zingiz kiriting ({min}–{max} slayd)", { min: allSlideOptions[0], max: slideCfg.options.at(-1) })}
              </span>
              <input
                className="field"
                inputMode="numeric"
                maxLength={2}
                placeholder={t('Masalan: 75')}
                value={customSlides}
                onChange={(e) => {
                  const value = e.target.value.replace(/\D/g, '');
                  setCustomSlides(value);
                  const n = Number(value);
                  if (n >= allSlideOptions[0] && n <= slideCfg.options.at(-1)) chooseSlides(n);
                }}
              />
            </label>
            {customSlides && (Number(customSlides) < allSlideOptions[0] || Number(customSlides) > slideCfg.options.at(-1)) && (
              <p className="note note--warn">
                {t('{min} dan {max} gacha son kiriting.', { min: allSlideOptions[0], max: slideCfg.options.at(-1) })}
              </p>
            )}
            <p className="card__hint mt-12">
              {t("Tuzilma: muqova, mundarija, reja, har bir rejaga kamida 1 ta slayd va xulosa — shuning uchun slaydlar kamida «reja + {n}» ta. Kichik variant tanlansa, reja soni o'zi moslashadi.", { n: slideCfg.fixed })}
            </p>
          </section>
        </>
      ) : (
        <section className="card">
          <div className="card__label">
            {t('Hajmi')} <span className="card__hint">{t('har bir bet {price}', { price: money(unitPrice) })}</span>
          </div>
          <div className="options">
            {settings.pages[kind].map((n) => (
              <button
                key={n}
                className={`option ${pages === n && !customPages ? 'option--active' : ''}`}
                onClick={() => {
                  haptic('select');
                  setCustomPages('');
                  setPages(n);
                }}
              >
                <b>{n} {t('bet')}</b>
                <span>{isAdmin ? <><s className="price-old">{money(n * unitPrice)}</s> {t('bepul')}</> : money(n * unitPrice)}</span>
              </button>
            ))}
          </div>
          <label className="editor-field">
            <span className="field-label">
              {t("Yoki o'zingiz kiriting ({min}–{max} bet)", { min: pageMin, max: pageMax })}
            </span>
            <input
              className="field"
              inputMode="numeric"
              maxLength={3}
              placeholder={t('Masalan: {n}', { n: Math.round((pageMin + pageMax) / 2) })}
              value={customPages}
              onChange={(e) => {
                const value = e.target.value.replace(/\D/g, '');
                setCustomPages(value);
                const n = Number(value);
                if (n >= pageMin && n <= pageMax) {
                  haptic('select');
                  setPages(n);
                }
              }}
            />
          </label>
          {customPagesBad && (
            <p className="note note--warn">{t('{min} dan {max} gacha son kiriting.', { min: pageMin, max: pageMax })}</p>
          )}
        </section>
      )}

      {/* Til */}
      <section className="card">
        <div className="card__label">{t('Hujjat tili')}</div>
        <div className="segment">
          {Object.entries(settings.languages).map(([key, label]) => {
            const [, name] = splitEmoji(label);
            return (
              <button
                key={key}
                className={lang === key ? 'segment--active' : ''}
                onClick={() => {
                  haptic('select');
                  setLang(key);
                }}
              >
                <Flag lang={key} /> {name}
              </button>
            );
          })}
        </div>
      </section>

      {isPres && (
        <>
          <DesignPicker
            settings={settings} themeKeys={themeKeys} theme={theme} setTheme={setTheme}
            fromTemplate={Boolean(presetTheme)} onChangeTemplate={pop}
          />

          <section className="card">
            <div className="card__label">
              {t('Muallif')} <span className="card__hint">{t('ixtiyoriy')}</span>
            </div>
            <input
              className="field"
              maxLength={AUTHOR_MAX}
              placeholder={t("Masalan: Aliyev Vali, 10-«A» sinf o'quvchisi")}
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
            />
          </section>
        </>
      )}

      {settings.pdf && (
        <section className="card">
          <div className="card__label">{t('Format')}</div>
          <div className="options">
            {[isPres ? 'pptx' : 'docx', 'pdf'].map((key) => (
              <button
                key={key}
                className={`option ${fmt === key ? 'option--active' : ''}`}
                onClick={() => {
                  haptic('select');
                  setFmt(key);
                }}
              >
                <b>{FORMATS[key].label}</b>
                <span>{t(FORMATS[key].hint)}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {!isPres && title !== null && (
        <button className="card menu__item pressable" style={{ marginTop: 12 }} onClick={() => push('title')}>
          <div className="menu__icon" style={{ background: 'var(--grad-blue)' }}>
            <IdCardIcon size={20} />
          </div>
          <span>
            {t("Titul ma'lumotlari")}
            <br />
            <small>{titleFilled ? t("{n} ta maydon to'ldirilgan", { n: titleFilled }) : t("To'ldirilmagan — muqovada faqat mavzu bo'ladi")}</small>
          </span>
          <ChevronRight size={20} />
        </button>
      )}

      {/* Hisob-kitob */}
      <section className="card">
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
