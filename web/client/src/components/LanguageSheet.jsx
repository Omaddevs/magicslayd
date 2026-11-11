import { useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { LANGS, setLang, t, useLang } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';
import Flag from './Flag.jsx';
import { Sheet } from './ui.jsx';

const Check = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);

/** Ilova tilini tanlash: bayroq · til nomi (o'z tilida) · joriy tildagi nomi. */
export default function LanguageSheet({ close }) {
  const { toast } = useApp();
  const lang = useLang();
  const [picked, setPicked] = useState(lang);

  const choose = (code) => {
    if (code === lang) {
      close();
      return;
    }
    haptic('select');
    setPicked(code);
    // Tanlov belgisi ko'rinib ulgursin, keyin ilova yangi tilda qayta chiziladi
    setTimeout(() => {
      setLang(code);
      close();
      haptic('success');
      toast(t("Til o'zgartirildi"));
    }, 220);
  };

  return (
    <Sheet title={t('Tilni tanlang')} onClose={close}>
      <p className="lang-sheet__hint">{t("Ilova shu tilda ko'rsatiladi. Istalgan vaqtda o'zgartirishingiz mumkin.")}</p>
      <div className="lang-list" role="radiogroup" aria-label={t('Tilni tanlang')}>
        {LANGS.map(({ code, name, sub }) => {
          const active = picked === code;
          return (
            <button
              key={code}
              role="radio"
              aria-checked={active}
              className={`lang-item pressable ${active ? 'lang-item--active' : ''}`}
              onClick={() => choose(code)}
            >
              <span className="lang-item__flag">
                <Flag lang={code} width={36} className="lang-flag" />
              </span>
              <span className="lang-item__text">
                <b>{name}</b>
                <small>{t(sub)}</small>
              </span>
              <span className="lang-item__radio">{active && <Check />}</span>
            </button>
          );
        })}
      </div>
    </Sheet>
  );
}
