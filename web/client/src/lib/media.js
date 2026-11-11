import { t } from './i18n.js';

const MAX_SIDE = 1920;

/** Rasmni JPEG ga aylantirib kichraytiradi: telefondagi 5–10 MB rasm ~300–600 KB bo'ladi.
 *  PNG/HEIC/WebP ham JPEG bo'ladi (PowerPoint WebP ni qo'llamaydi). */
export async function prepareImage(file) {
  const bitmap = await loadImage(file);
  const ratio = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * ratio);
  canvas.height = Math.round(bitmap.height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; // shaffof PNG qora bo'lib qolmasin
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error(t("Rasmni o'qib bo'lmadi.")))), 'image/jpeg', 0.86);
  });
}

async function loadImage(file) {
  if (window.createImageBitmap) {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' });
    } catch {
      // eski Safari — pastdagi usul
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    return image;
  } catch {
    throw new Error(t("Bu rasm formatini o'qib bo'lmadi. JPG yoki PNG tanlang."));
  } finally {
    URL.revokeObjectURL(url);
  }
}

export const VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/x-m4v'];
