import { useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { apiUpload } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';
import { ChevronRight } from './Icons.jsx';

const MAX_MB = 25;
const ACCEPT = '.pptx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation';

/** O'z taqdimotini (PPTX yoki PDF) yuklab, muharrirda tahrirlash. */
export default function ImportCard({ onDone }) {
  const { push, toast, requireAuth } = useApp();
  const input = useRef();
  const [busy, setBusy] = useState(false);

  async function onFile(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!/\.(pptx|pdf)$/i.test(file.name)) {
      toast(file.name.toLowerCase().endsWith('.ppt')
        ? t("Eski .ppt formati. PowerPoint'da «.pptx» qilib saqlab, qayta yuklang.")
        : t('Faqat PPTX yoki PDF fayl yuklash mumkin.'), 'error');
      return;
    }
    if (file.size > MAX_MB * 1048576) {
      toast(t('Fayl {n} MB dan oshmasin.', { n: MAX_MB }), 'error');
      return;
    }
    setBusy(true);
    haptic('medium');
    try {
      const { documentId } = await apiUpload('/imports', file, { 'X-File-Name': encodeURIComponent(file.name) });
      haptic('success');
      onDone?.();
      push('editor', { docId: documentId });
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={onFile} />
      <button
        className="import-card pressable"
        onClick={() => requireAuth(() => input.current?.click(), t('Faylni tahrirlash uchun hisobingizga kiring'))}
        disabled={busy}
      >
        <span className="import-card__icon" aria-hidden="true">{busy ? '⏳' : '📤'}</span>
        <span className="import-card__text">
          <b>{busy ? t('Yuklanmoqda…') : t("O'z faylingizni tahrirlang")}</b>
          <small>{t("PPTX yoki PDF yuklang — matn va rasmlar muharrirga o'tadi")}</small>
        </span>
        <ChevronRight size={20} />
      </button>
    </>
  );
}
