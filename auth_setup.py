"""
Authentication setup and status verification for Spotify and YouTube Music.
"""

import os
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_SCOPE = "playlist-read-private playlist-modify-private user-library-read"


def get_spotify_config() -> Tuple[Optional[str], Optional[str], str]:
    load_dotenv(override=True)
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8080")
    return client_id, client_secret, redirect_uri


def has_spotify_credentials() -> bool:
    client_id, client_secret, _ = get_spotify_config()
    return bool(client_id and client_secret and "your_spotify" not in client_id)


def build_spotify_auth_manager(open_browser: bool = True):
    from spotipy.oauth2 import SpotifyOAuth

    client_id, client_secret, redirect_uri = get_spotify_config()
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SPOTIFY_SCOPE,
        open_browser=open_browser,
    )


def get_spotify_client_nonblocking() -> Tuple[Optional[object], Dict]:
    """Load a Spotify client from cached token without blocking on stdin."""
    if not has_spotify_credentials():
        return None, {
            "configured": False,
            "connected": False,
            "user": None,
            "message": "SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET missing in .env",
        }

    try:
        import spotipy
        auth_manager = build_spotify_auth_manager(open_browser=False)
        token_info = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
        if not token_info:
            return None, {
                "configured": True,
                "connected": False,
                "user": None,
                "message": "Not signed in yet. Authorize Spotify to connect.",
            }

        sp = spotipy.Spotify(auth_manager=auth_manager)
        user = sp.current_user()
        return sp, {
            "configured": True,
            "connected": True,
            "user": user.get("display_name") or user.get("id"),
            "user_id": user.get("id"),
            "message": "Connected",
        }
    except Exception as e:
        return None, {
            "configured": True,
            "connected": False,
            "user": None,
            "message": str(e),
        }


def test_spotify():
    """Verify Spotify credentials interactively."""
    if not has_spotify_credentials():
        print("Spotify credentials missing in .env. Copy .env.example to .env and fill them in.")
        return None

    try:
        import spotipy
        auth_manager = build_spotify_auth_manager(open_browser=True)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        user = sp.current_user()
        print(f"Spotify connected: {user.get('display_name')} ({user.get('id')})")
        return sp
    except Exception as e:
        print(f"Spotify auth failed: {e}")
        return None


def get_ytmusic_instance():
    """Initialize YTMusic from OAuth token or browser headers file."""
    load_dotenv(override=True)
    auth_file = os.getenv("YTM_AUTH_FILE", "oauth.json")
    if not os.path.exists(auth_file):
        if os.path.exists("browser.json"):
            auth_file = "browser.json"
        else:
            return None, auth_file

    try:
        from ytmusicapi import YTMusic, OAuthCredentials

        client_id = os.getenv("YTM_CLIENT_ID")
        client_secret = os.getenv("YTM_CLIENT_SECRET")

        if client_id and client_secret and auth_file.endswith(".json") and "browser" not in auth_file:
            yt = YTMusic(auth_file, oauth_credentials=OAuthCredentials(client_id=client_id, client_secret=client_secret))
        else:
            yt = YTMusic(auth_file)

        return yt, auth_file
    except Exception as e:
        return None, str(e)


def get_ytmusic_status() -> Tuple[Optional[object], Dict]:
    """Verify YouTube Music authentication non-interactively."""
    yt, info = get_ytmusic_instance()
    if not yt:
        return None, {
            "connected": False,
            "auth_file": info,
            "message": f"Auth file '{info}' not found." if not os.path.exists(str(info)) else str(info),
        }

    try:
        yt.search("test", filter="songs", limit=1)
        return yt, {
            "connected": True,
            "auth_file": info,
            "message": f"Connected via {info}",
        }
    except Exception as e:
        return None, {
            "connected": False,
            "auth_file": info,
            "message": str(e),
        }


def test_ytmusic():
    """Verify YouTube Music authentication for CLI."""
    yt, status = get_ytmusic_status()
    if not yt:
        info = status["auth_file"]
        if not os.path.exists(str(info)):
            print(f"YouTube Music auth file '{info}' not found.")
        else:
            print(f"YouTube Music auth failed: {status['message']}")
            print("Note: Google OAuth apps in 'Testing' mode expire refresh tokens after 7 days.")
            print("Run `python auth_setup.py` to refresh credentials.")
        return None

    print(f"YouTube Music connected ({status['auth_file']}).")
    return yt


def setup_ytmusic_interactive():
    print("\nYouTube Music auth methods:")
    print("  [1] Google OAuth (requires Google Cloud TV/Limited Input Client ID & Secret)")
    print("  [2] Browser headers (paste raw request headers from DevTools)")

    choice = input("\nChoose auth method (1 or 2): ").strip()

    if choice == "1":
        client_id = os.getenv("YTM_CLIENT_ID") or input("Google Cloud OAuth Client ID: ").strip()
        client_secret = os.getenv("YTM_CLIENT_SECRET") or input("Google Cloud OAuth Client Secret: ").strip()
        auth_file = os.getenv("YTM_AUTH_FILE", "oauth.json")

        if not client_id or not client_secret:
            print("Client ID and Client Secret are required for OAuth.")
            return

        try:
            from ytmusicapi import setup_oauth
            print(f"\nStarting OAuth device flow (saving to '{auth_file}')...")
            setup_oauth(client_id=client_id, client_secret=client_secret, filepath=auth_file)
            print(f"Saved '{auth_file}'.")
        except Exception as e:
            print(f"OAuth setup failed: {e}")

    elif choice == "2":
        try:
            import ytmusicapi
            print("\n1. Open https://music.youtube.com logged in.")
            print("2. Open DevTools (F12) -> Network tab.")
            print("3. Copy request headers from a POST request (e.g. 'browse' or 'next').")
            ytmusicapi.setup(filepath="browser.json")
            print("Saved 'browser.json'.")
        except Exception as e:
            print(f"Browser setup failed: {e}")


def main():
    print("Spotify -> YouTube Music Auth Setup\n")

    print("[1/2] Spotify:")
    test_spotify()

    print("\n[2/2] YouTube Music:")
    yt = test_ytmusic()

    if not yt:
        setup_choice = input("\nSet up YouTube Music credentials now? (y/n): ").strip().lower()
        if setup_choice == "y":
            setup_ytmusic_interactive()
            print("\nRe-testing YouTube Music connection...")
            test_ytmusic()


if __name__ == "__main__":
    main()
