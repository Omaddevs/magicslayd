import { t } from '../lib/i18n.js';
import { kindOf, timeAgo } from '../lib/notify.js';


/** Xabar turi belgisi — rangli doira ichida emoji. */
export function KindBubble({ kind, size = 46 }) {
  const meta = kindOf(kind);
  return (
    <span className={`notif-kind notif-kind--${meta.tone}`} style={{ width: size, height: size, fontSize: size * 0.46 }} aria-hidden="true">
      {meta.icon}
    </span>
  );
}

export function KindChip({ kind }) {
  const meta = kindOf(kind);
  return (
    <span className={`notif-chip notif-chip--${meta.tone}`}>
      {meta.icon} {t(meta.label)}
    </span>
  );
}

/** Ro'yxatdagi bitta bildirishnoma. O'qilmagan — rangli fon, chap chiziq va nuqta bilan. */
export default function NotifCard({ item, onOpen, preview = false }) {
  const Tag = onOpen ? 'button' : 'div';
  return (
    <Tag
      type={onOpen ? 'button' : undefined}
      className={`notif ${item.read ? '' : 'notif--unread'} ${onOpen ? 'pressable' : ''} ${preview ? 'notif--preview' : ''}`}
      onClick={onOpen}
      aria-label={onOpen ? `${item.read ? '' : `${t("O'qilmagan")}: `}${item.title}` : undefined}
    >
      <KindBubble kind={item.kind} />
      <span className="notif__body">
        <b className="notif__title">{item.title || t('Sarlavha')}</b>
        <span className="notif__text">{item.preview || item.body || t('Xabar matni shu yerda chiqadi…')}</span>
        <span className="notif__meta">
          <span className={`notif__kind notif__kind--${kindOf(item.kind).tone}`}>{t(kindOf(item.kind).label)}</span>
          <span aria-hidden="true">·</span>
          <span className="notif__time">{preview ? t('hozirgina') : timeAgo(item.createdAt)}</span>
        </span>
      </span>
      {item.image && <img className="notif__thumb" src={item.image} alt="" loading="lazy" />}
      {!item.read && <span className="notif__dot" aria-hidden="true" />}
    </Tag>
  );
}
