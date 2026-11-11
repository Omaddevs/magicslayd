import { useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import FileItem from '../components/FileItem.jsx';
import { BookmarkIcon, FolderIcon } from '../components/Icons.jsx';
import { Empty, Skeleton } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';

/** Mehmon uchun: loyihalar hisobga bog'langan. */
function GuestProjects() {
  const { openAuth, boot } = useApp();
  const registerFirst = Boolean(boot.authHint) && !boot.authHint.registered;
  return (
    <div className="guest-empty">
      <div className="guest-empty__art" aria-hidden="true">
        <span className="guest-empty__card guest-empty__card--a" />
        <span className="guest-empty__card guest-empty__card--b" />
        <span className="guest-empty__lock">🔒</span>
      </div>
      <b>{t('Loyihalaringiz shu yerda saqlanadi')}</b>
      <span>{t("Yaratgan taqdimot, referat va saqlagan materiallaringizni ko'rish uchun hisobingizga kiring.")}</span>
      <div className="guest-empty__actions">
        <button className="btn btn--primary" onClick={() => openAuth({ view: registerFirst ? 'register' : 'login' })}>
          {registerFirst ? t("Ro'yxatdan o'tish") : t('Kirish')}
        </button>
        <button className="btn btn--soft" onClick={() => openAuth({ view: registerFirst ? 'login' : 'register' })}>
          {registerFirst ? t('Menda hisob bor') : t("Ro'yxatdan o'tish")}
        </button>
      </div>
    </div>
  );
}

export default function Saved() {
  const { openSheet, authed } = useApp();
  const [view, setView] = useState('documents');
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!authed) return;
    api('/saved')
      .then(setData)
      .catch(() => setData({ documents: [], bookmarks: [] }));
  }, [authed]);

  const removeBookmark = (item, saved) => {
    if (!saved) setData((prev) => ({ ...prev, bookmarks: prev.bookmarks.filter((b) => b.id !== item.id) }));
  };

  if (!authed) {
    return (
      <main className="page">
        <h1 className="page-title">{t('Loyihalar')}</h1>
        <GuestProjects />
      </main>
    );
  }

  const items = data?.[view === 'documents' ? 'documents' : 'bookmarks'] ?? [];

  return (
    <main className="page">
      <h1 className="page-title">{t('Loyihalar')}</h1>
      <div className="segment">
        <button className={view === 'documents' ? 'segment--active' : ''} onClick={() => setView('documents')}>
          {t('Hujjatlarim')} {data ? `(${data.documents.length})` : ''}
        </button>
        <button className={view === 'bookmarks' ? 'segment--active' : ''} onClick={() => setView('bookmarks')}>
          {t('Materiallar')} {data ? `(${data.bookmarks.length})` : ''}
        </button>
      </div>

      <div className="mt-16">
        {data === null ? (
          <Skeleton />
        ) : items.length ? (
          <div className="list">
            {view === 'documents'
              ? items.map((item) => <FileItem key={item.id} item={item} source="document" />)
              : items.map((item) => <FileItem key={item.id} item={item} onBookmark={removeBookmark} />)}
          </div>
        ) : view === 'documents' ? (
          <Empty
            icon={<FolderIcon size={32} />}
            title={t("Hali hujjatlaringiz yo'q")}
            text={t('Bot yoki ilova orqali yaratilgan barcha fayllar shu yerda saqlanadi.')}
          >
            <button className="btn btn--primary btn--sm mt-12" onClick={() => openSheet('create')}>
              {t('Birinchi ishni yaratish')}
            </button>
          </Empty>
        ) : (
          <Empty
            icon={<BookmarkIcon size={32} />}
            title={t("Saqlangan materiallar yo'q")}
            text={t("Ommabop materiallardagi 🔖 belgisini bosib saqlab qo'ying.")}
          />
        )}
      </div>
    </main>
  );
}
