import { useCallback, useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { AiArt, MaqolaDecor, MaqolaHeroArt } from '../components/Art.jsx';
import FileItem from '../components/FileItem.jsx';
import { BellIcon, ChevronRight, FolderIcon, SearchIcon } from '../components/Icons.jsx';
import { AdCarousel, Stories, StoryViewer, groupStories, useSeenStories } from '../components/News.jsx';
import ServiceIcon from '../components/ServiceIcons.jsx';
import { Avatar, Empty, Skeleton } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { badgeText } from '../lib/notify.js';
import { haptic } from '../lib/telegram.js';

// «Xizmatlarimiz»: [kalit, nomi, ochiladigan joy]. Buyurtma oynalari va jarayonlar o'zgarmagan
const SERVICES_GRID = [
  ['pres', 'Presentatsiya', ['order', { kind: 'pres' }]],
  ['referat', 'Referat', ['order', { kind: 'referat' }]],
  ['kurs', 'Kurs ishi', ['order', { kind: 'kurs' }]],
  ['diss', 'Dissertatsiya', ['dissertation']],
  ['diplom', 'Diplom ishi', ['diploma']],
  ['mustaqil', 'Mustaqil ish', ['order', { kind: 'mustaqil' }]],
];

function Logo() {
  return (
    <span className="brand" aria-label="MagicSlayd">
      <img src="/logo.png" alt="" className="brand__mark brand__mark--img" width="36" height="36" />
      <span className="brand__name">
        Magic<b>Slayd</b>
      </span>
    </span>
  );
}

export default function Home() {
  const { boot, push, setTab, openSheet, authed, openAuth, refreshUnread } = useApp();
  const [materials, setMaterials] = useState(null);
  const [news, setNews] = useState({ stories: [], ads: [] });
  const [viewer, setViewer] = useState(null); // ochilgan story guruhi indeksi
  const [seen, markSeen] = useSeenStories();
  const isAdmin = Boolean(boot.isAdmin);
  // Yangilik / story / reklama qo'shish — «📣 Xabar tarqatish» huquqi bilan
  const canPost = Boolean(boot.adminPerms?.includes('broadcast'));

  const loadNews = useCallback(() => {
    api('/news')
      .then((data) => setNews({ stories: data.stories || [], ads: data.ads || [] }))
      .catch(() => {});
  }, []);

  useEffect(() => {
    api('/materials?limit=5')
      .then((data) => setMaterials(data.materials))
      .catch(() => setMaterials([]));
    loadNews();
  }, [loadNews]);

  const groups = groupStories(news.stories);
  const unread = boot.unreadNotifications || 0;

  // Bosh sahifaga qaytilganda raqam yangilansin (yangi xabar kelgan bo'lishi mumkin)
  useEffect(() => {
    refreshUnread();
  }, [refreshUnread]);

  const openStories = (index = 0) => {
    if (!groups.length) return;
    haptic('light');
    setViewer(index);
  };

  // Qo'ng'iroqcha — bildirishnomalar (admin yuborgan e'lonlar)
  const openBell = () => {
    haptic('light');
    push('notifications');
  };

  const go = (target) => {
    haptic('light');
    push(...target);
  };

  return (
    <main className="page home">
      {/* Sarlavha: qidiruv · logo · yangiliklar · profil */}
      <header className="topbar-home">
        <button className="round-btn pressable" onClick={() => push('search')} aria-label={t('Qidirish')}>
          <SearchIcon size={21} />
        </button>
        <Logo />
        <div className="topbar-home__right">
          {isAdmin && (
            <button className="round-btn round-btn--admin pressable" onClick={() => push('admin')} aria-label={t('Admin panel')}>
              <span aria-hidden="true">🛠</span>
            </button>
          )}
          <button
            className={`round-btn pressable ${unread ? 'round-btn--ring' : ''}`}
            onClick={openBell}
            aria-label={unread ? t('Bildirishnomalar: {n} ta o\'qilmagan', { n: unread }) : t('Bildirishnomalar')}
          >
            <BellIcon size={21} />
            {unread > 0 && <span key={unread} className="bell-badge">{badgeText(unread)}</span>}
          </button>
          {authed ? (
            <button className="topbar-home__avatar pressable" onClick={() => setTab('profile')} aria-label={t('Profil')}>
              <Avatar user={boot.user} />
            </button>
          ) : (
            <button className="login-pill pressable" onClick={() => openAuth()} aria-label={t("Kirish yoki ro'yxatdan o'tish")}>
              {t('Kirish')}
            </button>
          )}
        </div>
      </header>

      {/* Yangiliklar (Story) */}
      {(groups.length > 0 || canPost) && (
        <>
          <div className="section-head home__head">
            <h2>
              {t('Yangiliklar')} <span className="home__head-muted">(Story)</span>
            </h2>
            {groups.length > 0 && (
              <button className="link-btn" onClick={() => openStories(0)}>
                {t('Barchasi')} <ChevronRight size={16} />
              </button>
            )}
          </div>
          <Stories
            stories={news.stories}
            isAdmin={canPost}
            seen={seen}
            onAdd={() => openSheet('story-new', { onSaved: loadNews })}
            onOpen={openStories}
          />
        </>
      )}

      {/* Reklama banneri — avtomatik almashadi */}
      <AdCarousel ads={news.ads} isAdmin={canPost} onAdd={() => openSheet('ad-new', { onSaved: loadNews })} onChanged={loadNews} />

      {/* Xizmatlarimiz */}
      <div className="section-head home__head">
        <h2>{t('Xizmatlarimiz')}</h2>
        <button className="link-btn" onClick={() => openSheet('create')}>
          {t('Barchasi')} <ChevronRight size={16} />
        </button>
      </div>
      <div className="svc-grid">
        {SERVICES_GRID.map(([kind, title, target]) => (
          <button key={kind} className={`svc svc--${kind} pressable`} onClick={() => go(target)}>
            <ServiceIcon kind={kind} />
            <span className="svc__title">
              {t(title)}
              <span className="svc__go" aria-hidden="true"><ChevronRight size={11} /></span>
            </span>
          </button>
        ))}
      </div>
      {/* Maqola — 3×2 tartib buzilmasin deb alohida keng karta */}
      <button className="maqola-card pressable" onClick={() => go(['article-order'])}>
        <MaqolaHeroArt className="maqola-card__art" />
        <span className="maqola-card__text">
          <span className="maqola-card__head">
            <span className="maqola-card__title">{t('Maqola')}</span>
            <span className="maqola-card__badge">{t('Yangi')} <span aria-hidden="true">✦</span></span>
          </span>
          <span className="maqola-card__sub">{t('Mavzuga mos professional maqolani tezda yarating.')}</span>
          <span className="maqola-card__btn">
            {t('Boshlash')} <ChevronRight size={16} />
          </span>
        </span>
        <MaqolaDecor className="maqola-card__decor" />
      </button>

      {/* AI yordamchi */}
      <section className="feature-card feature-card--ai">
        <div className="feature-card__text">
          <h2 className="feature-card__title">{t('AI yordamchi')}</h2>
          <p className="feature-card__sub">{t('Mavzuni yozing — reja va matn bir necha soniyada tayyor!')}</p>
          <button className="feature-card__btn pressable" onClick={() => push('ai')}>
            {t('Yaratish')}
            <ChevronRight size={18} />
          </button>
        </div>
        <AiArt className="feature-card__art" />
      </section>

      {/* Ommabop materiallar */}
      <div className="section-head">
        <h2>
          <span aria-hidden="true">🔥</span> {t('Ommabop materiallar')}
        </h2>
        <button className="link-btn" onClick={() => push('materials')}>
          {t("Barchasini ko'rish")} <ChevronRight size={16} />
        </button>
      </div>
      {materials === null ? (
        <Skeleton height={80} count={2} />
      ) : materials.length ? (
        <div className="list">
          {materials.map((item) => (
            <FileItem key={item.id} item={item} bookmarkable={false} />
          ))}
        </div>
      ) : (
        <Empty icon={<FolderIcon size={32} />} title={t("Hozircha materiallar yo'q")} text={t("Tez orada shu yerda eng ko'p yuklangan ishlar chiqadi.")} />
      )}

      {viewer !== null && (
        <StoryViewer
          stories={news.stories}
          startGroup={viewer}
          isAdmin={canPost}
          onClose={() => {
            setViewer(null);
            loadNews(); // like soni va holati yangilansin
          }}
          onSeen={markSeen}
          onDeleted={loadNews}
        />
      )}
    </main>
  );
}
