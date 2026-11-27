#!/usr/bin/env python3
"""
FastAPI web frontend server for the Spotify -> YouTube Music migrator.
Run with: python web.py
"""

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth_setup import (
    build_spotify_auth_manager,
    get_spotify_client_nonblocking,
    get_ytmusic_status,
    has_spotify_credentials,
)
from migrator import PlaylistMigrator

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Spotify to YouTube Music Migrator", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory job tracker: job_id -> {"history": list, "done": bool}
jobs: Dict[str, Dict] = {}
jobs_lock = threading.Lock()


class SpotifyCallbackRequest(BaseModel):
    redirect_url: str = Field(..., min_length=1)


class YTMusicBrowserRequest(BaseModel):
    headers_raw: str = Field(..., min_length=10)


class PlaylistPreviewRequest(BaseModel):
    playlist: str = Field(..., min_length=1)


class TransferRequest(BaseModel):
    mode: Literal["playlist", "liked", "all"]
    playlist: Optional[str] = None
    custom_name: Optional[str] = None
    privacy: Literal["PRIVATE", "PUBLIC", "UNLISTED"] = "PRIVATE"
    delay: float = Field(default=0.5, ge=0.0, le=10.0)


def _push_job_event(job_id: str, event: Dict) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["history"].append(event)


def _finish_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["done"] = True


def _run_transfer_job(job_id: str, sp, yt, req: TransferRequest) -> None:
    migrator = PlaylistMigrator(sp, yt, rate_limit_delay=req.delay)

    def on_progress(evt: Dict) -> None:
        _push_job_event(job_id, evt)

    try:
        if req.mode == "playlist":
            if not req.playlist:
                _push_job_event(job_id, {"type": "error", "message": "No playlist URL or ID provided."})
                return
            playlist_id = PlaylistMigrator.extract_spotify_id(req.playlist)
            _push_job_event(job_id, {"type": "status", "message": f"Fetching Spotify playlist ({playlist_id})..."})
            sp_playlist = sp.playlist(playlist_id)
            name = (req.custom_name or "").strip() or sp_playlist.get("name", "Transferred Spotify Playlist")
            desc = sp_playlist.get("description") or "Imported from Spotify"
            tracks = migrator.get_playlist_tracks(playlist_id)
            if not tracks:
                _push_job_event(job_id, {"type": "error", "message": "This Spotify playlist has 0 playable tracks."})
                return
            migrator.transfer_tracks(
                tracks,
                yt_playlist_name=name,
                yt_playlist_desc=desc,
                privacy_status=req.privacy,
                progress_callback=on_progress,
            )

        elif req.mode == "liked":
            _push_job_event(job_id, {"type": "status", "message": "Fetching your Spotify Liked Songs..."})
            tracks = migrator.get_liked_songs()
            if not tracks:
                _push_job_event(job_id, {"type": "error", "message": "No Liked Songs found in your Spotify library."})
                return
            name = (req.custom_name or "").strip() or "Spotify Liked Songs"
            migrator.transfer_tracks(
                tracks,
                yt_playlist_name=name,
                yt_playlist_desc="Imported from Spotify Liked Songs collection",
                privacy_status=req.privacy,
                progress_callback=on_progress,
            )

        elif req.mode == "all":
            _push_job_event(job_id, {"type": "status", "message": "Fetching all playlists from your Spotify account..."})
            playlists = migrator.get_user_playlists()
            if not playlists:
                _push_job_event(job_id, {"type": "error", "message": "No playlists found in your Spotify account."})
                return

            summary: List[Dict] = []
            total_pl = len(playlists)
            for idx, p in enumerate(playlists, 1):
                _push_job_event(job_id, {
                    "type": "batch_playlist",
                    "index": idx,
                    "total_playlists": total_pl,
                    "name": p["name"],
                })
                tracks = migrator.get_playlist_tracks(p["id"])
                if not tracks:
                    continue
                res = migrator.transfer_tracks(
                    tracks,
                    yt_playlist_name=p["name"],
                    yt_playlist_desc=p["description"] or "Imported from Spotify",
                    privacy_status=req.privacy,
                    progress_callback=on_progress,
                )
                summary.append({
                    "name": p["name"],
                    "playlist_id": res.get("playlist_id"),
                    "added": res.get("added", 0),
                    "total": res.get("total", 0),
                    "failed_count": len(res.get("failed", [])),
                })

            _push_job_event(job_id, {"type": "batch_complete", "playlists": summary})

    except Exception as e:
        _push_job_event(job_id, {"type": "error", "message": str(e)})
    finally:
        _finish_job(job_id)


@app.get("/")
def serve_index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/status")
def api_status():
    _, sp_status = get_spotify_client_nonblocking()
    _, yt_status = get_ytmusic_status()
    return {"spotify": sp_status, "ytmusic": yt_status}


