import { useEffect, useMemo, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { CategoryBadge } from '../components/CategoryIcons.jsx';
import FileItem from '../components/FileItem.jsx';
import { ChevronRight, CloseIcon, FilterIcon, SearchIcon } from '../components/Icons.jsx';
import ImportCard from '../components/ImportCard.jsx';
import SlidePreview from '../components/SlidePreview.jsx';
import { DOC_TYPES, RecommendedCarousel, buildRecommended, useFavorites } from '../components/TemplateShowcase.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';

const ALL = 'all';
const FALLBACK = 'umumiy';
const ROW = 4; // yig'ilgan holatda bitta qator kvadrat
// Tur bo'yicha filtr (qidiruv tagidagi tugmalar). Referat / kurs / mustaqil — tayyor namunalar va AI bilan yaratish
const TYPES = [
  ['all', 'Barchasi'],
  ['pres', 'Presentatsiya'],
  ['referat', 'Referat'],
  ['kurs', 'Kurs ishi'],
  ['mustaqil', 'Mustaqil ish'],
];

/** Referat / kurs ishi / mustaqil ish: AI bilan yaratish kartasi va admin qo'shgan tayyor namunalar. */
function DocTypeView({ kind, query }) {
  const { push } = useApp();
  const [items, setItems] = useState(null);
  const meta = DOC_TYPES[kind];

  useEffect(() => {
    setItems(null);
    api(`/materials?kind=${kind}&limit=50`)
      .then((data) => setItems(data.materials))
      .catch(() => setItems([]));
  }, [kind]);

  const words = normalize(query).split(' ').filter(Boolean);
  const shown = (items || []).filter((m) => words.every((w) => normalize(m.title).includes(w)));

  return (
    <>
      <button className={`doc-hero rec__card--${meta.color} pressable`} onClick={() => { haptic('light'); push('order', { kind }); }}>
        <span className="doc-hero__text">
          <b>{t('{title}ni AI bilan yaratish', { title: t(meta.title) })}</b>
          <span>{t('Mavzuni yozing — tayyor DOCX fayl Telegram chatga keladi')}</span>
          <span className="doc-hero__cta">{t('Boshlash')} <ChevronRight size={16} /></span>
        </span>
        <span className="doc-hero__art"><meta.Art /></span>
      </button>
      <div className="section-head">
        <h2>{t('Tayyor namunalar')}</h2>
        {items?.length > 0 && <span className="badge">{items.length}</span>}
      </div>
      {items === null ? (
        <Skeleton height={76} count={3} />
      ) : shown.length ? (
        <div className="list">
          {shown.map((item) => <FileItem key={item.id} item={item} />)}
        </div>
      ) : (
        <Empty
          icon={<SearchIcon size={30} />}
          title={words.length ? t('Hech narsa topilmadi') : t("Hozircha namunalar yo'q")}
          text={words.length ? t("Boshqa so'z bilan qidirib ko'ring.") : t('Tez orada shu yerda {title} namunalari chiqadi. Hozir AI bilan yarating.', { title: t(meta.title).toLowerCase() })}
        />
      )}
    </>
  );
}

/** Qidiruv uchun matnni bir xil ko'rinishga keltiradi: kichik harf, apostrof turlari va emojisiz. */
const normalize = (text) =>
  String(text || '')
    .toLowerCase()
    .replace(/[ʻʼ‘’`']/g, '')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();

/** Bitta shablon kartochkasi: o'z maketi borlari katta, oddiy rangli dizaynlar ikki ustunli to'rda. */
function ThemeCards({ items, onPick }) {
  const styled = items.filter((item) => item.theme.style);
  const classic = items.filter((item) => !item.theme.style);
  return (
    <>
      {styled.length > 0 && (
        <div className="templates">
          {styled.map(({ key, theme }) => (
            <button key={key} className="template-card pressable" onClick={() => onPick(key)}>
              <SlidePreview theme={theme} />
              <span className="template-card__body">
                <span className="template-card__name">{t(theme.name)}</span>
                {theme.about && <span className="template-card__about">{t(theme.about)}</span>}
                <span className="template-card__tag">{theme.image_style ? `🪄 ${t('AI rasmlar')}` : `📷 ${t('Haqiqiy fotolar')}`}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      {classic.length > 0 && (
        <div className="themes">
          {classic.map(({ key, theme }) => (
            <button
              key={key}
              className="theme pressable"
              style={{ background: 'var(--surface)', boxShadow: 'var(--shadow-soft)' }}
              onClick={() => onPick(key)}
            >
              <SlidePreview theme={theme} />
              <span className="theme__name">{t(theme.name)}</span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/** Shablonlar: qidiruv + filtr, kvadrat kategoriyalar, tanlangan soha shablonlari.
 *  Sohalar va shablonlar bot tomonida (presentation/themes.py) — yangi shablon o'z sohasiga avtomatik tushadi. */
export default function Templates({ asTab }) {
  const { boot, push } = useApp();
  const [files, setFiles] = useState([]);
  const [type, setType] = useState('all'); // all | pres | referat | kurs | mustaqil | fav
  const [fav, toggleFav] = useFavorites();
  const [category, setCategory] = useState(ALL);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(false); // «Barchasi» — hamma kategoriyalar ko'rinadi
  const catsRef = useRef(null);

  const { categories, themes } = useMemo(() => {
    const raw = boot.settings.themes || {};
    const list = [...(boot.settings.theme_categories || [])];
    // Bot hali yangilanmagan yoki sohasi noma'lum shablon bo'lsa — «Umumiy»ga tushadi
    const keys = new Set(list.map((c) => c.key));
    const items = Object.entries(raw).map(([key, theme]) => ({
      key,
      theme,
      category: keys.has(theme.category) ? theme.category : FALLBACK,
    }));
    if (!keys.has(FALLBACK) && items.some((i) => i.category === FALLBACK)) {
      list.push({ key: FALLBACK, short: 'Umumiy', name: 'Umumiy', emoji: '✨', keywords: '' });
    }
    const byKey = Object.fromEntries(list.map((c) => [c.key, c]));
    return {
      categories: list,
      themes: items.map((item) => {
        const c = byKey[item.category];
        return { ...item, haystack: normalize([item.theme.name, item.theme.about, t(item.theme.name), t(item.theme.about ?? ''), c?.name, c?.keywords].join(' ')) };
      }),
    };
  }, [boot.settings]);

  useEffect(() => {
    api('/materials?kind=shablon&limit=50')
      .then((data) => setFiles(data.materials))
      .catch(() => setFiles([]));
  }, []);

  const words = normalize(query).split(' ').filter(Boolean);
  const matches = (haystack) => words.every((w) => haystack.includes(w));

  const counts = themes.reduce((acc, item) => ({ ...acc, [item.category]: (acc[item.category] || 0) + 1 }), {});
  const current = categories.find((c) => c.key === category);
  const visible = themes.filter((item) => (!current || item.category === current.key) && matches(item.haystack));
  const sections = categories
    .map((c) => ({ ...c, items: visible.filter((item) => item.category === c.key) }))
    .filter((c) => c.items.length > 0);
  const visibleFiles = current
    ? []
    : files.filter((f) => matches(normalize(`${f.title} ${f.description || ''}`))).slice(0, words.length ? undefined : 3);

  // Soha tanlanmagan bo'lsa — hamma kategoriyalar ko'rinadi (ostida uzun ro'yxat yo'q).
  // Tanlanganda bitta qatorga yig'iladi; tanlangan soha qatordan tashqarida bo'lsa — oxirgi kvadrat o'rniga chiqadi
  let tiles = categories;
  if (!expanded) {
    tiles = categories.slice(0, ROW);
    if (current && !tiles.includes(current)) tiles = [...tiles.slice(0, ROW - 1), current];
  }

  const pick = (key) => {
    haptic('select');
    setCategory((prev) => (prev === key ? ALL : key)); // qayta bosilsa — tanlov bekor bo'ladi
    setExpanded(false);
  };

  const toggleAll = () => {
    haptic('light');
    setExpanded((v) => !v);
  };

  const order = (key) => {
    haptic('light');
    push('order', { kind: 'pres', theme: key });
  };

  const recommended = useMemo(() => buildRecommended(themes), [themes]);
  const favItems = recommended.filter((r) => fav.has(r.id));
  const favThemes = themes.filter((t) => !t.theme.style && fav.has(`theme:${t.key}`));
  const docMode = ['referat', 'kurs', 'mustaqil'].includes(type);
  // Oxirgi sevimli olib tashlansa — «Sevimlilar» tugmasi yo'qoladi, sahifa «Barchasi» ga qaytadi
  useEffect(() => {
    if (type === 'fav' && fav.size === 0) setType('all');
  }, [type, fav]);

  const pickRec = (item) => {
    haptic('light');
    if (item.type === 'doc') push('order', { kind: item.key });
    else push('order', { kind: 'pres', theme: item.key });
  };

  const pickType = (key) => {
    if (key === type) return;
    haptic('select');
    setType(key);
    if (key !== 'all' && key !== 'pres') setCategory(ALL);
  };

  return (
    <main className="page">
      {asTab ? (
        <header className="tpl-head">
          <h1>{t('Shablonlar')}</h1>
          <p>{t('Tayyor, zamonaviy va mos shablonlar')}</p>
        </header>
      ) : (
        <TopBar title={t('Shablonlar')} />
      )}

      <div className="tpl-filter">
        <div className="tpl-filter__row">
          <label className="tpl-search">
            <SearchIcon size={20} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={current ? t('{name} ichidan qidirish...', { name: t(current.short || current.name) }) : t('Shablon qidirish...')}
              enterKeyHint="search"
              type="search"
            />
            {query && (
              <button className="search__clear" onClick={() => setQuery('')} aria-label={t('Tozalash')}>
                <CloseIcon size={14} />
              </button>
            )}
          </label>
          <button
            className={`tpl-filter__btn ${expanded ? 'tpl-filter__btn--open' : ''} ${current ? 'tpl-filter__btn--on' : ''}`}
            onClick={() => {
              // Filtr — barcha kategoriyalarni ochadi / yig'adi (hujjat turlarida — taqdimot shablonlariga qaytadi)
              if (docMode || type === 'fav') setType('all');
              toggleAll();
              setTimeout(() => catsRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50);
            }}
            aria-label={t('Kategoriyalar')}
            aria-expanded={expanded}
          >
            <FilterIcon size={22} />
          </button>
        </div>
        <div className="type-chips" role="tablist" aria-label={t('Turi')}>
          {TYPES.map(([key, label]) => (
            <button key={key} role="tab" aria-selected={type === key} className={`type-chip ${type === key ? 'type-chip--on' : ''}`} onClick={() => pickType(key)}>
              {t(label)}
            </button>
          ))}
          {fav.size > 0 && (
            <button role="tab" aria-selected={type === 'fav'} className={`type-chip ${type === 'fav' ? 'type-chip--on' : ''}`} onClick={() => pickType('fav')}>
              <span className="type-chip__heart" aria-hidden="true">♥</span> {t('Sevimlilar')}
            </button>
          )}
        </div>
      </div>

      {docMode && <DocTypeView kind={type} query={query} />}

      {type === 'fav' && (
        favItems.length || favThemes.length ? (
          <>
            <div className="section-head"><h2>{t('Sevimli shablonlar')}</h2><span className="badge">{favItems.length + favThemes.length}</span></div>
            {favItems.length > 0 && <RecommendedCarousel items={favItems} fav={fav} onFav={toggleFav} onPick={pickRec} />}
            {favThemes.length > 0 && <div className="tpl-section"><ThemeCards items={favThemes} onPick={order} /></div>}
          </>
        ) : (
          <Empty icon={<span style={{ fontSize: 30 }}>♡</span>} title={t("Sevimlilar bo'sh")} text={t('Shablon kartochkasidagi yurakchani bosing — shu yerda saqlanadi.')} />
        )
      )}

      {!docMode && type !== 'fav' && (<>
      <section ref={catsRef} className="cats" aria-label={t('Kategoriyalar')}>
        <div className="section-head cats__head">
          <h2>{t('Kategoriyalar')}</h2>
          {categories.length > ROW && (
            <button className="link-btn" onClick={toggleAll}>
              {expanded ? t("Yig'ish") : t('Barchasi')} <ChevronRight size={16} className={expanded ? 'cats__chev--up' : ''} />
            </button>
          )}
        </div>
        <div className="cats__grid" role="tablist">
          {tiles.map((c) => {
            const active = c.key === category;
            return (
              <button
                key={c.key}
                role="tab"
                aria-selected={active}
                className={`cat-tile pressable ${active ? 'cat-tile--active' : ''}`}
                onClick={() => pick(c.key)}
              >
                {counts[c.key] ? <span className="cat-tile__count">{counts[c.key]}</span> : null}
                <CategoryBadge category={c} size={42} />
                <span className="cat-tile__name">{t(c.short || c.name)}</span>
              </button>
            );
          })}
        </div>
      </section>

      {current && (
        <div className="cat-result">
          <CategoryBadge category={current} size={36} />
          <span className="cat-result__text">
            <b>{t(current.name)}</b>
            <span>{counts[current.key] ? t('{n} ta shablon', { n: counts[current.key] }) : t('Tez orada')}</span>
          </span>
          <button className="cat-result__clear" onClick={() => pick(current.key)} aria-label={t('Filtrni olib tashlash')}>
            <CloseIcon size={14} /> {t('Hammasi')}
          </button>
        </div>
      )}

      {!current && !words.length && (
        <p className="cats__hint">{t('Mavzungizga mos sohani tanlang — faqat shu soha shablonlari chiqadi.')}</p>
      )}

      {(current || words.length > 0) && sections.length === 0 && (
        <div className="empty">
          {words.length || !current ? (
            <span className="empty__icon"><SearchIcon size={34} /></span>
          ) : (
            <CategoryBadge category={current} size={72} />
          )}
          {words.length ? (
            <>
              <b>{t('Hech narsa topilmadi')}</b>
              <span>{t("Boshqa so'z bilan qidirib ko'ring yoki barcha shablonlarni oching.")}</span>
            </>
          ) : (
            <>
              <b>{t('{name} shablonlari tez orada', { name: t(current?.name || '') })}</b>
              <span>{t('Hozircha boshqa sohadagi dizaynlardan foydalanishingiz mumkin.')}</span>
            </>
          )}
          <button
            className="chip chip--pill chip--active mt-12"
            onClick={() => {
              setQuery('');
              setCategory(ALL);
            }}
          >
            {t('Barcha shablonlar')}
          </button>
        </div>
      )}

      {current
        ? sections.map((section) => (
            <div key={section.key} className="tpl-section tpl-section--single">
              <ThemeCards items={section.items} onPick={order} />
            </div>
          ))
        : words.length > 0 && sections.map((section) => (
            <section key={section.key} className="tpl-section">
              <div className="section-head">
                <h2>{t(section.name)}</h2>
                <button
                  className="link-btn"
                  onClick={() => {
                    pick(section.key);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  {t('{n} ta', { n: section.items.length })} <ChevronRight size={16} />
                </button>
              </div>
              <ThemeCards items={section.items} onPick={order} />
            </section>
          ))}

      {!current && !words.length && <div className="mt-16"><ImportCard /></div>}

      {visibleFiles.length > 0 && (
        <>
          <div className="section-head">
            <h2>📄 {t('Tayyor shablonlar')}</h2>
          </div>
          <div className="list">
            {visibleFiles.map((item) => (
              <FileItem key={item.id} item={item} />
            ))}
          </div>
        </>
      )}
      </>)}
    </main>
  );
}
