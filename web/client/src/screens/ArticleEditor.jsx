import { useCallback, useEffect, useRef, useState } from 'react';

import { useApp } from '../app/AppContext.jsx';
import {
  CheckIcon, DownloadIcon, ImageIcon, PlusIcon, RefreshIcon, SendIcon, TrashIcon,
} from '../components/Icons.jsx';
import { Empty, Sheet, Skeleton, TopBar } from '../components/ui.jsx';
import { api, apiUpload } from '../lib/api.js';
import {
  TYPE_BY_KEY, blocksToHtml, downloadArticle, figureHtml, htmlToBlocks, sendArticle, wordCount,
} from '../lib/article.js';
import { t } from '../lib/i18n.js';
import { prepareImage } from '../lib/media.js';
import { confirmDialog, haptic, setClosingConfirmation } from '../lib/telegram.js';

const SAVE_DELAY = 1500;
const DRAFT_DELAY = 400;
const draftKey = (id) => `slayd-article-draft-${id}`;
const SIZES = [10, 12, 14, 16, 18, 24, 32];
const COLORS = ['#141414', '#5b6170', '#c62828', '#e65100', '#f9a825', '#2e7d32', '#00838f', '#1565c0', '#5e35b1', '#ad1457'];
const BLOCK_STYLES = [['P', 'Matn'], ['H1', 'H1'], ['H2', 'H2'], ['H3', 'H3']];
const STATUS = {
  saved: ['Saqlandi', 'ok'],
  dirty: ["O'zgarishlar bor", 'wait'],
  saving: ['Saqlanmoqda…', 'wait'],
  offline: ['Oflayn — qurilmada saqlandi', 'warn'],
  error: ['Saqlanmadi — qayta urinish', 'bad'],
};
const NOTICES = {
  no_sources: "Bu mavzu bo'yicha ishonchli ilmiy manba topilmadi — adabiyotlar ro'yxati qo'shilmadi. Manbalarni o'zingiz tekshirib qo'shing.",
  few_sources: "Mavzu bo'yicha manbalar kam topildi. Ro'yxatdagilar haqiqiy, lekin keng emas — kerak bo'lsa qo'shimcha manba qo'shing.",
};

function readDraft(id) {
  try {
    return JSON.parse(localStorage.getItem(draftKey(id)) || 'null');
  } catch {
    return null;
  }
}
function writeDraft(id, draft) {
  try {
    if (draft) localStorage.setItem(draftKey(id), JSON.stringify(draft));
    else localStorage.removeItem(draftKey(id));
  } catch {
    // xotira to'la yoki yopiq — server baribir saqlaydi
  }
}

/** Joriy belgilash muharrir ichidami. */
const inside = (root, node) => Boolean(root && node && (node === root || root.contains(node)));

/** Muharrirning bevosita farzandi (xatboshi, sarlavha, ro'yxat, jadval, rasm). */
function topBlock(root, node) {
  let el = node;
  while (el && el.parentNode !== root) el = el.parentNode;
  return el && el.parentNode === root ? el : null;
}

const emptyParagraph = () => {
  const p = document.createElement('p');
  p.appendChild(document.createElement('br'));
  return p;
};

