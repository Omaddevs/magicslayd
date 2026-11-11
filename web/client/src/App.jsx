import { useEffect, useRef } from 'react';

import { useApp } from './app/AppContext.jsx';
import BottomNav from './components/BottomNav.jsx';
import Sheets from './components/Sheets.jsx';
import { Toast } from './components/ui.jsx';
import { useLang } from './lib/i18n.js';
import { setBackButton, tg } from './lib/telegram.js';
import Admin from './screens/Admin.jsx';
import ArticleEditor from './screens/ArticleEditor.jsx';
import ArticleOrder from './screens/ArticleOrder.jsx';
import Assistant from './screens/Assistant.jsx';
import Broadcast from './screens/Broadcast.jsx';
import Diploma from './screens/Diploma.jsx';
import Dissertation from './screens/Dissertation.jsx';
import Editor from './screens/Editor.jsx';
import Home from './screens/Home.jsx';
import Materials from './screens/Materials.jsx';
import NotificationDetail from './screens/NotificationDetail.jsx';
import Notifications from './screens/Notifications.jsx';
import Order from './screens/Order.jsx';
import PaperEditor from './screens/PaperEditor.jsx';
import Profile from './screens/Profile.jsx';
import Progress from './screens/Progress.jsx';
import Saved from './screens/Saved.jsx';
import Search from './screens/Search.jsx';
import Templates from './screens/Templates.jsx';
import TitleEdit from './screens/TitleEdit.jsx';
import Topup from './screens/Topup.jsx';

const TABS = { home: Home, templates: Templates, saved: Saved, profile: Profile };
const SCREENS = {
  order: Order,
  'article-order': ArticleOrder,
  article: ArticleEditor,
  editor: Editor,
  paper: PaperEditor,
  diploma: Diploma,
  dissertation: Dissertation,
  search: Search,
  topup: Topup,
  progress: Progress,
  ai: Assistant,
  materials: Materials,
  templates: Templates,
  title: TitleEdit,
  notifications: Notifications,
  notification: NotificationDetail,
  broadcast: Broadcast,
  admin: Admin,
};

export default function App() {
  const { tab, setTab, stack, pop, sheet, closeSheet, boot, push, openAuth } = useApp();
  const top = stack[stack.length - 1];
  const lang = useLang();

  // Telegram «orqaga» tugmasi: sheet → ichki sahifa → bosh sahifa
  useEffect(() => {
    if (sheet) return setBackButton(closeSheet);
    if (top) return setBackButton(pop);
    if (tab !== 'home') return setBackButton(() => setTab('home'));
    return setBackButton(null);
  }, [sheet, top, tab, pop, closeSheet, setTab]);

  // Birinchi ochilishda: botdagi fayl ostidagi «✏️ Tahrirlash» tugmasi (?edit=<id> — taqdimot, ?paper=<id> — ish),
  // tayyorlanayotgan buyurtma jarayoniga qaytarish yoki to'g'ridan-to'g'ri havola
  // (/ai-yordamchi yoki t.me/<bot>?startapp=ai) — AI yordamchi sahifasi
  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current) return;
    resumed.current = true;
    const query = new URLSearchParams(window.location.search);
    const deckId = Number(query.get('edit'));
    const paperId = Number(query.get('paper'));
    const diplomaId = Number(query.get('diplom'));
    const diplomaDoc = Number(query.get('diplomdoc'));
    // Botdagi bildirishnoma ostidagi «📱 Ilovada o'qish» (?notif=<id> yoki startapp=notif_<id>)
    const notifId = Number(query.get('notif')) || Number(/^notif_(\d+)$/.exec(tg?.initDataUnsafe?.start_param || '')?.[1]);
    if (notifId > 0) push('notification', { id: notifId });
    // Botdagi «🌐 Web admin panel» (?admin=1): admin bo'lmasa ham ochiladi — sahifa o'zi kirishni so'raydi
    else if (query.get('admin') === '1') push('admin');
    else if (deckId > 0) push('editor', { docId: deckId });
    else if (paperId > 0) push('paper', { docId: paperId });
    else if (diplomaId > 0) push('diploma', { diplomaId });
    else if (diplomaDoc > 0) push('diploma', { documentId: diplomaDoc });
    else if (Number(query.get('diss')) > 0) push('dissertation', { dissId: Number(query.get('diss')) });
    else if (Number(query.get('article')) > 0) push('article', { docId: Number(query.get('article')) });
    else if (Number(query.get('dissdoc')) > 0) push('dissertation', { documentId: Number(query.get('dissdoc')) });
    else if (boot.activeOrder) push('progress', { orderId: boot.activeOrder.id, kind: boot.activeOrder.kind });
    else if (window.location.pathname === '/ai-yordamchi' || tg?.initDataUnsafe?.start_param === 'ai') push('ai');
    else if (tg?.initDataUnsafe?.start_param === 'login' && !boot.account) openAuth();
  }, [boot.activeOrder, boot.account, push, openAuth]);

  const Screen = top ? SCREENS[top.name] : TABS[tab];

  // key={lang} — til almashganda butun interfeys yangi tilda qayta chiziladi (ochiq sahifa va oyna saqlanadi)
  return (
    <div className="app" key={lang}>
      {/* key — bir xil turdagi sahifa qayta ochilganda (yoki kirish/chiqishdan so'ng) holati yangidan boshlansin */}
      <Screen key={top ? `${stack.length}-${top.name}` : `${tab}-${boot.account?.digits ?? 'guest'}`} {...(top?.props ?? { asTab: true })} />
      {!top && <BottomNav />}
      <Sheets />
      <Toast />
    </div>
  );
}
