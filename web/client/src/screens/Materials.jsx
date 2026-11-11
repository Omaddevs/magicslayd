import { useEffect, useState } from 'react';

import FileItem from '../components/FileItem.jsx';
import { FolderIcon } from '../components/Icons.jsx';
import { Empty, Skeleton, TopBar } from '../components/ui.jsx';
import { api } from '../lib/api.js';
import { t } from '../lib/i18n.js';
import { SERVICES } from '../lib/services.js';

const FILTERS = [['', 'Hammasi'], ...['pres', 'referat', 'kurs', 'mustaqil', 'shablon'].map((k) => [k, SERVICES[k].label])];

/** «Barchasini ko'rish» — ommabop materiallar, turi bo'yicha filtr bilan. */
export default function Materials({ kind: initialKind = '', title = 'Ommabop materiallar' }) {
  const [kind, setKind] = useState(initialKind);
  const [materials, setMaterials] = useState(null);

  useEffect(() => {
    setMaterials(null);
    api(`/materials?limit=50${kind ? `&kind=${kind}` : ''}`)
      .then((data) => setMaterials(data.materials))
      .catch(() => setMaterials([]));
  }, [kind]);

  return (
    <main className="page">
      <TopBar title={t(title)} />
      <div className="chips chips--scroll">
        {FILTERS.map(([key, label]) => (
          <button key={key} className={`chip chip--pill ${kind === key ? 'chip--active' : ''}`} onClick={() => setKind(key)}>
            {t(label)}
          </button>
        ))}
      </div>
      <div className="mt-12">
        {materials === null ? (
          <Skeleton />
        ) : materials.length ? (
          <div className="list">
            {materials.map((item) => (
              <FileItem key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <Empty icon={<FolderIcon size={32} />} title={t("Bu bo'limda hozircha material yo'q")} text={t("Tez orada qo'shiladi.")} />
        )}
      </div>
    </main>
  );
}
