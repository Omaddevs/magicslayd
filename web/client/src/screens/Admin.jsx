import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { ChevronRight, SearchIcon } from '../components/Icons.jsx';
import { KindChip } from '../components/NotifCard.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api, apiBlob } from '../lib/api.js';
import { initials, money, shortDate } from '../lib/format.js';
import { getLang, t } from '../lib/i18n.js';
import { badgeText } from '../lib/notify.js';
import { KIND_LABEL } from '../lib/services.js';
import { confirmDialog, haptic } from '../lib/telegram.js';

// [kalit, belgi, nomi, kerakli huquq] — admin faqat huquqi bor bo'limlarni ko'radi (bot/admins.py → PERMS)
const TABS = [
  ['overview', '📊', 'Umumiy', 'stats'],
  ['users', '👥', 'Userlar', 'users'],
  ['payments', '💳', "To'lovlar", 'payments'],
  ['messages', '📣', 'Xabarlar', 'broadcast'],
  ['apis', '🔌', 'API', 'stats'],
];
// Huquqlar — bot/admins.py → PERMS bilan bir xil kalitlar va tartib
const PERM_LABELS = {
  payments: "💳 Cheklarni ko'rish va tasdiqlash",
  users: '👤 Userlar: qidirish, xabar yozish',
  balance: "💰 Balansni o'zgartirish",
  broadcast: '📣 Xabar tarqatish, yangilik, story, reklama',
  stats: '📊 Statistika, xarajat va API',
  free: "🎁 O'z buyurtmalari bepul",
};
const MONTHS = {
  uz: ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
  ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};
