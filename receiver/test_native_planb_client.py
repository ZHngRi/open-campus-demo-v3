"""Mock contract checks for the native client's Plan B / Race HTTP calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend_client import BackendClient


class _Response:
    ok = True
    status_code = 200
    text = ""
    def json(self):
        return {"session_id": "demo", "processing_target": "planb"}


class NativePlanBClientTests(unittest.TestCase):
    def test_upload_is_multipart_file_with_exact_target(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "clip.mov"; video.write_bytes(b"video")
            with patch("backend_client.requests.request", return_value=_Response()) as request:
                BackendClient("http://sender:8056").upload_video(str(video), "planb")
            method, url = request.call_args.args[:2]
            kwargs = request.call_args.kwargs
            self.assertEqual((method, url), ("POST", "http://sender:8056/videos/upload"))
            self.assertEqual(kwargs["data"], {"processing_target": "planb"})
            self.assertIn("file", kwargs["files"])
            self.assertFalse(isinstance(kwargs["files"]["file"], str))

    def test_start_has_no_json_body(self):
        with patch("backend_client.requests.request", return_value=_Response()) as request:
            BackendClient("http://sender:8056").start_processing("demo")
        self.assertEqual(request.call_args.args[:2], ("POST", "http://sender:8056/sessions/demo/start"))
        self.assertNotIn("json", request.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
