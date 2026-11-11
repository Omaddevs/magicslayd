"""Gemini rasm generatsiyasi: javobdan rasmni topish va API ishlamaganda zaxira yo'l (lokal soxta server bilan)."""
import asyncio
import base64
import io
import os
import tempfile
import unittest
from unittest import mock

# Haqiqiy bazaga tegmaslik uchun — vaqtinchalik papka (config DATA_DIR ni import paytida o'qiydi)
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="slayd-test-"))

from aiohttp import web  # noqa: E402
from PIL import Image  # noqa: E402

from presentation import genimage  # noqa: E402


def jpeg_b64(width=1376, height=768):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 60)).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


class FindImageTest(unittest.TestCase):
    def test_generate_content_shape(self):
        data = jpeg_b64()
        payload = {"candidates": [{"content": {"parts": [{"text": "ok"}, {"inlineData": {"mimeType": "image/png", "data": data}}]}}]}
        self.assertEqual(genimage.find_image(payload), data)

    def test_interactions_shape(self):
        data = jpeg_b64()
        payload = {"steps": [{"type": "model_output", "content": [{"type": "image", "mime_type": "image/jpeg", "data": data}]}]}
        self.assertEqual(genimage.find_image(payload), data)
        self.assertEqual(genimage.find_image({"output_image": {"data": data, "mime_type": "image/jpeg"}}), data)

    def test_no_image(self):
        self.assertIsNone(genimage.find_image({"steps": [{"type": "model_output", "content": [{"type": "text", "text": "x" * 2000}]}]}))

    def test_prompt_forbids_text(self):
        prompt = genimage.prompt_for("solar panels", "Energiya", "Quyosh energiyasi", "baroque oil painting")
        self.assertIn("baroque oil painting", prompt)
        self.assertIn("no text", prompt)


class FallbackTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Faqat Gemini sinovi: .env da Cloudflare kaliti bo'lsa ham haqiqiy so'rov ketmasin
        patcher = mock.patch.object(genimage, "CLOUDFLARE_API_TOKEN", "")
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_interactions_404_falls_back_to_generate_content(self):
        calls = []
        data = jpeg_b64()

        async def interactions(request):
            calls.append("interactions")
            return web.json_response({"error": {"message": "not found"}}, status=404)

        async def generate(request):
            calls.append("generateContent")
            body = await request.json()
            assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
            return web.json_response({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/jpeg", "data": data}}]}}]})

        app = web.Application()
        app.router.add_post("/v1beta/interactions", interactions)
        app.router.add_post(r"/v1beta/models/{model}:generateContent", generate)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with mock.patch.object(genimage, "API", f"http://127.0.0.1:{port}/v1beta"), \
                    mock.patch.object(genimage, "GEMINI_API_KEY", "test"), \
                    mock.patch.object(genimage, "_legacy_only", False):
                images = await genimage.generate_images(["a", "b"])
                self.assertTrue(all(images))
                Image.open(io.BytesIO(images[0])).verify()
                self.assertTrue(genimage._legacy_only)  # keyingi so'rovlar to'g'ridan-to'g'ri eskisiga
        finally:
            await runner.cleanup()
        self.assertIn("interactions", calls)
        self.assertIn("generateContent", calls)

    async def test_bad_key_disables_and_returns_none(self):
        async def forbidden(request):
            return web.json_response({"error": {"message": "API key not valid"}}, status=403)

        app = web.Application()
        app.router.add_post("/v1beta/interactions", forbidden)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with mock.patch.object(genimage, "API", f"http://127.0.0.1:{port}/v1beta"), \
                    mock.patch.object(genimage, "GEMINI_API_KEY", "bad"), \
                    mock.patch.object(genimage, "_legacy_only", False), \
                    mock.patch.object(genimage, "_disabled_until", 0.0):
                self.assertEqual(await genimage.generate_images(["a"]), [None])
                self.assertFalse(genimage.enabled())  # bir muddat urinilmaydi — foto qidiruvi ishlaydi
        finally:
            await runner.cleanup()


class CloudflareTest(unittest.IsolatedAsyncioTestCase):
    async def serve(self, handler):
        app = web.Application()
        app.router.add_post("/run", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        self.addAsyncCleanup(runner.cleanup)
        return f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/run"

    def patches(self, url):
        return (mock.patch.object(genimage, "CF_API", url), mock.patch.object(genimage, "GEMINI_API_KEY", ""),
                mock.patch.object(genimage, "CLOUDFLARE_ACCOUNT_ID", "acc"),
                mock.patch.object(genimage, "CLOUDFLARE_API_TOKEN", "tok"),
                mock.patch.object(genimage, "_cf_disabled_until", 0.0))

    async def test_free_flux_image(self):
        data = jpeg_b64(1024, 1024)
        seen = {}

        async def run(request):
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = await request.json()
            return web.json_response({"result": {"image": data}, "success": True, "errors": []})

        url = await self.serve(run)
        a, b, c, d, e = self.patches(url)
        with a, b, c, d, e:
            self.assertTrue(genimage.enabled())
            images = await genimage.generate_images(["Timurid cavalry on the steppe"])
        self.assertTrue(images[0])
        self.assertEqual(seen["auth"], "Bearer tok")
        self.assertEqual(seen["body"]["steps"], genimage.CF_STEPS)

    async def test_daily_limit_falls_back(self):
        async def run(request):
            return web.json_response({"success": False, "errors": [{"code": 4006, "message": "daily free allocation"}]}, status=429)

        url = await self.serve(run)
        a, b, c, d, e = self.patches(url)
        with a, b, c, d, e:
            self.assertEqual(await genimage.generate_images(["x"]), [None])
            self.assertFalse(genimage.enabled())  # ertasi kungacha — rasmlar fotobazadan


if __name__ == "__main__":
    asyncio.run(unittest.main())
