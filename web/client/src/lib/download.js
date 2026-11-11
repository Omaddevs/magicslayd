import { api } from './api.js';
import { haptic, saveFile } from './telegram.js';

/** Material yoki o'z hujjatini saytdan yuklab oladi. source: 'materials' | 'documents' */
export async function downloadFile(source, id) {
  haptic('medium');
  const { url, fileName } = await api(`/${source}/${id}/link`, { method: 'POST' });
  saveFile(url, fileName);
  return fileName;
}
