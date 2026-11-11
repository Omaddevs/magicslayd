import { useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { api } from '../lib/api.js';
import { downloadArticle, sendArticle } from '../lib/article.js';
import { downloadFile } from '../lib/download.js';
import { shortDate } from '../lib/format.js';
import { KIND_LABEL, fileTypeOf, unitOf } from '../lib/services.js';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';
import { FileIcon } from './Art.jsx';
import { BookmarkIcon, DownloadIcon, EditIcon, SendIcon } from './Icons.jsx';

/** Material (ommabop) yoki botda yaratilgan hujjat.
 *  ⬇️ — saytdan yuklab olish, ✈️ — Telegram chatga yuborish. */
export default function FileItem({ item, source = 'material', bookmarkable = true, sendable, onBookmark }) {
  const { toast, push, requireAuth } = useApp();
  // Muharrirda ochiladigan taqdimot yoki ish (loyihasi saqlangan)
  // Maqola loyihasi bo'lmasa (juda eski) — faqat chatdagi fayl beriladi, muharrir ochilmaydi
  const editable = source === 'document' && item.editable && !(item.kind === 'maqola' && !item.ready);
  const canSend = sendable ?? source === 'document';
  const [busy, setBusy] = useState(null);
  const [saved, setSaved] = useState(Boolean(item.saved));
  const path = source === 'material' ? 'materials' : 'documents';
  // Maqola: fayl doim muharrirdagi OXIRGI versiyadan yasaladi (chatdagi birinchi Word emas)
  const article = editable && item.kind === 'maqola';

  const meta =
    source === 'material'
      ? `${KIND_LABEL(item.kind)} · ${item.pages} ${unitOf(item.kind)}`
      : `${KIND_LABEL(item.kind)} · ${shortDate(item.created_at)}`;

  async function download() {
    setBusy('download');
    try {
      if (article) await downloadArticle(item.id, 'docx');
      else await downloadFile(path, item.id);
      toast(t('Yuklab olinmoqda') + ' ⬇️');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  async function send() {
    setBusy('send');
    haptic('medium');
    try {
      if (article) await sendArticle(item.id, 'docx');
      else await api(`/${path}/${item.id}/send`, { method: 'POST' });
      haptic('success');
      toast(t('Fayl Telegram chatga yuborildi') + ' 📩');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  async function bookmark() {
    // Saqlash — hisob talab qiladi; kirgach avtomatik saqlanadi
    if (!requireAuth(bookmark, t('Materialni saqlash uchun hisobingizga kiring'))) return;
    haptic('select');
    try {
      const result = await api(`/materials/${item.id}/bookmark`, { method: 'POST' });
      setSaved(result.saved);
      toast(result.saved ? t("Saqlanganlarga qo'shildi") : t('Saqlanganlardan olib tashlandi'));
      onBookmark?.(item, result.saved);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  return (
    <div className="item">
      <FileIcon type={fileTypeOf(item)} />
      <div
        className={`item__body ${editable ? 'item__body--link' : ''}`}
        onClick={editable ? () => {
          if (item.kind === 'diplom') push('diploma', { documentId: item.id });
          else if (item.kind === 'diss') push('dissertation', { documentId: item.id });
          else if (item.kind === 'maqola') push('article', { docId: item.id });
          else push(item.kind === 'pres' ? 'editor' : 'paper', { docId: item.id });
        } : undefined}
        role={editable ? 'button' : undefined}
      >
        <div className="item__title">{item.title}</div>
        <div className="item__meta">
          {meta}
          {editable && (
            <span className="edit-tag">
              · <EditIcon size={13} /> {t('Ochish')}
            </span>
          )}
        </div>
      </div>
      <div className="item__actions">
        {source === 'material' && bookmarkable && (
          <button
            className={`icon-btn icon-btn--ghost ${saved ? 'icon-btn--active' : ''}`}
            onClick={bookmark}
            aria-label={saved ? t('Saqlanganlardan olib tashlash') : t('Saqlash')}
          >
            <BookmarkIcon size={22} active={saved} />
          </button>
        )}
        {canSend && (
          <button className="icon-btn icon-btn--ghost pressable" onClick={send} disabled={busy !== null} aria-label={t('Telegram chatga yuborish')}>
            <SendIcon size={21} />
          </button>
        )}
        <button className="icon-btn pressable" onClick={download} disabled={busy !== null} aria-label={t('Yuklab olish')}>
          <DownloadIcon size={22} />
        </button>
      </div>
    </div>
  );
}