@app.get("/api/auth/spotify/url")
def api_spotify_auth_url():
    if not has_spotify_credentials():
        raise HTTPException(
            status_code=400,
            detail="SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be configured in .env first.",
        )
    auth_manager = build_spotify_auth_manager(open_browser=False)
    return {"url": auth_manager.get_authorize_url()}


@app.post("/api/auth/spotify/callback")
def api_spotify_auth_callback(payload: SpotifyCallbackRequest):
    if not has_spotify_credentials():
        raise HTTPException(status_code=400, detail="Spotify credentials missing in .env.")
    try:
        auth_manager = build_spotify_auth_manager(open_browser=False)
        raw = payload.redirect_url.strip()
        code = auth_manager.parse_response_code(raw) if "code=" in raw else raw
        auth_manager.get_access_token(code, as_dict=True, check_cache=False)
        sp, status = get_spotify_client_nonblocking()
        if not sp:
            raise HTTPException(status_code=400, detail=status.get("message", "Failed to verify Spotify token."))
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Spotify authorization failed: {e}")


@app.post("/api/auth/ytmusic/browser")
def api_ytmusic_browser_setup(payload: YTMusicBrowserRequest):
    try:
        import ytmusicapi
        ytmusicapi.setup(filepath=str(BASE_DIR / "browser.json"), headers_raw=payload.headers_raw.strip())
        _, status = get_ytmusic_status()
        if not status.get("connected"):
            raise HTTPException(status_code=400, detail=status.get("message", "Saved headers could not authenticate."))
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid browser headers: {e}")


@app.get("/api/playlists")
def api_get_playlists():
    sp, sp_status = get_spotify_client_nonblocking()
    if not sp:
        raise HTTPException(status_code=401, detail=sp_status.get("message", "Spotify not connected."))

    try:
        migrator = PlaylistMigrator(sp, None)
        playlists = migrator.get_user_playlists()
        saved = sp.current_user_saved_tracks(limit=1)
        liked_total = saved.get("total", 0) if saved else 0
        return {"liked_total": liked_total, "playlists": playlists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load Spotify library: {e}")


@app.post("/api/preview")
def api_preview_playlist(payload: PlaylistPreviewRequest):
    sp, sp_status = get_spotify_client_nonblocking()
    if not sp:
        raise HTTPException(status_code=401, detail=sp_status.get("message", "Spotify not connected."))

    playlist_id = PlaylistMigrator.extract_spotify_id(payload.playlist)
    try:
        p = sp.playlist(playlist_id)
        images = p.get("images") or []
        tracks_info = p.get("tracks") or {}
        owner = p.get("owner") or {}
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "description": p.get("description") or "",
            "owner": owner.get("display_name") or owner.get("id") or "Unknown",
            "track_count": tracks_info.get("total", 0),
            "image_url": images[0].get("url") if images else None,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch playlist '{playlist_id}': {e}")


@app.post("/api/transfer")
def api_start_transfer(req: TransferRequest):
    sp, sp_status = get_spotify_client_nonblocking()
    if not sp:
        raise HTTPException(status_code=401, detail=sp_status.get("message", "Spotify not connected."))

    yt, yt_status = get_ytmusic_status()
    if not yt:
        raise HTTPException(status_code=401, detail=yt_status.get("message", "YouTube Music not connected."))

    job_id = uuid.uuid4().hex[:12]
    with jobs_lock:
        jobs[job_id] = {
            "history": [],
            "done": False,
        }

    thread = threading.Thread(
        target=_run_transfer_job,
        args=(job_id, sp, yt, req),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/transfer/{job_id}/stream")
async def api_stream_transfer(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Transfer job not found.")

    async def event_generator():
        cursor = 0
        heartbeat_ticks = 0
        while True:
            with jobs_lock:
                batch = job["history"][cursor:]
                is_done = job["done"]

            if batch:
                heartbeat_ticks = 0
                for evt in batch:
                    yield f"data: {json.dumps(evt)}\n\n"
                    cursor += 1
            elif is_done:
                yield "event: end\ndata: {}\n\n"
                break
            else:
                heartbeat_ticks += 1
                if heartbeat_ticks >= 150:
                    yield ": keep-alive\n\n"
                    heartbeat_ticks = 0
                await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/failed-tracks")
def api_failed_tracks():
    failed_path = BASE_DIR / "failed_tracks.txt"
    if not failed_path.exists():
        return PlainTextResponse("No failed tracks logged.", status_code=200)
    return FileResponse(
        str(failed_path),
        media_type="text/plain",
        filename="failed_tracks.txt",
    )


if __name__ == "__main__":
    print("Spotify -> YouTube Music Web UI: http://127.0.0.1:8000")
    uvicorn.run("web:app", host="127.0.0.1", port=8000, reload=False)
