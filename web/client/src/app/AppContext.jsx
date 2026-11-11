import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { setSession } from '../lib/session.js';
import { haptic, openBotChat } from '../lib/telegram.js';

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

// Ro'yxatdan o'tmagan foydalanuvchi bu sahifalarni ochmoqchi bo'lsa — avval kirish oynasi chiqadi.
// Ko'rish (bosh sahifa, dizaynlar, materiallar, qidiruv) — hamma uchun ochiq
const GATED = {
  order: 'Ish buyurtma qilish uchun hisobingizga kiring',
  editor: 'Loyihani tahrirlash uchun hisobingizga kiring',
  paper: 'Loyihani tahrirlash uchun hisobingizga kiring',
  diploma: 'Diplom ishini boshlash uchun hisobingizga kiring',
  dissertation: 'Dissertatsiyani boshlash uchun hisobingizga kiring',
  ai: 'AI yordamchidan foydalanish uchun hisobingizga kiring',
  title: "Titul ma'lumotlarini saqlash uchun hisobingizga kiring",
  topup: "Hisobni to'ldirish uchun hisobingizga kiring",
  progress: 'Buyurtmani kuzatish uchun hisobingizga kiring',
};

export function AppProvider({ boot: initialBoot, children }) {
  const [boot, setBootState] = useState(initialBoot);
  const [tab, setTabState] = useState('home');
  // Ichki sahifalar steki: [{ name, props, scroll }]
  const [stack, setStack] = useState([]);
  const [sheet, setSheet] = useState(null);
  const [toastState, setToast] = useState(null);
  const toastTimer = useRef();
  const scrolls = useRef({});
  // Callback'lar ichida eng yangi holat (kirgandan so'ng darhol bajariladigan amal uchun)
  const bootRef = useRef(boot);
  bootRef.current = boot;

  const setBoot = useCallback((patch) => setBootState((prev) => ({ ...prev, ...patch })), []);

  const toast = useCallback((text, type = 'info') => {
    clearTimeout(toastTimer.current);
    setToast({ text, type, key: Date.now() });
    haptic(type === 'error' ? 'error' : 'light');
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  const restoreScroll = (y) => requestAnimationFrame(() => window.scrollTo(0, y ?? 0));

  const setTab = useCallback((next) => {
    setTabState((current) => {
      scrolls.current[current] = window.scrollY;
      restoreScroll(current === next ? 0 : scrolls.current[next]);
      return next;
    });
    setStack([]);
    haptic('select');
  }, []);

  /** Kirish oynasi. opts: { view: 'login'|'register'|'forgot'|'change', reason, then } */
  const openAuth = useCallback((opts = {}) => setSheet({ name: 'auth', props: opts }), []);

  /** Amal hisob talab qiladi: kirgan bo'lsa — darhol bajaradi, aks holda kirish oynasi (kirgach — bajariladi). */
  const requireAuth = useCallback((action, reason) => {
    if (bootRef.current.account) {
      action?.();
      return true;
    }
    haptic('warning');
    setSheet({ name: 'auth', props: { reason, then: action } });
    return false;
  }, []);

  const rawPush = useCallback((name, props = {}) => {
    setStack((prev) => [...prev, { name, props, scroll: window.scrollY }]);
    restoreScroll(0);
  }, []);

  const push = useCallback(
    (name, props = {}) => {
      if (GATED[name] && !bootRef.current.account) {
        requireAuth(() => rawPush(name, props), t(GATED[name]));
        return;
      }
      rawPush(name, props);
    },
    [rawPush, requireAuth],
  );

  // Server «avval kiring» desa (masalan eski ekranda qolgan tugma) — kirish oynasi ochiladi
  useEffect(() => {
    const onAuthRequired = () => setSheet((prev) => (prev?.name === 'auth' ? prev : { name: 'auth', props: {} }));
    window.addEventListener('slayd:auth-required', onAuthRequired);
    return () => window.removeEventListener('slayd:auth-required', onAuthRequired);
  }, []);

  // Sahifa chiqib ketishni to'xtatib turishi mumkin (muharrirda saqlanmagan o'zgarishlar)
  const leaveGuard = useRef(null);
  const setLeaveGuard = useCallback((fn) => {
    leaveGuard.current = fn;
  }, []);

  const pop = useCallback(async () => {
    if (leaveGuard.current && !(await leaveGuard.current())) return;
    leaveGuard.current = null;
    setStack((prev) => {
      if (!prev.length) return prev;
      restoreScroll(prev[prev.length - 1].scroll);
      return prev.slice(0, -1);
    });
  }, []);

  /** Joriy sahifani almashtiradi (masalan buyurtma → jarayon: orqaga bosilsa forma qaytmasin). */
  const replace = useCallback((name, props = {}) => {
    leaveGuard.current = null;
    setStack((prev) => [...prev.slice(0, -1), { name, props, scroll: prev[prev.length - 1]?.scroll ?? 0 }]);
    restoreScroll(0);
  }, []);

  const openSheet = useCallback((name, props = {}) => setSheet({ name, props }), []);
  const closeSheet = useCallback(() => setSheet(null), []);

  /** Bootstrap qayta olinadi (kirish / chiqishdan so'ng: user, balans, hisob). */
  const reload = useCallback(async () => {
    try {
      const next = await api('/bootstrap');
      bootRef.current = next;
      setBootState(next);
      return next;
    } catch (error) {
      // Oddiy brauzerda chiqildi — kirish sahifasi ko'rsatiladi
      if (error.status === 401) window.location.reload();
      throw error;
    }
  }, []);

  /** Kirish / ro'yxatdan o'tish muvaffaqiyatli bo'lganda (AuthSheet chaqiradi). */
  const signIn = useCallback(
    async (token) => {
      setSession(token);
      await reload();
    },
    [reload],
  );

  const signOut = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch {
      /* tarmoq xatosi — token baribir o'chiriladi */
    }
    setSession('');
    setSheet(null);
    setStack([]);
    setTabState('home');
    restoreScroll(0);
    await reload().catch(() => {});
    haptic('success');
    toast(t('Hisobdan chiqdingiz') + ' 👋');
  }, [reload, toast]);

  /** Qo'ng'iroqchadagi o'qilmagan bildirishnomalar soni. */
  const setUnread = useCallback((n) => setBoot({ unreadNotifications: Math.max(0, Number(n) || 0) }), [setBoot]);
  const refreshUnread = useCallback(async () => {
    try {
      const { unread } = await api('/notifications/unread-count');
      setUnread(unread);
    } catch {
      /* tarmoq xatosi — keyingi safar */
    }
  }, [setUnread]);

  // Yangi xabar kelsa raqam o'zi yangilansin: har daqiqada va ilovaga qaytilganda
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') refreshUnread();
    }, 60_000);
    const onVisible = () => document.visibilityState === 'visible' && refreshUnread();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refreshUnread]);

  const refreshBalance = useCallback(async () => {
    const { balance } = await api('/balance');
    setBoot({ balance });
    return balance;
  }, [setBoot]);

  /** Hisobni to'ldirish — ilova ichida: summa → karta → chek. */
  const topup = useCallback(
    (need = 0) => {
      setSheet(null);
      push('topup', { need: Math.max(0, need) });
    },
    [push],
  );

  /** Zaxira yo'l: to'lov bot chatida (botga «Hisobni to'ldirish» tugmali xabar keladi). */
  const topupViaBot = useCallback(
    async (need = 0) => {
      try {
        const { bot } = await api('/topup', { method: 'POST', body: { need } });
        haptic('success');
        toast(t("Botga to'lov xabari yuborildi") + ' 💳');
        setTimeout(() => openBotChat(bot), 600);
      } catch (error) {
        toast(error.message, 'error');
      }
    },
    [toast],
  );

  const authed = Boolean(boot.account);

  const value = useMemo(
    () => ({
      boot, setBoot, refreshBalance, tab, setTab, stack, push, pop, replace, setLeaveGuard,
      sheet, openSheet, closeSheet, toast, toastState, topup, topupViaBot,
      authed, openAuth, requireAuth, signIn, signOut, setUnread, refreshUnread,
    }),
    [boot, setBoot, refreshBalance, tab, setTab, stack, push, pop, replace, setLeaveGuard, sheet, openSheet, closeSheet,
      toast, toastState, topup, topupViaBot, authed, openAuth, requireAuth, signIn, signOut, setUnread, refreshUnread],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
