"""Logodan ilova va bot uchun barcha ikonkalarni yasaydi.

Ishlatish:  python branding/make_icons.py branding/logo-source.png
            python branding/make_icons.py branding/logo-source.png --full   # fonli to'liq kvadrat rasm (fon kesilmaydi)
Natija:     client/public/ (sayt ikonkalari) va branding/ (bot avatari, asl logo)
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "client" / "public"
BRANDING = ROOT / "branding"
SENTINEL = (255, 0, 255)


def cut_background(source):
    """Oq fonni olib tashlaydi: burchaklardan to'ldirib, logoning ichidagi oq qismlarga tegmaydi."""
    image = source.convert("RGB")
    filled = image.copy()
    w, h = filled.size
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(filled, corner, SENTINEL, thresh=60)
    background = Image.new("RGB", filled.size, SENTINEL)
    # Fon — SENTINEL bo'lgan joylar; qolgani logo
    diff = ImageChops.difference(filled, background).convert("L")
    mask = diff.point(lambda v: 255 if v > 0 else 0)
    # Oq «halo» qolmasin: 1 px ichkariga va yumshoq qirra
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    logo = image.convert("RGBA")
    logo.putalpha(mask)
    return logo.crop(mask.getbbox())


def square(image):
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def opaque(logo, inset=0.095):
    """Burchaksiz to'liq kvadrat (iPhone bosh ekrani va Telegram avatari o'zi yumaloqlaydi)."""
    d = round(logo.width * inset)
    return logo.crop((d, d, logo.width - d, logo.height - d)).convert("RGB")


def resized(image, size):
    return image.resize((size, size), Image.Resampling.LANCZOS)


def center_square(image):
    """Fonli rasm: markazdan kvadrat qilib qirqadi (fon saqlanadi)."""
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    return image.convert("RGB").crop((left, top, left + side, top + side))


def rounded(image, radius=0.22):
    """Ilova ikonkasi kabi yumaloq burchaklar (shaffof fon)."""
    mask = Image.new("L", (image.width * 4, image.height * 4), 0)  # silliq qirra uchun 4× chizib kichraytiriladi
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=round(mask.width * radius), fill=255)
    out = image.convert("RGBA")
    out.putalpha(mask.resize(image.size, Image.Resampling.LANCZOS))
    return out


def main(source_path, full=False):
    if full:
        full_image = center_square(Image.open(source_path))
        logo = rounded(full_image)
    else:
        logo = square(cut_background(Image.open(source_path)))
    BRANDING.mkdir(exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    resized(logo, 1024).save(BRANDING / "logo-1024.png", optimize=True)
    # Sayt: yuklanish ekrani, PWA (telefon bosh ekrani), brauzer tabi
    resized(logo, 256).save(PUBLIC / "logo.png", optimize=True)  # yuklanish ekrani: 112 px × 2 (retina)
    resized(logo, 512).save(PUBLIC / "icon-512.png", optimize=True)
    resized(logo, 192).save(PUBLIC / "icon-192.png", optimize=True)
    resized(logo, 32).save(PUBLIC / "favicon-32.png", optimize=True)
    resized(logo, 48).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    full = full_image if full else opaque(logo)
    resized(full, 180).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    # Telegram: bot avatari (@BotFather → /setuserpic) va Mini App ikonkasi
    resized(full, 640).save(BRANDING / "bot-avatar-640.jpg", quality=95)
    resized(full, 512).save(BRANDING / "bot-avatar-512.png", optimize=True)
    print("Tayyor:", ", ".join(p.name for p in sorted(PUBLIC.glob("*")) + sorted(BRANDING.glob("*.*"))))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--full"]
    main(args[0] if args else BRANDING / "logo-source.png", full="--full" in sys.argv)
