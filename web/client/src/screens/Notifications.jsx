import { useEffect, useMemo, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import NotifCard from '../components/NotifCard.jsx';
import { Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { badgeText, dayGroup } from '../lib/notify.js';
import { haptic } from '../lib/telegram.js';

const GROUPS = ['Bugun', 'Kecha', 'Shu hafta', 'Avvalroq'];

const CheckAllIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m2.5 12.5 4.5 4.5L15.5 8.5" />
    <path d="m11.5 16 1 1 9-9.5" />
  </svg>
);

function EmptyBell({ title, text }) {
  return (
    <div className="notif-empty">
      <div className="notif-empty__art" aria-hidden="true">
        <span className="notif-empty__ring" />
        <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z" />
          <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
        </svg>
      </div>
      <b>{title}</b>
      <span>{text}</span>
    </div>
  );
}

/** Bildirishnomalar: Hammasi / O'qilmagan / O'qilgan, sana bo'yicha guruhlangan. */
export default function Notifications() {
  const { push, setUnread, toast } = useApp();
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    api('/notifications')
      .then((data) => {
        setItems(data.items);
        setUnread(data.unread);
      })
      .catch((error) => {
        setItems([]);
        toast(error.message, 'error');
      });
  }, [setUnread, toast]);

  const counts = useMemo(() => {
    const unread = (items || []).filter((i) => !i.read).length;
    return { all: items?.length ?? 0, unread, read: (items?.length ?? 0) - unread };
  }, [items]);

  const shown = (items || []).filter((i) => (filter === 'unread' ? !i.read : filter === 'read' ? i.read : true));
  const groups = GROUPS.map((name) => ({ name, list: shown.filter((i) => dayGroup(i.createdAt) === name) })).filter((g) => g.list.length);

  const open = (item) => {
    haptic('light');
    // Darhol o'qilgan ko'rinsin (server ham detail ochilganda belgilaydi)
    if (!item.read) {
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, read: true } : i)));
      setUnread(counts.unread - 1);
    }
    push('notification', { id: item.id });
  };

  const readAll = async () => {
    haptic('success');
    setItems((prev) => prev.map((i) => ({ ...i, read: true })));
    setUnread(0);
    try {
      await api('/notifications/read-all', { method: 'POST' });
      toast(t("Hammasi o'qilgan deb belgilandi") + ' ✓');
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  const tabs = [
    ['all', t('Hammasi'), counts.all],
    ['unread', t("O'qilmagan"), counts.unread],
    ['read', t("O'qilgan"), counts.read],
  ];

  return (
    <main className="page notif-page">
      <TopBar
        title={t('Bildirishnomalar')}
        right={counts.unread > 0 && (
          <button className="notif-readall pressable" onClick={readAll} aria-label={t("Hammasini o'qilgan deb belgilash")}>
            <CheckAllIcon />
            <span>{t("Hammasini o'qish")}</span>
          </button>
        )}
      />

      <div className="segment notif-tabs" role="tablist">
        {tabs.map(([key, label, n]) => (
          <button key={key} role="tab" aria-selected={filter === key} className={filter === key ? 'segment--active' : ''}
            onClick={() => { haptic('select'); setFilter(key); }}>
            {label}
            {items && n > 0 && <span className={`notif-tabs__n ${key === 'unread' ? 'notif-tabs__n--hot' : ''}`}>{badgeText(n)}</span>}
          </button>
        ))}
      </div>

      {items === null ? (
        <div className="mt-16"><Skeleton height={84} count={4} /></div>
      ) : groups.length ? (
        groups.map((group) => (
          <section key={group.name} className="notif-group">
            <h2 className="notif-group__title">{t(group.name)}</h2>
            <div className="notif-list">
              {group.list.map((item) => <NotifCard key={item.id} item={item} onOpen={() => open(item)} />)}
            </div>
          </section>
        ))
      ) : filter === 'unread' && counts.all > 0 ? (
        <EmptyBell title={t("Hammasi o'qilgan") + ' 🎉'} text={t("Yangi xabar kelganda shu yerda ko'rasiz.")} />
      ) : filter === 'read' && counts.all > 0 ? (
        <EmptyBell title={t("O'qilgan xabarlar yo'q")} text={t("Ochib o'qigan xabarlaringiz shu yerga o'tadi.")} />
      ) : (
        <EmptyBell title={t("Hozircha xabarlar yo'q")} text={t("Yangiliklar, aksiyalar va muhim e'lonlar shu yerda chiqadi.")} />
      )}
    </main>
  );
}
