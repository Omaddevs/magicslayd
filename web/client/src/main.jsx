import { StrictMode, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App.jsx';
import { AppProvider } from './app/AppContext.jsx';
import { AuthScreen } from './components/Auth.jsx';
import { api } from './lib/api.js';
import { initLang, t, useLang } from './lib/i18n.js';
import { restoreSession, setSession } from './lib/session.js';
import { initTelegram } from './lib/telegram.js';
import { initTheme } from './lib/theme.js';
import './styles.css';

initTelegram();
initTheme();
initLang();

function Root() {
  const [boot, setBoot] = useState(null);
  const [error, setError] = useState(null);
  useLang(); // kirish sahifasida til almashsa — qayta chiziladi

  const load = useCallback(async () => {
    try {
      const data = await api('/bootstrap');
      // Token eskirgan / chiqarilgan bo'lsa — o'chiriladi (mehmon sifatida davom etadi)
      if (!data.account) setSession('');
      setError(null);
      setBoot(data);
    } catch (e) {
      setError(e);
      throw e;
    }
  }, []);

  useEffect(() => {
    restoreSession().then(() => load().catch(() => {}));
  }, [load]);

  // Telegram'siz (oddiy brauzer) va kirilmagan — telefon + parol bilan kirish sahifasi
  if (error?.status === 401) {
    return <AuthScreen onSignedIn={load} />;
  }

  if (error) {
    return (
      <div className="splash">
        <div>
          <div style={{ fontSize: 56 }}>😕</div>
          <h2 style={{ fontWeight: 900, marginTop: 8 }}>{t("Ulanib bo'lmadi")}</h2>
          <p>{error.message}</p>
          <button className="btn btn--primary mt-16" onClick={() => window.location.reload()}>
            {t('Qayta urinish')}
          </button>
        </div>
      </div>
    );
  }

  if (!boot) {
    return (
      <div className="splash">
        <div>
          <img src="/logo.png" alt="MagicSlayd" width="112" height="112" className="splash__logo float" />
          <div className="splash__name">MagicSlayd</div>
          <p>{t('Yuklanmoqda...')}</p>
        </div>
      </div>
    );
  }

  return (
    <AppProvider boot={boot}>
      <App />
    </AppProvider>
  );
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
