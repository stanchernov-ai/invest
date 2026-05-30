import unittest
from unittest.mock import patch, MagicMock

from src.output.reporting import fetch_briefing_visual_assets, format_chart_health


SAMPLE_HTML = """
<html><body>
  <img src="https://example.com/chart-a.png" alt="Performance vs. Benchmark">
  <img src="data:image/png;base64,abc" alt="inline-skip">
</body></html>
"""


class TestBriefingVisualAssets(unittest.TestCase):
    @patch("src.output.reporting.requests.get")
    def test_fetch_skips_data_urls_and_downloads_http_images(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "image/png"}
        resp.content = b"\x89PNG fake"
        mock_get.return_value = resp

        assets = fetch_briefing_visual_assets(SAMPLE_HTML, max_images=5)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["name"], "Performance vs. Benchmark")
        self.assertEqual(assets[0]["mime_type"], "image/png")
        mock_get.assert_called_once()

    @patch("src.output.reporting.requests.get")
    def test_fetch_reuses_prefetched_chart_bytes(self, mock_get):
        chart_url = "https://example.com/chart-a.png"
        html = f'<html><body><img src="{chart_url}" alt="Performance vs. Benchmark"></body></html>'
        prefetched = {
            chart_url: {
                "name": "Performance vs. Benchmark — indexed (line)",
                "url": chart_url,
                "bytes": b"\x89PNG cached",
                "mime_type": "image/png",
            }
        }
        assets = fetch_briefing_visual_assets(html, prefetched_by_url=prefetched)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["bytes"], b"\x89PNG cached")
        mock_get.assert_not_called()


class TestChartHealthFormat(unittest.TestCase):
    def test_format_marks_broken(self):
        text = format_chart_health([{"name": "Line", "ok": False, "detail": "HTTP 404"}])
        self.assertIn("BROKEN", text)


if __name__ == "__main__":
    unittest.main()
