import { useApp } from '../app/AppContext.jsx';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';
import { GridIcon, HomeIcon, PlusIcon, ProjectsIcon, UserIcon } from './Icons.jsx';

const TABS = [
  { key: 'home', label: 'Bosh sahifa', Icon: HomeIcon },
  { key: 'templates', label: 'Shablonlar', Icon: GridIcon },
  null, // o'rtadagi «+» tugmasi
  { key: 'saved', label: 'Loyihalar', Icon: ProjectsIcon },
  { key: 'profile', label: 'Profil', Icon: UserIcon },
];

export default function BottomNav() {
  const { tab, setTab, openSheet } = useApp();
  const index = TABS.findIndex((item) => item?.key === tab);
  const ActiveIcon = TABS[index]?.Icon;
  return (
    // --ni — faol tab o'rni: menyudagi o'yiq va ko'tarilgan doira shu bilan birga siljiydi
    <nav className={`nav ${index >= 0 ? 'nav--notch' : ''}`} style={{ '--ni': Math.max(index, 0) }} aria-label={t("Asosiy menyu")}>
      {ActiveIcon && (
        <span className="nav__bubble" aria-hidden="true">
          {/* key — har o'tishda sakrash animatsiyasi qaytadan boshlanadi */}
          <span key={tab} className="nav__ball">
            <ActiveIcon size={26} active />
          </span>
        </span>
      )}
      {TABS.map((item) =>
        item ? (
          <button
            key={item.key}
            className={`nav__item ${tab === item.key ? 'nav__item--active' : ''}`}
            onClick={() => {
              if (tab !== item.key) haptic('select');
              setTab(item.key);
            }}
            aria-current={tab === item.key ? 'page' : undefined}
          >
            <span className="nav__icon">
              <item.Icon size={26} active={tab === item.key} />
            </span>
            {t(item.label)}
          </button>
        ) : (
          <button
            key="fab"
            className="nav__fab pressable"
            aria-label={t('Yangi buyurtma')}
            onClick={() => {
              haptic('medium');
              openSheet('create');
            }}
          >
            <PlusIcon size={30} />
          </button>
        ),
      )}
    </nav>
  );
}
