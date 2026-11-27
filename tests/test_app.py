import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import requests
import uvicorn

import web
from migrator import PlaylistMigrator


class FakeSpotify:
    def __init__(self):
        self._pages = {
            "page2": {
                "items": [
                    {"track": {"name": "Track Two", "artists": [{"name": "Artist B"}]}},
                    {"track": None},
                ],
                "next": None,
            }
        }

    def playlist(self, playlist_id):
        return {
            "id": playlist_id,
            "name": "Test Mix",
            "description": "Test description",
            "owner": {"display_name": "Test User"},
            "tracks": {"total": 2},
            "images": [{"url": "https://example.com/cover.jpg"}],
        }

    def playlist_tracks(self, playlist_id):
        return {
            "items": [
                {"track": {"name": "Track One", "artists": [{"name": "Artist A"}]}},
            ],
            "next": "page2",
        }

    def next(self, current):
        return self._pages.get(current.get("next"))

    def current_user_saved_tracks(self, limit=50):
        return {
            "total": 1,
            "items": [
                {"track": {"name": "Saved Song", "artists": [{"name": "Artist S"}]}},
            ],
            "next": None,
        }

    def current_user_playlists(self, limit=50):
        return {
            "items": [
                {
                    "id": "pl_123",
                    "name": "Test Mix",
                    "description": "",
                    "tracks": {"total": 2},
                    "images": [],
                    "public": False,
                }
            ],
            "next": None,
        }


class FakeYTMusic:
    def __init__(self, fail_queries=None):
        self.created = []
        self.added = []
        self.fail_queries = set(fail_queries or [])

    def create_playlist(self, title, description, privacy_status="PRIVATE"):
        self.created.append((title, description, privacy_status))
        return "YT_PL_001"

    def search(self, query, filter="songs"):
        if query in self.fail_queries:
            return []
        if filter == "songs" and query == "Video Fallback Track Artist V":
            return []
        return [{"videoId": f"vid_{query.replace(' ', '_')}"}]

    def add_playlist_items(self, playlist_id, video_ids):
        self.added.append((playlist_id, list(video_ids)))
        return {"status": "STATUS_SUCCEEDED"}


class TestMigrator(unittest.TestCase):
    def test_extract_spotify_id(self):
        self.assertEqual(
            PlaylistMigrator.extract_spotify_id("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )
        self.assertEqual(
            PlaylistMigrator.extract_spotify_id("spotify:playlist:6zV3IVldsAYns53vK9CQGQ"),
            "6zV3IVldsAYns53vK9CQGQ",
        )
        self.assertEqual(
            PlaylistMigrator.extract_spotify_id("4JLDVYu7w2XukVV1fDT1vT"),
            "4JLDVYu7w2XukVV1fDT1vT",
        )

    def test_paginated_tracks_and_liked_songs(self):
        m = PlaylistMigrator(FakeSpotify(), FakeYTMusic(), rate_limit_delay=0)
        tracks = m.get_playlist_tracks("pl_123")
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["query"], "Track One Artist A")
        self.assertEqual(tracks[1]["query"], "Track Two Artist B")

        liked = m.get_liked_songs()
        self.assertEqual(len(liked), 1)
        self.assertEqual(liked[0]["title"], "Saved Song")

        playlists = m.get_user_playlists()
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]["id"], "pl_123")

    def test_search_fallback_and_transfer_with_retry(self):
        yt = FakeYTMusic(fail_queries={"Missing Artist Track Unknown", "Missing Artist Track"})
        m = PlaylistMigrator(FakeSpotify(), yt, rate_limit_delay=0)
        events = []

        tracks = [
            {"title": "Track One", "artist": "Artist A", "query": "Track One Artist A"},
            {"title": "Video Fallback Track", "artist": "Artist V", "query": "Video Fallback Track Artist V"},
            {"title": "Missing Artist Track", "artist": "Unknown", "query": "Missing Artist Track Unknown"},
        ]

        orig_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                result = m.transfer_tracks(tracks, "My Export", progress_callback=events.append)
                self.assertTrue(os.path.exists("failed_tracks.txt"))
            finally:
                os.chdir(orig_cwd)

        self.assertEqual(result["playlist_id"], "YT_PL_001")
        self.assertEqual(result["added"], 2)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(events[0]["type"], "playlist_created")
        self.assertEqual(events[-1]["type"], "complete")


class TestWebAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8766
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = uvicorn.Server(uvicorn.Config(web.app, host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(30):
            try:
                requests.get(f"{cls.base_url}/", timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=2)

    def test_routes_and_sse_transfer(self):
        fake_sp = FakeSpotify()
        fake_yt = FakeYTMusic()

        with (
            patch("web.get_spotify_client_nonblocking", return_value=(fake_sp, {"configured": True, "connected": True, "user": "Test User", "message": "Connected"})),
            patch("web.get_ytmusic_status", return_value=(fake_yt, {"connected": True, "auth_file": "oauth.json", "message": "Connected"})),
        ):
            r_index = requests.get(f"{self.base_url}/")
            self.assertEqual(r_index.status_code, 200)
            self.assertIn("Spotify", r_index.text)

            r_js = requests.get(f"{self.base_url}/static/app.js")
            self.assertEqual(r_js.status_code, 200)

            r_status = requests.get(f"{self.base_url}/api/status")
            self.assertEqual(r_status.status_code, 200)
            self.assertTrue(r_status.json()["spotify"]["connected"])
            self.assertTrue(r_status.json()["ytmusic"]["connected"])

            r_playlists = requests.get(f"{self.base_url}/api/playlists")
            self.assertEqual(r_playlists.status_code, 200)
            self.assertEqual(r_playlists.json()["liked_total"], 1)

            r_preview = requests.post(f"{self.base_url}/api/preview", json={"playlist": "pl_123"})
            self.assertEqual(r_preview.status_code, 200)
            self.assertEqual(r_preview.json()["name"], "Test Mix")

            r_start = requests.post(
                f"{self.base_url}/api/transfer",
                json={"mode": "playlist", "playlist": "pl_123", "delay": 0.0},
            )
            self.assertEqual(r_start.status_code, 200)
            job_id = r_start.json()["job_id"]

            events = []
            saw_end = False
            with requests.get(f"{self.base_url}/api/transfer/{job_id}/stream", stream=True, timeout=10) as stream:
                for line in stream.iter_lines(decode_unicode=True):
                    if line == "event: end":
                        saw_end = True
                    elif line and line.startswith("data: "):
                        parsed = json.loads(line[6:])
                        if parsed:
                            events.append(parsed)

            self.assertTrue(saw_end)
            event_types = [e["type"] for e in events]
            self.assertIn("playlist_created", event_types)
            self.assertIn("complete", event_types)
            complete = [e for e in events if e["type"] == "complete"][0]
            self.assertEqual(complete["added"], 2)
            self.assertEqual(complete["total"], 2)


if __name__ == "__main__":
    unittest.main()
