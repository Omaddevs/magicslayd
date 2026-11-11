import { t } from './i18n.js';

// Xizmatlar — bosh sahifadagi kartalar va buyurtma sahifalari shu ro'yxatdan quriladi
export const SERVICES = {
  pres: {
    title: 'Presentatsiya',
    sub: 'Tayyor slaydlar',
    color: 'purple',
    unit: 'slayd',
    label: 'Taqdimot',
    about: 'Muqova, mundarija, reja, slaydlar va xulosa — mavzuga mos rasmlar bilan',
  },
  referat: {
    title: 'Referat',
    sub: 'Turli mavzularda',
    color: 'green',
    unit: 'bet',
    label: 'Referat',
    about: 'Muqova → mundarija → kirish → boblar → xulosa → adabiyotlar',
  },
  kurs: {
    title: 'Kurs ishi',
    sub: 'Namunaviy ishlar',
    color: 'orange',
    unit: 'bet',
    label: 'Kurs ishi',
    about: "Nazariy va tahliliy boblar, xulosa va adabiyotlar ro'yxati bilan",
  },
  mustaqil: {
    title: 'Mustaqil ish',
    sub: 'Topshiriq va yechimlar',
    color: 'blue',
    unit: 'bet',
    label: 'Mustaqil ish',
    about: 'Mavzu bo\'yicha to\'liq yozilgan mustaqil ish — titul bilan',
  },
  diplom: {
    title: 'Diplom ishi',
    sub: 'Bitiruv malakaviy ishi',
    color: 'purple',
    unit: 'bet',
    label: 'Diplom ishi',
    about: "Reja, kirish, boblar, xulosa va haqiqiy manbalar — bosqichma-bosqich",
  },
  diss: {
    title: 'Dissertatsiya',
    sub: 'Magistrlik, PhD, DSc',
    color: 'blue',
    unit: 'bet',
    label: 'Dissertatsiya',
    about: 'Reja, kirish, boblar, grafiklar, haqiqiy manbalar va sifat nazorati',
  },
  maqola: {
    title: 'Maqola',
    sub: '5 turdagi maqola',
    color: 'green',
    unit: "so'z",
    label: 'Maqola',
    about: 'Oddiy, ilmiy, tahliliy, publitsistik va sharh maqolalari — tahrirlash, Word va PDF',
  },
  shablon: {
    title: 'Shablonlar',
    sub: 'Word, PPT, PDF',
    color: 'pink',
    unit: 'bet',
    label: 'Shablon',
  },
};

export const KIND_LABEL = (kind) => t(SERVICES[kind]?.label ?? 'Hujjat');
export const unitOf = (kind) => t(SERVICES[kind]?.unit ?? 'bet');

/** Fayl turi: materiallarda file_type bor, bot hujjatlarida turi bo'yicha aniqlanadi. */
export const fileTypeOf = (item) => item.file_type || (item.kind === 'pres' ? 'pptx' : 'docx');

/** Buyurtma hajmi: «15 slayd», «10 bet» yoki «~1250 so'z» (maqola). */
export const orderSize = (kind, params) => {
  if (kind === 'pres') return `${params.slides ?? ''} ${t('slayd')}`;
  if (kind === 'maqola') return `~${params.words ?? ''} ${t("so'z")}`;
  return `${params.pages ?? ''} ${t('bet')}`;
};

export const PROGRESS_STEPS = {
  pres: [
    'Mavzu tahlil qilinmoqda',
    'Reja tuzilmoqda',
    'Slaydlar matni yozilmoqda',
    'Mavzuga mos rasmlar tanlanmoqda',
    "Ma'lumotlar tekshirilmoqda",
    'Dizayn chizilmoqda',
  ],
  article: [
    'Mavzu tahlil qilinmoqda',
    'Maqola tuzilmasi rejalashtirilmoqda',
    "Bo'limlar yozilmoqda",
    'Haqiqiy manbalar va rasmlar tanlanmoqda',
    'Sifat tekshirilmoqda',
    'Hujjat tayyorlanmoqda',
  ],
  doc: [
    'Mavzu tahlil qilinmoqda',
    'Ish rejasi tuzilmoqda',
    'Kirish va boblar yozilmoqda',
    'Adabiyotlar va rasmlar tanlanmoqda',
    'Xulosa yozilmoqda',
    'Fayl tayyorlanmoqda',
  ],
};