const dayLabel = (day) => {
  const [, m, d] = day.split('-').map(Number);
  return `${d} ${(MONTHS[getLang()] ?? MONTHS.uz)[m - 1]}`;
};
const compact = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}K` : String(n));

// ===================== Grafik: kunlik ustunlar (bitta qator — bitta rang, sarlavha nomlaydi) =====================
function BarChart({ title, total, data, format = (n) => String(n), floor = 1 }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(floor, ...data.map((d) => d.n));
  const last = data[data.length - 1];
  return (
    <section className="card chart">
      <div className="chart__head">
        <span className="chart__title">{title}</span>
        <b className="chart__total">{total}</b>
      </div>
      <div className="chart__plot" role="img" aria-label={`${title}: ${data.map((d) => `${dayLabel(d.day)} ${format(d.n)}`).join(', ')}`}
        onMouseLeave={() => setHover(null)}>
        <div className="chart__grid" aria-hidden="true"><span /><span /><span /></div>
        <div className="chart__bars">
          {data.map((d, i) => (
            <button
              key={d.day}
              type="button"
              className={`chart__col ${hover === i ? 'chart__col--on' : ''}`}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onClick={() => setHover(hover === i ? null : i)}
              aria-label={`${dayLabel(d.day)}: ${format(d.n)}`}
            >
              <span className="chart__bar" style={{ height: `${d.n ? Math.max(4, (d.n / max) * 100) : 0}%` }} />
            </button>
          ))}
        </div>
        {hover !== null && (
          <div className="chart__tip" style={{ left: `${((hover + 0.5) / data.length) * 100}%` }}>
            <b>{format(data[hover].n)}</b>
            <span>{dayLabel(data[hover].day)}</span>
          </div>
        )}
      </div>
      <div className="chart__axis" aria-hidden="true">
        <span>{dayLabel(data[0].day)}</span>
        <span>{t('max')}: {format(max)}</span>
        <span>{dayLabel(last.day)}</span>
      </div>
    </section>
  );
}

function Stat({ icon, label, value, sub, tone = 'purple', onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag className={`astat astat--${tone} ${onClick ? 'pressable' : ''}`} onClick={onClick}>
      <span className="astat__icon" aria-hidden="true">{icon}</span>
      <span className="astat__label">{label}</span>
      <b className="astat__value">{value}</b>
      {sub && <span className="astat__sub">{sub}</span>}
    </Tag>
  );
}

// ===================== 📊 Umumiy =====================
function Overview({ data, go }) {
  if (!data) return <Skeleton height={110} count={4} />;
  const { users, documents, money: m, series, activeOrders } = data;
  const kinds = Object.entries(documents.byKind).sort((a, b) => b[1] - a[1]);
  const maxKind = Math.max(1, ...kinds.map(([, n]) => n));
  return (
    <>
      <div className="astats">
        <Stat icon="👥" label={t('Foydalanuvchilar')} value={users.total} sub={t('+{today} bugun · +{week} 7 kunda', users)} />
        <Stat icon="🔐" label={t("Ro'yxatdan o'tgan")} value={users.accounts}
          sub={t('{p}% foydalanuvchilar', { p: users.total ? Math.round((users.accounts / users.total) * 100) : 0 })} tone="blue" />
        <Stat icon="💰" label={t('Tushum')} value={money(m.revenue)} sub={t('{week} — 7 kunda', { week: money(m.week) })} tone="green" />
        <Stat icon="📄" label={t('Hujjatlar')} value={documents.total} sub={t('+{n} bugun', { n: documents.today })} tone="orange" />
        <Stat icon="👛" label={t('Balanslarda')} value={money(m.balances)} sub={t('userlar hisobidagi pul')} tone="blue" />
        <Stat icon="⏳" label={t('Tekshiruvdagi to\'lovlar')} value={m.pending} sub={m.pending ? money(m.pendingSum) : t("hammasi ko'rilgan")}
          tone={m.pending ? 'red' : 'green'} onClick={m.pending ? () => go('payments') : undefined} />
      </div>
      {activeOrders > 0 && <div className="note note--info">⚙️ {t('Hozir tayyorlanayotgan buyurtmalar: {n}', { n: activeOrders })}</div>}

      <BarChart title={t('Yangi foydalanuvchilar · 14 kun')} total={`+${series.users.reduce((s, d) => s + d.n, 0)}`} data={series.users} />
      <BarChart title={t('Tushum · 14 kun')} total={compact(series.revenue.reduce((s, d) => s + d.n, 0))} data={series.revenue} format={money} />
      <BarChart title={t('Yaratilgan hujjatlar · 14 kun')} total={series.documents.reduce((s, d) => s + d.n, 0)} data={series.documents} />

      {kinds.length > 0 && (
        <section className="card">
          <div className="card__label">{t("Hujjatlar turi bo'yicha")}</div>
          <div className="hbars">
            {kinds.map(([kind, n]) => (
              <div key={kind} className="hbar">
                <span className="hbar__label">{KIND_LABEL(kind)}</span>
                <span className="hbar__track"><span style={{ width: `${(n / maxKind) * 100}%` }} /></span>
                <b className="hbar__value">{n}</b>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

// ===================== 👥 Userlar =====================
function UserDetail({ id, onChanged }) {
  const { boot, toast } = useApp();
  const canBalance = Boolean(boot.adminPerms?.includes('balance')); // «💰 Balans» huquqi
  const [data, setData] = useState(null);
  const [amount, setAmount] = useState('');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api(`/admin/users/${id}`).then(setData).catch((e) => toast(e.message, 'error'));
  }, [id, toast]);
  useEffect(load, [load]);

  const changeBalance = async (sign) => {
    const n = Number(amount.replace(/\D/g, ''));
    if (!n) return toast(t("Summani to'g'ri kiriting."), 'error');
    if (!(await confirmDialog(t('{change} — balansni o\'zgartirasizmi?', { change: `${sign > 0 ? '+' : '−'}${money(n)}` })))) return;
    setBusy(true);
    try {
      await api(`/admin/users/${id}/balance`, { method: 'POST', body: { amount: sign * n } });
      haptic('success');
      toast(t("Balans o'zgartirildi") + ' ✅');
      setAmount('');
      load();
      onChanged();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api(`/admin/users/${id}/message`, { method: 'POST', body: { text } });
      haptic('success');
      toast(t('Xabar yuborildi') + ' 📩');
      setText('');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <div className="auser__detail"><Skeleton height={60} count={2} /></div>;
  return (
    <div className="auser__detail">
      <div className="auser__facts">
        <span>🆔 <code>{data.user.id}</code></span>
        <span>🗓 {data.user.joinedAt || '—'}</span>
        <span>📂 {t('{n} ta hujjat', { n: data.user.docs })}</span>
      </div>
      <div className="auser__balance">
        <span>{t('Balans')}: <b>{money(data.user.balance)}</b></span>
        {canBalance && <div className="auser__row">
          <input className="field" inputMode="numeric" placeholder={t('Summa, masalan 20000')} value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d ]/g, ''))} />
          <button className="btn btn--sm abtn--plus" disabled={busy} onClick={() => changeBalance(1)}>＋</button>
          <button className="btn btn--sm abtn--minus" disabled={busy} onClick={() => changeBalance(-1)}>−</button>
        </div>}
      </div>
      <div className="auser__row auser__row--msg">
        <textarea className="field" rows={2} maxLength={3500} placeholder={t('Userga shaxsiy xabar (bot orqali)…')} value={text}
          onChange={(e) => setText(e.target.value)} />
        <button className="btn btn--primary btn--sm" disabled={busy || !text.trim()} onClick={sendMessage}>{t('Yuborish')}</button>
      </div>
      {data.transactions.length > 0 && (
        <div className="auser__tx">
          <div className="card__hint">{t('Oxirgi amallar')}</div>
          {data.transactions.slice(0, 6).map((tx) => (
            <div key={tx.id} className="auser__txrow">
              <span>{t({ topup: "Hisob to'ldirildi", charge: 'Buyurtma', refund: 'Qaytarildi', admin: "Admin o'zgartirdi", bonus: 'Bonus' }[tx.kind] ?? tx.kind)}</span>
              <span className="muted">{shortDate(tx.created_at)}</span>
              <b className={tx.amount > 0 ? 'plus' : 'minus'}>{tx.amount > 0 ? '+' : '−'}{money(Math.abs(tx.amount))}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Users() {
  const [q, setQ] = useState('');
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const timer = useRef();

  const load = useCallback((query) => {
    api(`/admin/users?q=${encodeURIComponent(query)}`).then(setData).catch(() => setData({ users: [], total: 0 }));
  }, []);
  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => load(q.trim()), q ? 300 : 0);
    return () => clearTimeout(timer.current);
  }, [q, load]);

  return (
    <>
      <label className="search admin-search">
        <SearchIcon size={22} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('ID, @username, telefon yoki ism…')} enterKeyHint="search" />
      </label>
      {data === null ? (
        <Skeleton height={70} count={4} />
      ) : data.users.length ? (
        <>
          <p className="card__hint admin-count">{q ? t('Topildi: {n}', { n: data.users.length }) : t('Oxirgi qo\'shilganlar · jami {n}', { n: data.total })}</p>
          <div className="auser-list">
            {data.users.map((u) => (
              <div key={u.id} className={`auser ${open === u.id ? 'auser--open' : ''}`}>
                <button className="auser__head" onClick={() => { haptic('select'); setOpen(open === u.id ? null : u.id); }} aria-expanded={open === u.id}>
                  <span className="auser__avatar">{initials(u.name)}</span>
                  <span className="auser__main">
                    <b>{u.name || '—'}</b>
                    <small>{[u.username && `@${u.username}`, u.phone].filter(Boolean).join(' · ') || t("Ro'yxatdan o'tmagan")}</small>
                  </span>
                  <span className="auser__money">{money(u.balance)}</span>
                  <ChevronRight size={18} className="auser__chev" />
                </button>
                {open === u.id && <UserDetail id={u.id} onChanged={() => load(q.trim())} />}
              </div>
            ))}
          </div>
        </>
      ) : (
        <Empty icon={<SearchIcon size={30} />} title={t('Hech narsa topilmadi')} text={t("Boshqa so'z bilan qidirib ko'ring.")} />
      )}
    </>
  );
}

// ===================== 💳 To'lovlar =====================
function Receipt({ payment }) {
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let url;
    apiBlob(`/admin/payments/${payment.id}/receipt`)
      .then((f) => { url = f.url; setFile(f); })
      .catch((e) => setError(e.message));
    return () => url && URL.revokeObjectURL(url);
  }, [payment.id]);
  if (error) return <div className="apay__receipt apay__receipt--empty">⚠️ {error}</div>;
  if (!file) return <div className="apay__receipt skeleton" />;
  if (file.type === 'application/pdf') {
    return <a className="apay__receipt apay__receipt--pdf" href={file.url} target="_blank" rel="noreferrer">📄 {t('Chekni ochish (PDF)')}</a>;
  }
  return <a className="apay__receipt" href={file.url} target="_blank" rel="noreferrer"><img src={file.url} alt={t('Chek')} /></a>;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ORDER_SIZE = (o) => (o.kind === 'pres' ? `${o.params.slides} ${t('slayd')}` : `${o.params.pages ?? ''} ${t('bet')}`);

function Payments({ onChanged }) {
  const { toast } = useApp();
  const [filter, setFilter] = useState('pending');
  const [list, setList] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    api(`/admin/payments?status=${filter}`).then((d) => setList(d.payments)).catch(() => setList([]));
  }, [filter]);
  useEffect(() => { setList(null); load(); }, [load]);

  const review = async (p, approve) => {
    const question = approve
      ? t("{sum} — to'lovni tasdiqlaysizmi? Balansga tushadi va userga xabar boradi.", { sum: money(p.amount) })
      : t("To'lov #{id} rad etilsinmi? Userga xabar boradi.", { id: p.id });
    if (!(await confirmDialog(question))) return;
    setBusy(p.id);
    haptic('medium');
    try {
      const { orderId } = await api(`/admin/payments/${p.id}/review`, { method: 'POST', body: { approve } });
      // Bot bajaradi (odatda 1–3 soniya)
      for (let i = 0; i < 30; i++) {
        await wait(1000);
        const r = await api(`/admin/review/${orderId}`);
        if (r.status === 'done') {
          haptic('success');
          toast(approve ? t('Tasdiqlandi') + ' ✅' : t('Rad etildi') + ' ❌');
          break;
        }
        if (r.status === 'failed') throw new Error(t(r.error || "Bajarib bo'lmadi. Qayta urinib ko'ring."));
        if (i === 29) toast(t('Bot hali javob bermadi — biroz kutib, ro\'yxatni yangilang.'), 'error');
      }
      load();
      onChanged();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(null);
    }
  };

  const STATUS = { pending: ['⏳', t('Tekshiruvda'), 'badge--warn'], approved: ['✅', t('Tasdiqlandi'), 'badge--ok'], rejected: ['❌', t('Rad etildi'), 'badge--bad'] };

  return (
    <>
      <div className="segment" role="tablist">
        <button role="tab" aria-selected={filter === 'pending'} className={filter === 'pending' ? 'segment--active' : ''} onClick={() => setFilter('pending')}>
          ⏳ {t('Tekshiruvda')}
        </button>
        <button role="tab" aria-selected={filter === 'all'} className={filter === 'all' ? 'segment--active' : ''} onClick={() => setFilter('all')}>
          🧾 {t('Hammasi')}
        </button>
      </div>
      {list === null ? (
        <div className="mt-12"><Skeleton height={140} count={3} /></div>
      ) : list.length ? (
        <div className="apay-list">
          {list.map((p) => {
            const [icon, label, tone] = STATUS[p.status] ?? ['•', p.status, ''];
            return (
              <article key={p.id} className="card apay">
                <div className="apay__top">
                  <span className="apay__id">#{p.id}</span>
                  <span className={`badge ${tone}`}>{icon} {label}</span>
                  <span className="apay__date">{shortDate(p.createdAt)}</span>
                </div>
                <div className="apay__body">
                  {p.status === 'pending' && <Receipt payment={p} />}
                  <div className="apay__info">
                    <b className="apay__amount">{money(p.amount)}</b>
                    <span>{p.name || '—'}{p.username ? ` · @${p.username}` : ''}</span>
                    <span className="muted">ID {p.userId}</span>
                    {p.order && <span className="apay__order">📦 {KIND_LABEL(p.order.kind)} · {ORDER_SIZE(p.order)}</span>}
                  </div>
                </div>
                {p.status === 'pending' && (
                  <div className="btn-row">
                    <button className="btn btn--sm abtn--reject" disabled={busy !== null} onClick={() => review(p, false)}>❌ {t('Rad etish')}</button>
                    <button className="btn btn--sm abtn--approve" disabled={busy !== null} onClick={() => review(p, true)}>
                      {busy === p.id ? t('Bajarilmoqda…') : `✅ ${t('Tasdiqlash')}`}
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <Empty icon={<span style={{ fontSize: 30 }}>✅</span>} title={filter === 'pending' ? t("Tekshiruvni kutayotgan to'lov yo'q") : t("To'lovlar yo'q")} />
      )}
    </>
  );
}

// ===================== 👑 Adminlar (faqat bot egasi) =====================
// Qo'shish / o'chirishni bot bajaradi (yangi adminga Telegram xabari va admin menyusi boradi) — natija kutiladi
async function waitJob(orderId) {
  for (let i = 0; i < 30; i++) {
    await wait(1000);
    const r = await api(`/admin/review/${orderId}`);
    if (r.status === 'done') return;
    if (r.status === 'failed') throw new Error(t(r.error || "Bajarib bo'lmadi. Qayta urinib ko'ring."));
  }
  throw new Error(t("Bot hali javob bermadi — biroz kutib, ro'yxatni yangilang."));
}

function Admins() {
  const { toast } = useApp();
  const [data, setData] = useState(null);
  const [userId, setUserId] = useState('');
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    api('/admin/admins').then(setData).catch((e) => { toast(e.message, 'error'); setData({ owner: {}, admins: [], max: 2 }); });
  }, [toast]);
  useEffect(load, [load]);

  const run = async (key, request, done) => {
    setBusy(key);
    haptic('medium');
    try {
      const { orderId } = await request();
      await waitJob(orderId);
      haptic('success');
      toast(done);
      setUserId('');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(null);
      load();
    }
  };

  const add = () => {
    const id = userId.replace(/\D/g, '');
    if (id.length < 5) {
      toast(t('Telegram ID raqamini kiriting (masalan 123456789).'), 'error');
      return;
    }
    run('add', () => api('/admin/admins', { method: 'POST', body: { userId: id } }), t("Admin qo'shildi ✅ Unga Telegram'da xabar yuborildi."));
  };

  const remove = async (a) => {
    if (!(await confirmDialog(t('{name} adminlikdan olinsinmi?', { name: a.name || a.userId })))) return;
    run(a.userId, () => api(`/admin/admins/${a.userId}`, { method: 'DELETE' }), t('Adminlikdan olindi.'));
  };

  // Huquqlar: avval belgilanadi, «Saqlash» bosilganda bir marta yuboriladi (adminga bitta xabar boradi)
  const [drafts, setDrafts] = useState({});
  const permsFor = (a) => drafts[a.userId] ?? a.perms;
  const changed = (a) => drafts[a.userId] && drafts[a.userId].slice().sort().join() !== a.perms.slice().sort().join();
  const toggle = (a, perm) => {
    haptic('select');
    const current = permsFor(a);
    setDrafts((d) => ({ ...d, [a.userId]: current.includes(perm) ? current.filter((p) => p !== perm) : [...current, perm] }));
  };
  const savePerms = (a) => run(`perms:${a.userId}`, () => api(`/admin/admins/${a.userId}/perms`, { method: 'PUT', body: { perms: permsFor(a) } }),
    t("Huquqlar saqlandi ✅ Adminga Telegram'da xabar yuborildi."))
    .then(() => setDrafts((d) => { const next = { ...d }; delete next[a.userId]; return next; }));

  if (!data) return <Skeleton height={80} count={3} />;
  const free = data.max - data.admins.length;

  return (
    <>
      <section className="card">
        <div className="card__label">👑 {t('Bot egasi')}</div>
        <div className="admin-row">
          <span className="avatar avatar--sm">{initials(data.owner.name || 'Admin')}</span>
          <div>
            <b>{data.owner.name || t('Siz')}</b>
            <span className="muted"> · ID {data.owner.userId}{data.owner.username ? ` · @${data.owner.username}` : ''}</span>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__label">
          🛠 {t("Qo'shimcha adminlar")} <span className="card__hint">{data.admins.length}/{data.max}</span>
        </div>
        {data.admins.length === 0 && <p className="card__hint">{t("Hali qo'shimcha admin yo'q.")}</p>}
        {data.admins.map((a) => (
          <div key={a.userId} className="admin-block">
            <div className="admin-row">
              <span className="avatar avatar--sm">{initials(a.name || String(a.userId))}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{a.name || `ID ${a.userId}`}</b>
                <div className="muted">ID {a.userId}{a.username ? ` · @${a.username}` : ''} · {shortDate(a.addedAt)}</div>
              </div>
              <button className="btn btn--sm abtn--reject" disabled={busy !== null} onClick={() => remove(a)}>
                {busy === a.userId ? '…' : t("O'chirish")}
              </button>
            </div>
            <div className="admin-perms" role="group" aria-label={t('Huquqlar')}>
              {Object.entries(PERM_LABELS).map(([perm, label]) => {
                const on = permsFor(a).includes(perm);
                return (
                  <button key={perm} type="button" role="switch" aria-checked={on} disabled={busy !== null}
                    className={`admin-perm ${on ? 'admin-perm--on' : ''}`} onClick={() => toggle(a, perm)}>
                    <span className="admin-perm__box" aria-hidden="true">{on ? '✓' : ''}</span>
                    {t(label)}
                  </button>
                );
              })}
            </div>
            {changed(a) && (
              <button className="btn btn--primary btn--sm mt-8" disabled={busy !== null} onClick={() => savePerms(a)}>
                {busy === `perms:${a.userId}` ? t('Bajarilmoqda…') : t('Huquqlarni saqlash')}
              </button>
            )}
          </div>
        ))}
      </section>

      {free > 0 ? (
        <section className="card">
          <div className="card__label">➕ {t("Admin qo'shish")}</div>
          <input className="field" inputMode="numeric" maxLength={15} placeholder={t('Telegram ID, masalan 123456789')}
            value={userId} onChange={(e) => setUserId(e.target.value.replace(/\D/g, ''))} />
          <button className="btn btn--primary mt-12" disabled={busy !== null} onClick={add}>
            {busy === 'add' ? t('Bajarilmoqda…') : t("Admin qilish")}
          </button>
          <p className="card__hint mt-12">
            💡 {t("ID ni odam @userinfobot dan bilib oladi. Qulayroq yo'l — botda /adminlar → «Kontaktlardan tanlash».")}
          </p>
        </section>
      ) : (
        <p className="note note--info">{t("Ko'pi bilan {n} ta qo'shimcha admin bo'ladi. Yangisini qo'shish uchun avval birini o'chiring.", { n: data.max })}</p>
      )}

      <p className="card__hint">
        ℹ️ {t("Yangi admin faqat cheklarni ko'radi va tasdiqlaydi. Qolgan huquqlarni o'zingiz belgilaysiz. Admin chek tasdiqlasa yoki balansni o'zgartirsa, sizga Telegram'da xabar keladi. Admin panelga kirish uchun admin ilovada ro'yxatdan o'tgan (telefon + parol) bo'lishi kerak.")}
      </p>
    </>
  );
}

// ===================== 📣 Xabarlar =====================
function Messages() {
  const { push } = useApp();
  const [data, setData] = useState(null);
  useEffect(() => {
    api('/admin/notifications').then(setData).catch(() => setData({ items: [], audience: 0 }));
  }, []);
  return (
    <>
      <button className="amsg-cta pressable" onClick={() => push('broadcast')}>
        <span className="amsg-cta__icon" aria-hidden="true">📣</span>
        <span>
          <b>{t('Yangi xabar yuborish')}</b>
          <small>{t('{n} ta foydalanuvchiga: ilova qo\'ng\'irog\'i va Telegram bot', { n: data?.audience ?? '…' })}</small>
        </span>
        <ChevronRight size={20} />
      </button>
      <p className="card__hint amsg-hint">💡 {t('Rasm, video yoki forward xabar yuborish uchun botda /admin buyrug\'idan foydalaning — ular ham shu ro\'yxatda ko\'rinadi.')}</p>
      <div className="section-head"><h2>{t('Oxirgi xabarlar')}</h2></div>
      {data === null ? (
        <Skeleton height={80} count={3} />
      ) : data.items.length ? (
        <div className="amsg-list">
          {data.items.slice(0, 8).map((n) => {
            const done = n.bot.sent + n.bot.failed;
            const pct = n.bot.total ? Math.min(100, Math.round((done / n.bot.total) * 100)) : 0;
            return (
              <button key={n.id} className="card amsg pressable" onClick={() => push('notification', { id: n.id })}>
                <span className="amsg__top">
                  <KindChip kind={n.kind} />
                  {n.mode === 'forward' && <span className="badge">↪️ {t('Forward')}</span>}
                  {!n.inApp && <span className="badge">🤖 {t('Faqat bot')}</span>}
                </span>
                <b className="amsg__title">{n.title}</b>
                {n.toBot && (
                  <span className="amsg__bar" aria-label={`${pct}%`}><span style={{ width: `${pct}%` }} /></span>
                )}
                <span className="amsg__stats">
                  {n.toBot && <>✅ {n.bot.sent} · ⛔ {n.bot.failed}</>}
                  {n.inApp && <> · 👁 {n.reads}</>}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty icon={<span style={{ fontSize: 30 }}>📭</span>} title={t('Hali xabar yuborilmagan')} />
      )}
    </>
  );
}

// ===================== 🔌 API va limitlar =====================
const usd = (n) => `$${(Number(n) || 0).toFixed(n >= 100 ? 0 : 2)}`;

/** Limit o'lchagichi: qancha ishlatilgan / jami. Rang — qolgan qismga qarab. */
function Meter({ used, max, label, caption }) {
  const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
  const tone = pct >= 90 ? 'red' : pct >= 70 ? 'orange' : 'green';
  return (
    <div className="meter">
      <div className="meter__top">
        <span>{label}</span>
        <b>{caption}</b>
      </div>
      <span className={`meter__track meter__track--${tone}`} role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={used} aria-label={label}>
        <span style={{ width: `${pct}%` }} />
      </span>
    </div>
  );
}

function ApiStatus({ enabled, state, limited }) {
  if (!enabled) return <span className="badge">⚪ {t('Ulanmagan')}</span>;
  if (state?.error) return <span className="badge badge--bad">❗ {t('Xato')}</span>;
  if (limited) return <span className="badge badge--warn">⛔ {t('Limit tugagan')}</span>;
  return <span className="badge badge--ok">✅ {t('Ishlayapti')}</span>;
}

function ApiCard({ icon, title, sub, status, children }) {
  return (
    <section className="card api-card">
      <div className="api-card__head">
        <span className="api-card__icon" aria-hidden="true">{icon}</span>
        <span className="api-card__title">
          <b>{title}</b>
          <small>{sub}</small>
        </span>
        {status}
      </div>
      {children}
    </section>
  );
}

function CreditForm({ current, onSaved }) {
  const { toast } = useApp();
  const [open, setOpen] = useState(!current);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const amount = Number(value.replace(',', '.').replace(/[^\d.]/g, ''));
    if (!value.trim() || !Number.isFinite(amount)) return toast(t("Summani dollarda to'g'ri kiriting."), 'error');
    setBusy(true);
    try {
      await api('/admin/apis/credit', { method: 'POST', body: { amount } });
      haptic('success');
      toast(t('Balans saqlandi') + ' ✅');
      setValue('');
      setOpen(false);
      onSaved();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };
  if (!open) {
    return (
      <button className="btn btn--soft btn--sm mt-12" onClick={() => setOpen(true)}>💰 {t('Balansni yangilash')}</button>
    );
  }
  return (
    <div className="api-credit">
      <p className="card__hint">{t("Claude hisobingizdagi hozirgi balansni kiriting (platform.claude.com → Billing). Shundan boshlab bot sarfni ayirib, qancha qolganini ko'rsatadi.")}</p>
      <div className="auser__row">
        <input className="field" inputMode="decimal" placeholder={t('Masalan: 50')} value={value}
          onChange={(e) => setValue(e.target.value.replace(/[^\d.,]/g, ''))} onKeyDown={(e) => e.key === 'Enter' && save()} />
        <button className="btn btn--primary btn--sm" disabled={busy} onClick={save}>{t('Saqlash')}</button>
      </div>
    </div>
  );
}

function Apis() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => {
    api('/admin/apis').then((d) => { setData(d); setFailed(false); }).catch(() => setFailed(true));
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 30_000); // ochiq turganda yangilanib turadi
    return () => clearInterval(timer);
  }, [load]);

  if (failed && !data) return <Empty icon={<span style={{ fontSize: 30 }}>⚠️</span>} title={t("Ma'lumotni olib bo'lmadi")} />;
  if (!data) return <Skeleton height={150} count={3} />;
  const { claude: c, cloudflare: cf, gemini: gm } = data;
  const b = c.balance;
  const cfLimited = Boolean(cf.state?.limit_until);
  const cfLeft = Math.max(0, cf.freeLimit - cf.images);

  return (
    <>
      <ApiCard icon="🧠" title="Claude" sub={t('Matn yozish (taqdimot, referat, diplom)')}
        status={<ApiStatus enabled={c.enabled} state={c.state} />}>
        {c.state?.error && <div className="note note--warn">❗ {t(c.state.error)}</div>}
        {b ? (
          <div className="api-balance">
            <span className="api-balance__label">{t('Taxminiy qoldiq')}</span>
            <b className={`api-balance__value ${b.left < Math.max(5, c.perDay * 3) ? 'api-balance__value--low' : ''}`}>{usd(b.left)}</b>
            <span className="api-balance__sub">
              {b.days != null ? t('~{n} kunga yetadi', { n: Math.max(0, Math.round(b.days)) }) : t('sarf hali kam')}
              {' · '}{t('{amount} dan {spent} sarflandi', { amount: usd(b.amount), spent: usd(b.spent) })}
            </span>
            <Meter used={b.spent} max={b.amount} label={t('Balansdan ishlatildi')} caption={`${b.amount > 0 ? Math.round((b.spent / b.amount) * 100) : 0}%`} />
          </div>
        ) : (
          <div className="note note--info">💰 {t("Balans kiritilmagan — qancha qolganini ko'rish uchun hozirgi balansni kiriting.")}</div>
        )}
        <CreditForm current={b} onSaved={load} />
        {c.budget > 0 && (
          <Meter used={c.today.cost} max={c.budget} label={t('Bugungi kunlik chegara')}
            caption={t('{used} / {max} · qoldi {left}', { used: usd(c.today.cost), max: usd(c.budget), left: usd(c.budgetLeft) })} />
        )}
        <div className="api-facts">
          <span><small>{t('Bugun')}</small><b>{usd(c.today.cost)}</b><em>{t('{n} so\'rov', { n: c.today.n })}</em></span>
          <span><small>{t('7 kun')}</small><b>{usd(c.week.cost)}</b><em>{t('kuniga ~{v}', { v: usd(c.perDay) })}</em></span>
          <span><small>{t('Jami')}</small><b>{usd(c.total.cost)}</b><em>{t('{n} so\'rov', { n: c.total.n })}</em></span>
        </div>
        {c.rateLimited > 0 && <p className="card__hint mt-12">⏳ {t('Bugun tezlik limitiga {n} marta urildi — so\'rovlar kutib qayta yuborildi.', { n: c.rateLimited })}</p>}
      </ApiCard>
      <BarChart title={t('Claude xarajati · 14 kun')} total={usd(c.daily.reduce((s, d) => s + d.n, 0))} data={c.daily} format={usd} floor={0.01} />

      <ApiCard icon="🎨" title="Cloudflare FLUX" sub={t('AI rasm chizish (mos foto topilmasa)')}
        status={<ApiStatus enabled={cf.enabled} state={cf.state} limited={cfLimited} />}>
        {cf.enabled ? (
          <>
            <Meter used={cf.images} max={cf.freeLimit} label={t('Bugungi bepul limit (UTC)')}
              caption={t('{used} / ~{max} rasm · qoldi ~{left}', { used: cf.images, max: cf.freeLimit, left: cfLeft })} />
            {cfLimited && <p className="card__hint mt-12">⛔ {t("Bepul limit tugadi — UTC 00:00 da tiklanadi. Shu paytgacha faqat foto bazalari ishlatiladi.")}</p>}
            {cf.state?.error && <div className="note note--warn">❗ {t(cf.state.error)}</div>}
          </>
        ) : (
          <p className="card__hint">{t("Ulanmagan: .env ga CLOUDFLARE_ACCOUNT_ID va CLOUDFLARE_API_TOKEN qo'shing.")}</p>
        )}
      </ApiCard>

      {gm.enabled && (
        <ApiCard icon="🍌" title="Gemini" sub={t('AI rasm (pullik)')} status={<ApiStatus enabled state={gm.state} />}>
          <div className="api-facts">
            <span><small>{t('Bugun')}</small><b>{gm.images}</b><em>{t('rasm')}</em></span>
            <span><small>{t('Xatolar')}</small><b>{gm.errors}</b><em>{t('bugun')}</em></span>
          </div>
        </ApiCard>
      )}

      <ApiCard icon="🖼" title={t('Foto bazalari')} sub={t('Slayd va referat rasmlari')}>
        <div className="api-sources">
          {[['pexels', 'Pexels'], ['pixabay', 'Pixabay'], ['wikimedia', 'Wikimedia']].map(([key, name]) => {
            const s = data[key];
            const rate = s.state?.remaining != null && s.state?.limit ? `${s.state.remaining}/${s.state.limit}` : null;
            return (
              <div key={key} className={`api-source ${s.enabled ? '' : 'api-source--off'}`}>
                <b>{name}</b>
                <span>{s.enabled ? t('{n} so\'rov bugun', { n: s.calls }) : t('Ulanmagan')}{s.errors ? ` · ${t('{n} xato', { n: s.errors })}` : ''}</span>
                {rate && <small>{t('Daqiqalik limit: {r} qolgan', { r: rate })}</small>}
                <ApiStatus enabled={s.enabled} state={s.state} />
              </div>
            );
          })}
        </div>
      </ApiCard>
      <p className="card__hint api-foot">ℹ️ {t("Claude qoldig'i — bot hisoblagan taxminiy summa (har bir so'rov narxi bo'yicha). Aniq qoldiq: platform.claude.com → Billing. Hisobni to'ldirganingizda yangi balansni shu yerga kiriting.")}</p>
    </>
  );
}

// ===================== Ekran =====================
export default function Admin() {
  const { boot, openAuth } = useApp();
  const perms = boot.adminPerms ?? [];
  // Faqat huquqi bor bo'limlar; «👑 Adminlar» — faqat bot egasiga
  const tabs = [...TABS.filter(([, , , perm]) => perms.includes(perm)), ...(boot.isOwner ? [['admins', '👑', 'Adminlar']] : [])];
  const [tab, setTab] = useState(() => tabs[0]?.[0] ?? 'none');
  const [overview, setOverview] = useState(null);

  const loadOverview = useCallback(() => {
    api('/admin/overview').then(setOverview).catch(() => {});
  }, []);
  useEffect(() => {
    if (boot.isAdmin) loadOverview();
  }, [boot.isAdmin, loadOverview]);

  const pending = overview?.money.pending ?? 0;
  const go = (key) => { haptic('select'); setTab(key); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  // Brauzerning uz-UZ formati ishonchsiz («M11 6») — o'z formatlovchimiz (mahalliy sana)
  const today = useMemo(() => {
    const n = new Date();
    return dayLabel(`${n.getFullYear()}-${n.getMonth() + 1}-${n.getDate()}`);
  }, []);

  if (!boot.isAdmin) {
    return (
      <main className="page">
        <TopBar title={t('Admin panel')} />
        <Empty icon={<span style={{ fontSize: 30 }}>🔒</span>} title={t('Faqat admin uchun')}
          text={t('Admin telefon raqami va paroli bilan kiring.')}>
          <button className="btn btn--primary btn--sm mt-12" onClick={() => openAuth({ view: 'login' })}>{t('Kirish')}</button>
        </Empty>
      </main>
    );
  }

  return (
    <main className="page admin">
      <TopBar title={t('Admin panel')} right={<span className="badge">🛠 {today}</span>} />

      <section className="admin-hero">
        <div className="admin-hero__glow" aria-hidden="true" />
        <span className="admin-hero__hello">👋 {t('Salom, {name}!', { name: boot.user.firstName || 'Admin' })}</span>
        {perms.includes('stats') && (
          <div className="admin-hero__kpis">
            <div><b>{overview?.users ? overview.users.total : '…'}</b><span>{t('foydalanuvchi')}</span></div>
            <div><b>{overview?.users ? `+${overview.users.today}` : '…'}</b><span>{t('bugun')}</span></div>
            <div><b>{overview?.users ? compact(overview.money.today) : '…'}</b><span>{t("bugungi tushum, so'm")}</span></div>
          </div>
        )}
        {!boot.isOwner && (
          <span className="admin-hero__perms">🔑 {t('Huquqlaringiz')}: {perms.length ? perms.map((p) => t(PERM_LABELS[p])).join(' · ') : '—'}</span>
        )}
        {pending > 0 && perms.includes('payments') && (
          <button className="admin-hero__alert pressable" onClick={() => go('payments')}>
            ⏳ {t("{n} ta to'lov tekshiruvni kutmoqda", { n: pending })} <ChevronRight size={16} />
          </button>
        )}
      </section>

      <div className="admin-tabs" role="tablist">
        {tabs.map(([key, icon, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={`admin-tab ${tab === key ? 'admin-tab--on' : ''}`} onClick={() => go(key)}>
            <span aria-hidden="true">{icon}</span> {t(label)}
            {key === 'payments' && pending > 0 && <span className="admin-tab__badge">{badgeText(pending)}</span>}
          </button>
        ))}
      </div>

      <div className="admin-body" key={tab}>
        {tabs.length === 0 && (
          <Empty icon={<span style={{ fontSize: 30 }}>🔒</span>} title={t("Sizga hali huquq berilmagan")}
            text={t("Bot egasi sizga kerakli huquqlarni bergach, bo'limlar shu yerda paydo bo'ladi.")} />
        )}
        {tab === 'overview' && <Overview data={overview} go={go} />}
        {tab === 'users' && <Users />}
        {tab === 'payments' && <Payments onChanged={loadOverview} />}
        {tab === 'messages' && <Messages />}
        {tab === 'apis' && <Apis />}
        {tab === 'admins' && boot.isOwner && <Admins />}
      </div>
    </main>
  );
}
