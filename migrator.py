"""
Core migration logic for transferring playlists and liked songs from Spotify to YouTube Music.
"""

import re
import time
from typing import Callable, Dict, List, Optional
from tqdm import tqdm


class PlaylistMigrator:
    def __init__(self, sp_client, yt_client, rate_limit_delay: float = 0.5):
        self.sp = sp_client
        self.yt = yt_client
        self.rate_limit_delay = rate_limit_delay

    @staticmethod
    def extract_spotify_id(playlist_input: str) -> str:
        """Extract playlist ID from a Spotify URI, URL, or raw ID."""
        playlist_input = playlist_input.strip()
        if playlist_input.startswith("spotify:playlist:"):
            return playlist_input.split(":")[-1]
        match = re.search(r"playlist/([a-zA-Z0-9]+)", playlist_input)
        if match:
            return match.group(1)
        return playlist_input

    def _collect_paginated_tracks(self, results: Optional[Dict]) -> List[Dict]:
        tracks = []
        while results:
            for item in results.get("items", []):
                track = item.get("track")
                if not track or not track.get("name"):
                    continue
                name = track["name"]
                artists = ", ".join(a["name"] for a in track.get("artists", []))
                tracks.append({
                    "title": name,
                    "artist": artists,
                    "query": f"{name} {artists}".strip(),
                })

            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return tracks

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Fetch all tracks from a Spotify playlist."""
        return self._collect_paginated_tracks(self.sp.playlist_tracks(playlist_id))

    def get_liked_songs(self) -> List[Dict]:
        """Fetch all Liked Songs for the authenticated Spotify user."""
        return self._collect_paginated_tracks(self.sp.current_user_saved_tracks(limit=50))

    def get_user_playlists(self) -> List[Dict]:
        """Fetch all playlists owned or followed by the authenticated Spotify user."""
        playlists = []
        results = self.sp.current_user_playlists(limit=50)
        while results:
            for p in results.get("items", []):
                if not p:
                    continue
                images = p.get("images") or []
                tracks_info = p.get("tracks") or {}
                playlists.append({
                    "id": p.get("id"),
                    "name": p.get("name", "Untitled Playlist"),
                    "description": p.get("description") or "",
                    "track_count": tracks_info.get("total", 0),
                    "image_url": images[0].get("url") if images else None,
                    "public": bool(p.get("public", False)),
                })
            if results.get("next"):
                results = self.sp.next(results)
            else:
                break
        return playlists

    def search_ytmusic_track(self, query: str) -> Optional[str]:
        """Search YouTube Music songs first, falling back to videos."""
        for filter_type in ("songs", "videos"):
            try:
                results = self.yt.search(query, filter=filter_type)
                if results and "videoId" in results[0]:
                    return results[0]["videoId"]
            except Exception:
                pass
        return None

    @staticmethod
    def _emit(callback: Optional[Callable[[Dict], None]], event: Dict) -> None:
        if callback is not None:
            callback(event)

    def transfer_tracks(
        self,
        tracks: List[Dict],
        yt_playlist_name: str,
        yt_playlist_desc: str = "Imported from Spotify",
        privacy_status: str = "PRIVATE",
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> Dict:
        """Create a YouTube Music playlist and add matching tracks."""
        quiet = progress_callback is not None
        if not quiet:
            print(f"\nCreating YouTube Music playlist: '{yt_playlist_name}'...")

        try:
            yt_playlist_id = self.yt.create_playlist(
                title=yt_playlist_name[:150],
                description=yt_playlist_desc,
                privacy_status=privacy_status,
            )
            if not quiet:
                print(f"Playlist created (ID: {yt_playlist_id})")
        except Exception as e:
            if not quiet:
                print(f"Failed to create playlist on YouTube Music: {e}")
            self._emit(progress_callback, {
                "type": "error",
                "message": f"Failed to create playlist on YouTube Music: {e}",
            })
            return {"playlist_id": None, "added": 0, "failed": tracks, "total": len(tracks)}

        self._emit(progress_callback, {
            "type": "playlist_created",
            "playlist_id": yt_playlist_id,
            "name": yt_playlist_name,
            "total": len(tracks),
        })

        added_count = 0
        failed_tracks = []
        total = len(tracks)

        if not quiet:
            print(f"Transferring {total} songs...")
        pbar = tqdm(tracks, desc="Migrating", unit="song", disable=quiet)

        for idx, track in enumerate(pbar, 1):
            video_id = self.search_ytmusic_track(track["query"])

            if video_id:
                try:
                    self.yt.add_playlist_items(yt_playlist_id, [video_id])
                    added_count += 1
                    self._emit(progress_callback, {
                        "type": "track",
                        "index": idx,
                        "total": total,
                        "title": track["title"],
                        "artist": track["artist"],
                        "status": "added",
                    })
                except Exception as e:
                    track["error"] = str(e)
                    failed_tracks.append(track)
                    self._emit(progress_callback, {
                        "type": "track",
                        "index": idx,
                        "total": total,
                        "title": track["title"],
                        "artist": track["artist"],
                        "status": "failed",
                        "error": str(e),
                    })
            else:
                track["error"] = "Not found on YouTube Music"
                failed_tracks.append(track)
                self._emit(progress_callback, {
                    "type": "track",
                    "index": idx,
                    "total": total,
                    "title": track["title"],
                    "artist": track["artist"],
                    "status": "failed",
                    "error": track["error"],
                })

            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        # Retry unmatched tracks using title only
        if failed_tracks:
            if not quiet:
                print(f"\nRetrying {len(failed_tracks)} failed tracks...")
            self._emit(progress_callback, {
                "type": "retry_start",
                "count": len(failed_tracks),
            })
            still_failed = []
            retry_total = len(failed_tracks)
            for idx, track in enumerate(tqdm(failed_tracks, desc="Retrying", unit="song", disable=quiet), 1):
                video_id = self.search_ytmusic_track(track["title"])
                added_on_retry = False
                if video_id:
                    try:
                        self.yt.add_playlist_items(yt_playlist_id, [video_id])
                        added_count += 1
                        added_on_retry = True
                    except Exception:
                        pass
                if added_on_retry:
                    self._emit(progress_callback, {
                        "type": "retry_track",
                        "index": idx,
                        "total": retry_total,
                        "title": track["title"],
                        "artist": track["artist"],
                        "status": "added",
                    })
                else:
                    still_failed.append(track)
                    self._emit(progress_callback, {
                        "type": "retry_track",
                        "index": idx,
                        "total": retry_total,
                        "title": track["title"],
                        "artist": track["artist"],
                        "status": "failed",
                    })
            failed_tracks = still_failed

        if failed_tracks:
            with open("failed_tracks.txt", "w", encoding="utf-8") as f:
                for t in failed_tracks:
                    f.write(f"{t['query']} | Reason: {t.get('error', 'Unknown')}\n")
            if not quiet:
                print(f"\n{len(failed_tracks)} track(s) failed. See failed_tracks.txt.")
        elif not quiet:
            print(f"\nTransferred all {added_count} tracks.")

        result = {
            "playlist_id": yt_playlist_id,
            "added": added_count,
            "failed": failed_tracks,
            "total": total,
        }
        self._emit(progress_callback, {"type": "complete", **result})
        return result
