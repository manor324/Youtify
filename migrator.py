"""
Core migration engine: transfers playlists and liked songs from Spotify to YouTube Music.
"""

import time
import re
from typing import List, Dict, Optional
from tqdm import tqdm


class PlaylistMigrator:
    def __init__(self, sp_client, yt_client, rate_limit_delay: float = 0.5):
        self.sp = sp_client
        self.yt = yt_client
        self.rate_limit_delay = rate_limit_delay

    @staticmethod
    def extract_spotify_id(playlist_input: str) -> str:
        """Extracts playlist ID from URI, URL, or raw ID."""
        playlist_input = playlist_input.strip()
        # Case: spotify:playlist:6zV3IVldsAYns53vK9CQGQ
        if playlist_input.startswith("spotify:playlist:"):
            return playlist_input.split(":")[-1]
        # Case: https://open.spotify.com/playlist/6zV3IVldsAYns53vK9CQGQ?si=...
        match = re.search(r"playlist/([a-zA-Z0-9]+)", playlist_input)
        if match:
            return match.group(1)
        # Raw ID
        return playlist_input

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Fetch all tracks from a Spotify playlist, handling pagination."""
        tracks = []
        results = self.sp.playlist_tracks(playlist_id)

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
                    "query": f"{name} {artists}".strip()
                })

            if results.get("next"):
                results = self.sp.next(results)
            else:
                break

        return tracks

    def get_liked_songs(self) -> List[Dict]:
        """Fetch all Liked Songs for the authenticated Spotify user."""
        tracks = []
        results = self.sp.current_user_saved_tracks(limit=50)

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
                    "query": f"{name} {artists}".strip()
                })

            if results.get("next"):
                results = self.sp.next(results)
            else:
                break

        return tracks

    def search_ytmusic_track(self, query: str) -> Optional[str]:
        """Search YouTube Music for a track, first in songs, then videos."""
        # 1. Try songs filter
        try:
            results = self.yt.search(query, filter="songs")
            if results and len(results) > 0 and "videoId" in results[0]:
                return results[0]["videoId"]
        except Exception:
            pass

        # 2. Fallback to videos filter
        try:
            results = self.yt.search(query, filter="videos")
            if results and len(results) > 0 and "videoId" in results[0]:
                return results[0]["videoId"]
        except Exception:
            pass

        return None

    def transfer_tracks(
        self,
        tracks: List[Dict],
        yt_playlist_name: str,
        yt_playlist_desc: str = "Imported from Spotify",
        privacy_status: str = "PRIVATE"
    ) -> Dict:
        """
        Creates a playlist on YouTube Music, searches and adds matching tracks.
        Returns a dict containing summary metrics and list of failed tracks.
        """
        print(f"\n▶ Creating YouTube Music playlist: '{yt_playlist_name}'...")
        try:
            yt_playlist_id = self.yt.create_playlist(
                title=yt_playlist_name[:150],
                description=yt_playlist_desc,
                privacy_status=privacy_status
            )
            print(f"✅ Playlist created! ID: {yt_playlist_id}")
        except Exception as e:
            print(f"❌ Failed to create playlist on YouTube Music: {e}")
            return {"playlist_id": None, "added": 0, "failed": tracks}

        added_count = 0
        failed_tracks = []

        print(f"⏳ Transferring {len(tracks)} songs...")
        pbar = tqdm(tracks, desc="Migrating", unit="song")

        for track in pbar:
            query = track["query"]
            video_id = self.search_ytmusic_track(query)

            if video_id:
                try:
                    self.yt.add_playlist_items(yt_playlist_id, [video_id])
                    added_count += 1
                except Exception as e:
                    track["error"] = str(e)
                    failed_tracks.append(track)
            else:
                track["error"] = "Not found on YouTube Music"
                failed_tracks.append(track)

            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        # Retry pass for failed tracks
        if failed_tracks:
            print(f"\n🔄 Attempting retry for {len(failed_tracks)} failed tracks...")
            still_failed = []
            for track in tqdm(failed_tracks, desc="Retrying", unit="song"):
                query = track["title"]  # try title only without artists as simpler fallback
                video_id = self.search_ytmusic_track(query)
                if video_id:
                    try:
                        self.yt.add_playlist_items(yt_playlist_id, [video_id])
                        added_count += 1
                        continue
                    except Exception:
                        pass
                still_failed.append(track)
            failed_tracks = still_failed

        # Log failed tracks to file
        if failed_tracks:
            with open("failed_tracks.txt", "w", encoding="utf-8") as f:
                for t in failed_tracks:
                    f.write(f"{t['query']} | Reason: {t.get('error', 'Unknown')}\n")
            print(f"\n⚠️  {len(failed_tracks)} track(s) could not be transferred.")
            print("   Details written to 'failed_tracks.txt'.")
        else:
            print(f"\n🎉 All {added_count} tracks transferred successfully with 0 failures!")

        return {
            "playlist_id": yt_playlist_id,
            "added": added_count,
            "failed": failed_tracks,
            "total": len(tracks)
        }
