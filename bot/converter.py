"""Tayyor .pptx / .docx faylni PDF ga aylantiradi (LibreOffice orqali).
LibreOffice o'rnatilmagan bo'lsa PDF_AVAILABLE = False va botda PDF tugmasi ko'rinmaydi."""
import asyncio
import shutil
import tempfile
from pathlib import Path

from config import DATA_DIR

_CANDIDATES = (
    shutil.which("soffice"),
    shutil.which("libreoffice"),
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)
SOFFICE = next((path for path in _CANDIDATES if path and Path(path).exists()), None)
PDF_AVAILABLE = SOFFICE is not None
PROFILE = (DATA_DIR / ".libreoffice").as_uri()  # alohida profil — kompyuterdagi ochiq LibreOffice'ga xalaqit bermaydi
TIMEOUT = 180

_lock = asyncio.Lock()  # bitta profil bilan bir vaqtda faqat bitta konvertatsiya ishlaydi


class ConvertError(Exception):
    pass


async def to_pdf(data: bytes, ext: str) -> bytes:
    if not PDF_AVAILABLE:
        raise ConvertError("PDF yaratish hozircha mavjud emas.")
    async with _lock:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / f"file.{ext}"
            source.write_bytes(data)
            process = await asyncio.create_subprocess_exec(
                SOFFICE, "--headless", "--norestore", "--nologo", f"-env:UserInstallation={PROFILE}",
                "--convert-to", "pdf", "--outdir", tmp, str(source),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(process.wait(), TIMEOUT)
            except TimeoutError:
                process.kill()
                raise ConvertError("PDF tayyorlash juda uzoq davom etdi.")
            result = Path(tmp) / "file.pdf"
            if not result.exists():
                raise ConvertError("PDF yaratib bo'lmadi.")
            return result.read_bytes()
