import { useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { TileArt } from '../components/Art.jsx';
import FileItem from '../components/FileItem.jsx';
import { ChevronRight, CloseIcon, SearchIcon } from '../components/Icons.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { SERVICES } from '../lib/services.js';

const ORDERABLE = ['pres', 'referat', 'kurs', 'mustaqil'];

export default function Search() {
  const { push } = useApp();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const input = useRef();

  useEffect(() => {
    input.current?.focus();
  }, []);

  // Yozish to'xtagandan 300 ms keyin qidiradi
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      return undefined;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      api(`/search?q=${encodeURIComponent(q)}`)
        .then(setResults)
        .catch(() => setResults({ materials: [], documents: [] }))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const q = query.trim();
  const nothing = results && !results.materials.length && !results.documents.length;

  return (
    <main className="page">
      <TopBar title={t('Qidiruv')} />
      <label className="search">
        <SearchIcon size={24} />
        <input
          ref={input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('Mavzu, hujjat yoki shablon qidirish...')}
          enterKeyHint="search"
        />
        {query && (
          <button className="search__clear" onClick={() => setQuery('')} aria-label={t('Tozalash')}>
            <CloseIcon size={14} />
          </button>
        )}
      </label>

      {q.length < 2 && (
        <>
          <div className="section-head">
            <h2>{t('Yangi ish buyurtma qilish')}</h2>
          </div>
          <div className="menu" style={{ marginTop: 0 }}>
            {ORDERABLE.map((kind) => (
              <button key={kind} className="menu__item pressable" onClick={() => push('order', { kind })}>
                <div className={`menu__icon tile--${SERVICES[kind].color}`}>
                  <TileArt kind={kind} className="" />
                </div>
                <span>
                  {t(SERVICES[kind].title)}
                  <br />
                  <small>{t(SERVICES[kind].sub)}</small>
                </span>
                <ChevronRight size={20} />
              </button>
            ))}
          </div>
        </>
      )}

      {q.length >= 2 && loading && !results && <div className="mt-16"><Skeleton /></div>}

      {results && (
        <>
          {/* Topilmasa — shu mavzuda yangi ish yaratishni taklif qilamiz */}
          <div className="card mt-16">
            <div className="card__label">{t('«{q}» mavzusida yangi ish', { q })}</div>
            <div className="chips">
              {ORDERABLE.map((kind) => (
                <button
                  key={kind}
                  className="chip"
                  onClick={() => push('order', { kind, initial: { topic: q } })}
                >
                  {t(SERVICES[kind].label)}
                </button>
              ))}
            </div>
          </div>

          {results.materials.length > 0 && (
            <>
              <div className="section-head">
                <h2>{t('Materiallar')}</h2>
              </div>
              <div className="list">
                {results.materials.map((item) => (
                  <FileItem key={`m${item.id}`} item={item} />
                ))}
              </div>
            </>
          )}
          {results.documents.length > 0 && (
            <>
              <div className="section-head">
                <h2>{t('Mening hujjatlarim')}</h2>
              </div>
              <div className="list">
                {results.documents.map((item) => (
                  <FileItem key={`d${item.id}`} item={item} source="document" />
                ))}
              </div>
            </>
          )}
          {nothing && <Empty icon={<SearchIcon size={32} />} title={t('Hech narsa topilmadi')} text={t('Yuqoridagi tugmalar orqali shu mavzuda yangi ish yaratishingiz mumkin.')} />}
        </>
      )}
    </main>
  );
}
