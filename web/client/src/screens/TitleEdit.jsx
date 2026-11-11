import { useEffect, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import { Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { haptic } from '../lib/telegram.js';

// Bot bilan bir xil maydonlar (keyboards.py → TITLE_FIELDS)
const FIELDS = [
  ['university', "O'quv muassasasi", 'Toshkent davlat iqtisodiyot universiteti'],
  ['faculty', 'Fakultet / kafedra', 'Iqtisodiyot fakulteti, Moliya kafedrasi'],
  ['subject', 'Fan nomi', 'Makroiqtisodiyot'],
  ['student', 'Talaba (F.I.Sh.)', 'Aliyev Vali Karimovich'],
  ['group', 'Guruh / sinf', 'IQ-21-01'],
  ['teacher', "O'qituvchi", 'i.f.n., dots. Karimov A.B.'],
  ['city', 'Shahar', 'Toshkent'],
];
const MAX = 150;

export default function TitleEdit() {
  const { pop, toast } = useApp();
  const [title, setTitle] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api('/title')
      .then((data) => setTitle(data.title))
      .catch(() => setTitle({}));
  }, []);

  async function save() {
    setSaving(true);
    try {
      await api('/title', { method: 'PUT', body: title });
      haptic('success');
      toast(t('Saqlandi') + ' ✅');
      pop();
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="page" style={{ paddingBottom: 'calc(110px + var(--safe-bottom))' }}>
      <TopBar title={t("Titul ma'lumotlari")} />
      <div className="note note--info" style={{ marginTop: 0 }}>
        {t("Referat, mustaqil ish va kurs ishining muqovasiga shu ma'lumotlar yoziladi. Botdagi «👤 Titul ma'lumotlari» bilan bir xil.")}
      </div>
      {title === null ? (
        <div className="mt-16">
          <Skeleton height={60} count={5} />
        </div>
      ) : (
        <section className="card mt-12">
          {FIELDS.map(([key, label, example]) => (
            <div key={key}>
              <label className="field-label" htmlFor={`t-${key}`}>
                {t(label)}
              </label>
              <input
                id={`t-${key}`}
                className="field"
                maxLength={MAX}
                placeholder={`${t('Masalan:')} ${example}`}
                value={title[key] ?? ''}
                onChange={(e) => setTitle((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            </div>
          ))}
          <button className="btn btn--soft mt-16" onClick={() => setTitle({})}>
            {t('Hammasini tozalash')}
          </button>
        </section>
      )}
      <div className="bottom-bar">
        <button className="btn btn--primary" onClick={save} disabled={saving || title === null}>
          {saving ? t('Saqlanmoqda...') : t('Saqlash')}
        </button>
      </div>
    </main>
  );
}