export default function ArticleEditor({ docId }) {
  const { push, replace, toast } = useApp();
  const editorRef = useRef(null);
  const fileRef = useRef(null);
  const rangeRef = useRef(null);
  const revRef = useRef(0);
  const dirtyRef = useRef(false);
  const savingRef = useRef(false);
  const changeRef = useRef(0);
  const saveTimer = useRef(null);
  const draftTimer = useRef(null);
  const titleRef = useRef('');
  const authorRef = useRef('');
  const imageTarget = useRef(null); // { mode: 'insert' } yoki { mode: 'replace', fig }

  const [article, setArticle] = useState(null);
  const [failed, setFailed] = useState(null);
  const [title, setTitleState] = useState('');
  const [author, setAuthorState] = useState('');
  const [status, setStatus] = useState('saved');
  const [words, setWords] = useState(0);
  const [focused, setFocused] = useState(false);
  const [marks, setMarks] = useState({});
  const [pop, setPop] = useState(null); // 'size' | 'color' | 'link'
  const [linkUrl, setLinkUrl] = useState('');
  const [figure, setFigure] = useState(null); // tanlangan rasm: { el, width, align, caption }
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(null);
  const [uploading, setUploading] = useState(false);

  const mediaUrl = useCallback((name) => `/api/article-media/${article?.mediaToken}/${name}`, [article?.mediaToken]);

  // ===== Yuklash va ko'rsatish =====
  const showArticle = useCallback((data, content = null) => {
    revRef.current = data.rev;
    const source = content ?? data;
    titleRef.current = source.title;
    authorRef.current = source.author ?? '';
    setTitleState(source.title);
    setAuthorState(source.author ?? '');
    setArticle(data);
    const url = (name) => `/api/article-media/${data.mediaToken}/${name}`;
    if (editorRef.current) editorRef.current.innerHTML = blocksToHtml(source.blocks, url);
    setWords(wordCount(source.blocks));
  }, []);

  // ===== Saqlash =====
  const collect = useCallback(() => ({
    title: titleRef.current.trim(),
    author: authorRef.current.trim(),
    blocks: htmlToBlocks(editorRef.current),
  }), []);

  const save = useCallback(async (force = false) => {
    if (!editorRef.current || !revRef.current) return false;
    if (savingRef.current) {
      // Hozirgi saqlash tugagach yana saqlanadi (o'zgarish hisoblagichi orqali)
      return false;
    }
    const content = collect();
    if (!content.title) {
      setStatus('error');
      toast(t("Sarlavha bo'sh bo'lmasin."), 'error');
      return false;
    }
    const change = changeRef.current;
    savingRef.current = true;
    setStatus('saving');
    try {
      const result = await api(`/articles/${docId}`, { method: 'PUT', body: { ...content, baseRev: revRef.current, force } });
      revRef.current = result.rev;
      if (changeRef.current === change) {
        dirtyRef.current = false;
        writeDraft(docId, null);
        setClosingConfirmation(false);
        setStatus('saved');
      } else {
        setStatus('dirty');
        clearTimeout(saveTimer.current);
        saveTimer.current = setTimeout(() => save(), SAVE_DELAY);
      }
      return true;
    } catch (error) {
      if (error.status === 0) {
        setStatus('offline');
      } else if (error.status === 409 && error.data?.conflict) {
        savingRef.current = false;
        const keepMine = await confirmDialog(t("Maqola boshqa oynada o'zgartirilgan. «OK» — o'zgarishlaringizni saqlash, «Bekor» — oxirgi versiyani yuklash."));
        if (keepMine) return save(true);
        dirtyRef.current = false;
        writeDraft(docId, null);
        setClosingConfirmation(false);
        showArticle(error.data.article);
        setStatus('saved');
        return false;
      } else {
        setStatus('error');
        toast(error.message, 'error');
      }
      return false;
    } finally {
      savingRef.current = false;
    }
  }, [collect, docId, showArticle, toast]);

  /** Har bir o'zgarishdan keyin: qurilmaga zaxira (oflayn uchun) va biroz kutib serverga. */
  const changed = useCallback(() => {
    changeRef.current += 1;
    dirtyRef.current = true;
    setClosingConfirmation(true);
    setStatus((s) => (s === 'offline' ? s : 'dirty'));
    clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      if (!editorRef.current) return;
      const content = collect();
      writeDraft(docId, { ...content, baseRev: revRef.current, at: Date.now() });
      setWords(wordCount(content.blocks));
    }, DRAFT_DELAY);
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => save(), SAVE_DELAY);
  }, [collect, docId, save]);

  /** Yuklab olish, nusxa va boshqa amallardan oldin — oxirgi o'zgarishlar albatta serverda bo'lsin. */
  const flush = useCallback(async () => {
    clearTimeout(saveTimer.current);
    if (!dirtyRef.current) return true;
    for (let i = 0; i < 20 && savingRef.current; i += 1) await new Promise((r) => setTimeout(r, 150));
    if (!dirtyRef.current) return true;
    const ok = await save();
    if (!ok) toast(t("Avval o'zgarishlar saqlanishi kerak. Internetni tekshirib, qayta urinib ko'ring."), 'error');
    return ok && !dirtyRef.current;
  }, [save, toast]);

  useEffect(() => {
    let alive = true;
    api(`/articles/${docId}`)
      .then(async (data) => {
        if (!alive) return;
        const draft = readDraft(docId);
        if (draft && draft.baseRev === data.rev) {
          // Oflayn yoki yopilib qolgan muharrirdagi saqlanmagan o'zgarishlar — tiklanadi va saqlanadi
          showArticle(data, draft);
          toast(t("Qurilmada saqlangan o'zgarishlar tiklandi"));
          changed();
        } else if (draft && draft.baseRev < data.rev) {
          showArticle(data);
          const restore = await confirmDialog(t("Qurilmada saqlanmagan eski o'zgarishlar bor, lekin maqola keyin boshqa joyda o'zgartirilgan. Qurilmadagi variantni tiklaymizmi?"));
          if (restore) {
            showArticle(data, draft);
            changeRef.current += 1;
            dirtyRef.current = true;
            save(true);
          } else writeDraft(docId, null);
        } else {
          if (draft) writeDraft(docId, null);
          showArticle(data);
        }
      })
      .catch((error) => alive && setFailed(error.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  // Internet qaytsa — navbatdagi o'zgarishlar yuboriladi; sahifadan chiqilsa — oxirgi marta saqlanadi
  useEffect(() => {
    const online = () => dirtyRef.current && save();
    window.addEventListener('online', online);
    return () => {
      window.removeEventListener('online', online);
      clearTimeout(saveTimer.current);
      clearTimeout(draftTimer.current);
      if (dirtyRef.current && editorRef.current) {
        writeDraft(docId, { ...collect(), baseRev: revRef.current, at: Date.now() });
        save();
      }
      setClosingConfirmation(false);
    };
  }, [collect, docId, save]);

  // ===== Belgilashni eslab qolish (asboblar paneli bosilganda yo'qolmasin) =====
  useEffect(() => {
    const onSelection = () => {
      const sel = window.getSelection();
      if (!sel?.rangeCount || !inside(editorRef.current, sel.anchorNode)) return;
      rangeRef.current = sel.getRangeAt(0).cloneRange();
      const node = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
      const block = topBlock(editorRef.current, sel.anchorNode);
      setMarks({
        b: document.queryCommandState('bold'),
        i: document.queryCommandState('italic'),
        u: document.queryCommandState('underline'),
        ul: document.queryCommandState('insertUnorderedList'),
        ol: document.queryCommandState('insertOrderedList'),
        block: block?.tagName ?? 'P',
        cell: Boolean(node?.closest?.('td, th')),
        link: Boolean(node?.closest?.('a')),
      });
    };
    document.addEventListener('selectionchange', onSelection);
    return () => document.removeEventListener('selectionchange', onSelection);
  }, []);

  function restoreRange() {
    const editor = editorRef.current;
    editor.focus({ preventScroll: true });
    const range = rangeRef.current;
    if (range && inside(editor, range.startContainer)) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }

  /** Asboblar paneli amali: belgilash tiklanadi, buyruq bajariladi, o'zgarish saqlanadi. */
  function command(fn) {
    if (!editorRef.current) return;
    restoreRange();
    document.execCommand('styleWithCSS', false, false);
    fn();
    changed();
    haptic('select');
  }
  const exec = (name, value = null) => command(() => document.execCommand(name, false, value));
  const keep = (e) => e.preventDefault(); // tugma bosilganda matndan fokus ketmasin

  function applySize(pt) {
    command(() => {
      document.execCommand('fontSize', false, '7');
      editorRef.current.querySelectorAll('font[size="7"]').forEach((font) => {
        const span = document.createElement('span');
        if (pt !== 12) span.style.fontSize = `${pt}pt`;
        while (font.firstChild) span.appendChild(font.firstChild);
        font.replaceWith(span);
      });
    });
    setPop(null);
  }

  function applyLink() {
    const url = linkUrl.trim();
    const valid = /^(https?:\/\/|mailto:)\S+$/i.test(url) ? url : /^[\w-]+(\.[\w-]+)+\S*$/.test(url) ? `https://${url}` : null;
    if (!valid) {
      toast(t("Havolani to'g'ri kiriting (https://...)"), 'error');
      return;
    }
    command(() => {
      const sel = window.getSelection();
      if (sel.isCollapsed) document.execCommand('insertHTML', false, `<a href="${valid.replace(/"/g, '%22')}">${valid.replace(/</g, '&lt;')}</a>&nbsp;`);
      else document.execCommand('createLink', false, valid);
    });
    setPop(null);
    setLinkUrl('');
  }

  // ===== Bloklar: jadval, bo'lim, rasm =====
  /** Yangi elementni joriy blokdan keyin qo'yadi (bo'sh xatboshi bo'lsa — o'rniga). */
  function insertBlock(el) {
    const editor = editorRef.current;
    const range = rangeRef.current;
    const block = range ? topBlock(editor, range.startContainer) : null;
    if (block && block.tagName === 'P' && !block.textContent.trim() && !block.querySelector('img')) block.replaceWith(el);
    else if (block) block.after(el);
    else editor.appendChild(el);
    if (!el.nextElementSibling) el.after(emptyParagraph());
    return el;
  }

  function placeCaret(node, select = false) {
    const range = document.createRange();
    range.selectNodeContents(node);
    if (!select) range.collapse(true);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    rangeRef.current = range.cloneRange();
  }

  function insertTable() {
    restoreRange();
    const table = document.createElement('table');
    table.className = 'art-table';
    const body = document.createElement('tbody');
    for (let r = 0; r < 3; r += 1) {
      const tr = document.createElement('tr');
      for (let c = 0; c < 3; c += 1) {
        const cell = document.createElement(r === 0 ? 'th' : 'td');
        cell.appendChild(document.createElement('br'));
        tr.appendChild(cell);
      }
      body.appendChild(tr);
    }
    table.appendChild(body);
    insertBlock(table);
    placeCaret(table.querySelector('th'));
    changed();
    haptic('select');
  }

  function currentCell() {
    const node = rangeRef.current?.startContainer;
    const el = node?.nodeType === 1 ? node : node?.parentElement;
    const cell = el?.closest?.('td, th');
    return cell && inside(editorRef.current, cell) ? cell : null;
  }

  function tableOp(op) {
    const cell = currentCell();
    if (!cell) return;
    const row = cell.parentElement;
    const table = cell.closest('table');
    const index = [...row.children].indexOf(cell);
    const rows = [...table.querySelectorAll('tr')];
    const blank = (tag) => {
      const c = document.createElement(tag);
      c.appendChild(document.createElement('br'));
      return c;
    };
    if (op === 'row+') {
      const tr = document.createElement('tr');
      [...row.children].forEach(() => tr.appendChild(blank('td')));
      row.after(tr);
      placeCaret(tr.firstChild);
    } else if (op === 'col+') {
      rows.forEach((tr) => {
        const ref = tr.children[index];
        const c = blank(ref?.tagName === 'TH' ? 'th' : 'td');
        if (ref) ref.after(c);
        else tr.appendChild(c);
      });
    } else if (op === 'row-') {
      if (rows.length <= 1) table.remove();
      else row.remove();
    } else if (op === 'col-') {
      if (row.children.length <= 1) table.remove();
      else rows.forEach((tr) => tr.children[index]?.remove());
    } else if (op === 'head') {
      const first = rows[0];
      const toTag = first.firstElementChild?.tagName === 'TH' ? 'td' : 'th';
      [...first.children].forEach((c) => {
        const n = document.createElement(toTag);
        while (c.firstChild) n.appendChild(c.firstChild);
        c.replaceWith(n);
      });
    } else if (op === 'del') {
      table.remove();
    }
    if (!editorRef.current.firstChild) editorRef.current.appendChild(emptyParagraph());
    changed();
    haptic('select');
  }

  function addSection() {
    restoreRange();
    const heading = document.createElement('h2');
    heading.textContent = t("Yangi bo'lim");
    const p = emptyParagraph();
    // Joriy bo'lim oxiriga (keyingi h1/h2 dan oldin) qo'yiladi
    const editor = editorRef.current;
    let block = rangeRef.current ? topBlock(editor, rangeRef.current.startContainer) : null;
    if (block) {
      while (block.nextElementSibling && !/^H[12]$/.test(block.nextElementSibling.tagName)) block = block.nextElementSibling;
      block.after(heading);
    } else editor.appendChild(heading);
    heading.after(p);
    heading.scrollIntoView({ block: 'center', behavior: 'smooth' });
    placeCaret(heading, true);
    changed();
    haptic('select');
  }

  async function deleteSection() {
    const editor = editorRef.current;
    let start = rangeRef.current ? topBlock(editor, rangeRef.current.startContainer) : null;
    while (start && !/^H[12]$/.test(start.tagName)) start = start.previousElementSibling;
    if (!start) {
      toast(t("Kursorni o'chiriladigan bo'lim ichiga qo'ying"), 'error');
      return;
    }
    const ok = await confirmDialog(t("«{name}» bo'limi butunlay o'chirilsinmi?", { name: start.textContent.trim().slice(0, 60) }));
    if (!ok) return;
    const level = Number(start.tagName[1]);
    let el = start;
    const remove = [];
    do {
      remove.push(el);
      el = el.nextElementSibling;
    } while (el && !(/^H[12]$/.test(el.tagName) && Number(el.tagName[1]) <= level));
    remove.forEach((n) => n.remove());
    if (!editor.firstChild) editor.appendChild(emptyParagraph());
    rangeRef.current = null;
    changed();
    haptic('medium');
  }

  // Rasm: galereyadan tanlash → JPEG ga siqish → serverga → matnga qo'yish yoki almashtirish
  function pickImage(target) {
    imageTarget.current = target;
    fileRef.current.value = '';
    fileRef.current.click();
  }

  async function onImageFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const blob = await prepareImage(file);
      const { name } = await apiUpload(`/articles/${docId}/media`, blob);
      const target = imageTarget.current;
      if (target?.mode === 'replace' && target.fig?.isConnected) {
        target.fig.dataset.src = name;
        target.fig.querySelector('img').src = mediaUrl(name);
      } else {
        const holder = document.createElement('div');
        holder.innerHTML = figureHtml({ src: name, width: 80, align: 'center', caption: '' }, mediaUrl);
        const fig = insertBlock(holder.firstChild);
        fig.scrollIntoView({ block: 'center', behavior: 'smooth' });
        openFigure(fig);
      }
      changed();
      haptic('success');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setUploading(false);
    }
  }

  function openFigure(el) {
    setFigure({
      el,
      width: Number(el.dataset.width) || 80,
      align: el.dataset.align || 'center',
      caption: el.querySelector('figcaption')?.textContent ?? '',
    });
  }

  function updateFigure(patch) {
    const el = figure?.el;
    if (!el?.isConnected) return;
    const next = { ...figure, ...patch };
    el.dataset.width = String(next.width);
    el.dataset.align = next.align;
    el.className = `art-fig art-fig--${next.align}`;
    el.querySelector('img').style.width = `${next.width}%`;
    el.querySelector('figcaption').textContent = next.caption;
    setFigure(next);
    changed();
  }

  function moveFigure(dir) {
    const el = figure?.el;
    if (!el?.isConnected) return;
    const sibling = dir < 0 ? el.previousElementSibling : el.nextElementSibling;
    if (!sibling) return;
    if (dir < 0) sibling.before(el);
    else sibling.after(el);
    el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    changed();
    haptic('select');
  }

  async function deleteFigure() {
    const el = figure?.el;
    if (!el?.isConnected) return;
    if (!(await confirmDialog(t("Rasm maqoladan o'chirilsinmi?")))) return;
    el.remove();
    if (!editorRef.current.firstChild) editorRef.current.appendChild(emptyParagraph());
    setFigure(null);
    changed();
  }

  function onEditorClick(event) {
    if (pop === 'size' || pop === 'color') setPop(null);
    const fig = event.target.closest?.('figure.art-fig');
    if (fig && inside(editorRef.current, fig)) {
      haptic('light');
      openFigure(fig);
    }
  }

  // Tashqaridan nusxalangan matn — faqat oddiy matn (begona uslub va skriptlar kirmaydi)
  function onPaste(event) {
    event.preventDefault();
    const text = event.clipboardData?.getData('text/plain') ?? '';
    document.execCommand('insertText', false, text);
  }

  // ===== Amallar =====
  async function download(fmt) {
    setBusy(fmt);
    try {
      if (!(await flush())) return;
      await downloadArticle(docId, fmt);
      toast(t('Yuklab olinmoqda') + ' ⬇️');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  async function send(fmt) {
    setBusy(`send-${fmt}`);
    try {
      if (!(await flush())) return;
      await sendArticle(docId, fmt);
      haptic('success');
      toast(t('Fayl Telegram chatga yuborildi') + ' 📩');
      setMore(false);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    setBusy('copy');
    try {
      if (!(await flush())) return;
      const { id } = await api(`/articles/${docId}/copy`, { method: 'POST' });
      haptic('success');
      toast(t('Yangi nusxa yaratildi'));
      setMore(false);
      replace('article', { docId: id });
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  async function restoreOriginal() {
    if (!(await confirmDialog(t("Maqola AI yozgan dastlabki holatiga qaytarilsinmi? Joriy versiya tarixda saqlanib qoladi.")))) return;
    setBusy('restore');
    try {
      clearTimeout(saveTimer.current);
      const data = await api(`/articles/${docId}/restore`, { method: 'POST' });
      dirtyRef.current = false;
      writeDraft(docId, null);
      setClosingConfirmation(false);
      showArticle(data);
      setStatus('saved');
      setMore(false);
      toast(t('Dastlabki variant tiklandi'));
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setBusy(null);
    }
  }

  function regenerate() {
    const p = article.params ?? {};
    setMore(false);
    push('article-order', {
      initial: {
        type: p.type, topic: p.topic, lang: p.lang, words: p.words, style: p.style,
        purpose: p.purpose, notes: p.notes, author: p.author,
      },
    });
  }

  // ===== Ko'rinish =====
  if (failed) {
    return (
      <main className="page">
        <TopBar title={t('Maqola')} />
        <Empty icon="📝" title={t('Maqola topilmadi')} text={failed} />
      </main>
    );
  }

  const [statusText, statusTone] = STATUS[status];
  const type = TYPE_BY_KEY[article?.params?.type];
  const tool = (label, onClick, { on = false, aria, wide = false } = {}) => (
    <button
      type="button"
      className={`art-tool ${on ? 'art-tool--on' : ''} ${wide ? 'art-tool--wide' : ''}`}
      onMouseDown={keep}
      onClick={onClick}
      aria-label={aria ?? (typeof label === 'string' ? label : undefined)}
      aria-pressed={on}
    >
      {label}
    </button>
  );

  return (
    <main className={`page art-ed ${focused ? 'art-ed--typing' : ''}`}>
      <TopBar
        title={t('Maqola muharriri')}
        right={article && (
          <button className={`art-status art-status--${statusTone}`} onClick={() => (status === 'error' || status === 'offline') && save()}>
            {status === 'saved' ? <CheckIcon size={14} /> : <span className="art-status__dot" />}
            {t(statusText)}
          </button>
        )}
      />

      {!article && <Skeleton height={60} count={5} />}

      <div style={{ display: article ? undefined : 'none' }}>
        {article?.notice && NOTICES[article.notice] && (
          <div className="note note--warn art-notice">⚠️ {t(NOTICES[article.notice])}</div>
        )}

        <div className="art-meta">
          {type && <span className="art-meta__type">{type.icon} {t(type.title)}</span>}
          <span>{t("{n} so'z", { n: words })}</span>
        </div>

        {/* Asboblar paneli — yuqorida yopishib turadi, telefonda yon tomonga suriladi */}
        <div className="art-toolbar">
          <div className="art-tools" role="toolbar" aria-label={t('Formatlash')}>
            {tool('↶', () => exec('undo'), { aria: t('Bekor qilish') })}
            {tool('↷', () => exec('redo'), { aria: t('Qaytarish') })}
            <span className="art-sep" />
            {BLOCK_STYLES.map(([tag, label]) => tool(t(label), () => exec('formatBlock', `<${tag.toLowerCase()}>`), {
              on: marks.block === tag, aria: tag === 'P' ? t('Oddiy matn') : t('{n}-darajali sarlavha', { n: tag[1] }), wide: tag === 'P',
            }))}
            <span className="art-sep" />
            {tool(<b>B</b>, () => exec('bold'), { on: marks.b, aria: t('Qalin') })}
            {tool(<i>I</i>, () => exec('italic'), { on: marks.i, aria: t('Kursiv') })}
            {tool(<u>U</u>, () => exec('underline'), { on: marks.u, aria: t('Tagiga chizilgan') })}
            {tool(<span className="art-tool__size">Aa</span>, () => setPop(pop === 'size' ? null : 'size'), { on: pop === 'size', aria: t('Shrift o\'lchami') })}
            {tool(<span className="art-tool__color" />, () => setPop(pop === 'color' ? null : 'color'), { on: pop === 'color', aria: t('Matn rangi') })}
            <span className="art-sep" />
            {tool(<AlignIcon kind="left" />, () => exec('justifyLeft'), { aria: t('Chapga') })}
            {tool(<AlignIcon kind="center" />, () => exec('justifyCenter'), { aria: t('Markazga') })}
            {tool(<AlignIcon kind="right" />, () => exec('justifyRight'), { aria: t("O'ngga") })}
            {tool(<AlignIcon kind="justify" />, () => exec('justifyFull'), { aria: t('Ikki tomonga') })}
            <span className="art-sep" />
            {tool('•≡', () => exec('insertUnorderedList'), { on: marks.ul, aria: t("Belgili ro'yxat") })}
            {tool('1≡', () => exec('insertOrderedList'), { on: marks.ol, aria: t("Raqamli ro'yxat") })}
            {tool('🔗', () => { setPop(pop === 'link' ? null : 'link'); }, { on: pop === 'link' || marks.link, aria: t('Havola') })}
            {tool('▦', insertTable, { aria: t('Jadval qo\'shish') })}
            {tool(<ImageIcon size={18} />, () => pickImage({ mode: 'insert' }), { aria: t("Rasm qo'shish") })}
            <span className="art-sep" />
            {tool(<><PlusIcon size={15} /> {t("Bo'lim")}</>, addSection, { aria: t("Bo'lim qo'shish"), wide: true })}
            {tool(<><TrashIcon size={15} /> {t("Bo'lim")}</>, deleteSection, { aria: t("Bo'limni o'chirish"), wide: true })}
          </div>

          {pop === 'size' && (
            <div className="art-pop">
              {SIZES.map((pt) => (
                <button key={pt} className="art-pop__btn" onMouseDown={keep} onClick={() => applySize(pt)}>
                  {pt}{pt === 12 ? ` · ${t('asosiy')}` : ''}
                </button>
              ))}
            </div>
          )}
          {pop === 'color' && (
            <div className="art-pop">
              {COLORS.map((c) => (
                <button key={c} className="art-swatch" style={{ background: c }} onMouseDown={keep}
                  onClick={() => { exec('foreColor', c); setPop(null); }} aria-label={c} />
              ))}
            </div>
          )}
          {pop === 'link' && (
            <div className="art-pop art-pop--link">
              <input
                className="field"
                inputMode="url"
                placeholder="https://..."
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyLink()}
              />
              <button className="btn btn--primary btn--sm" onClick={applyLink}>{t("Qo'yish")}</button>
              {marks.link && <button className="btn btn--soft btn--sm" onMouseDown={keep} onClick={() => { exec('unlink'); setPop(null); }}>{t('Olib tashlash')}</button>}
            </div>
          )}
          {marks.cell && (
            <div className="art-pop art-pop--table">
              <span className="art-pop__label">{t('Jadval')}:</span>
              {[['row+', "+ Qator"], ['col+', '+ Ustun'], ['row-', '− Qator'], ['col-', '− Ustun'], ['head', 'Sarlavha qatori'], ['del', "Jadvalni o'chirish"]].map(([op, label]) => (
                <button key={op} className="art-pop__btn" onMouseDown={keep} onClick={() => tableOp(op)}>{t(label)}</button>
              ))}
            </div>
          )}
        </div>

        <div className="art-paper">
          <textarea
            className="art-title"
            rows={2}
            maxLength={article?.limits?.title ?? 300}
            value={title}
            placeholder={t('Maqola sarlavhasi')}
            onChange={(e) => { titleRef.current = e.target.value; setTitleState(e.target.value); changed(); }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
          <input
            className="art-author"
            maxLength={article?.limits?.author ?? 200}
            value={author}
            placeholder={t('Muallif (ixtiyoriy)')}
            onChange={(e) => { authorRef.current = e.target.value; setAuthorState(e.target.value); changed(); }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
          <div
            ref={editorRef}
            className="art-doc"
            lang={article?.params?.lang ?? 'uz'}
            contentEditable
            suppressContentEditableWarning
            spellCheck
            onInput={changed}
            onClick={onEditorClick}
            onPaste={onPaste}
            onFocus={() => {
              setFocused(true);
              document.execCommand('defaultParagraphSeparator', false, 'p');
            }}
            onBlur={() => setFocused(false)}
          />
        </div>
        <p className="card__hint art-hint">
          {t("O'zgarishlar avtomatik saqlanadi. Rasmni bosing — o'lchami, joylashuvi va izohini o'zgartirasiz.")}
        </p>
      </div>

      <input ref={fileRef} type="file" accept="image/*" hidden onChange={onImageFile} />
      {uploading && <div className="art-uploading">{t('Rasm yuklanmoqda...')}</div>}

      {article && (
        <div className="bottom-bar art-bar">
          <button className="btn btn--white" onClick={() => download('pdf')} disabled={busy !== null}>
            <DownloadIcon size={19} /> {busy === 'pdf' ? '…' : 'PDF'}
          </button>
          <button className="btn btn--primary" onClick={() => download('docx')} disabled={busy !== null}>
            <DownloadIcon size={19} /> {busy === 'docx' ? t('Tayyorlanmoqda...') : 'Word'}
          </button>
          <button className="btn btn--soft art-bar__more" onClick={() => setMore(true)} aria-label={t("Boshqa amallar")}>⋯</button>
        </div>
      )}

      {figure && (
        <Sheet title={t('Rasm')} onClose={() => setFigure(null)}>
          <div className="art-fig-sheet">
            <img src={figure.el.querySelector('img')?.src} alt="" />
            <label className="editor-field">
              <span className="field-label">{t('Izoh (rasm ostidagi yozuv)')}</span>
              <input className="field" maxLength={300} value={figure.caption} placeholder={t('Masalan: 1-rasm. Toshkent shahri')}
                onChange={(e) => updateFigure({ caption: e.target.value })} />
            </label>
            <span className="field-label">{t("O'lchami")}: {figure.width}%</span>
            <input type="range" min={25} max={100} step={5} value={figure.width} className="art-range"
              onChange={(e) => updateFigure({ width: Number(e.target.value) })} />
            <span className="field-label">{t('Joylashuvi')}</span>
            <div className="segment">
              {[['left', 'Chapda'], ['center', 'Markazda'], ['right', "O'ngda"]].map(([key, label]) => (
                <button key={key} className={figure.align === key ? 'segment--active' : ''} onClick={() => updateFigure({ align: key })}>
                  {t(label)}
                </button>
              ))}
            </div>
            <div className="btn-row">
              <button className="btn btn--soft" onClick={() => moveFigure(-1)}>↑ {t('Yuqoriga')}</button>
              <button className="btn btn--soft" onClick={() => moveFigure(1)}>↓ {t('Pastga')}</button>
            </div>
            <div className="btn-row">
              <button className="btn btn--white" onClick={() => pickImage({ mode: 'replace', fig: figure.el })}>
                <RefreshIcon size={18} /> {t('Almashtirish')}
              </button>
              <button className="btn btn--danger" onClick={deleteFigure}>
                <TrashIcon size={18} /> {t("O'chirish")}
              </button>
            </div>
            <button className="btn btn--primary mt-12" onClick={() => setFigure(null)}>{t('Tayyor')}</button>
          </div>
        </Sheet>
      )}

      {more && (
        <Sheet title={t('Amallar')} onClose={() => setMore(false)}>
          <div className="menu">
            <button className="menu__item pressable" onClick={() => send('docx')} disabled={busy !== null}>
              <SendIcon size={20} /> <span>{busy === 'send-docx' ? t('Yuborilmoqda...') : t('Word faylni chatga yuborish')}</span>
            </button>
            <button className="menu__item pressable" onClick={() => send('pdf')} disabled={busy !== null}>
              <SendIcon size={20} /> <span>{busy === 'send-pdf' ? t('Yuborilmoqda...') : t('PDF faylni chatga yuborish')}</span>
            </button>
            <button className="menu__item pressable" onClick={copy} disabled={busy !== null}>
              <span aria-hidden="true">📄</span> <span>{t('Yangi nusxa')}<br /><small>{t('Joriy variantdan alohida nusxa — asl maqola o\'zgarmaydi')}</small></span>
            </button>
            <button className="menu__item pressable" onClick={regenerate} disabled={busy !== null}>
              <span aria-hidden="true">✨</span> <span>{t('Qayta yaratish')}<br /><small>{t('Shu sozlamalar bilan yangi maqola (pullik)')}</small></span>
            </button>
            {article?.hasOriginal && (
              <button className="menu__item pressable" onClick={restoreOriginal} disabled={busy !== null}>
                <span aria-hidden="true">↩️</span> <span>{t('Dastlabki variantga qaytarish')}</span>
              </button>
            )}
          </div>
        </Sheet>
      )}
    </main>
  );
}

function AlignIcon({ kind }) {
  const lines = {
    left: [[3, 17], [3, 12], [3, 17], [3, 10]],
    center: [[3, 17], [6, 14], [3, 17], [7, 13]],
    right: [[3, 17], [8, 17], [3, 17], [10, 17]],
    justify: [[3, 17], [3, 17], [3, 17], [3, 17]],
  }[kind];
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">
      {lines.map(([a, b], i) => <path key={i} d={`M${a} ${4 + i * 4}H${b}`} stroke="currentColor" strokeWidth="2" strokeLinecap="round" />)}
    </svg>
  );
}
