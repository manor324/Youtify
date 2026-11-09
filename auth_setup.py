"""
Authentication setup & verification helper for Spotify and YouTube Music.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()


def test_spotify():
    """Verify Spotify credentials and login."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8080")

    if not client_id or not client_secret or "your_spotify" in client_id:
        print("❌ Spotify credentials missing or incomplete in .env!")
        print("   Please edit .env and provide SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET.")
        return None

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        scope = "playlist-read-private playlist-modify-private user-library-read"
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        ))
        user = sp.current_user()
        print(f"✅ Spotify Auth Success! Logged in as: {user.get('display_name')} (ID: {user.get('id')})")
        return sp
    except Exception as e:
        print(f"❌ Spotify Auth Failed: {e}")
        return None


def get_ytmusic_instance():
    """Initialize YTMusic using either OAuth or Browser headers."""
    auth_file = os.getenv("YTM_AUTH_FILE", "oauth.json")
    if not os.path.exists(auth_file):
        # Also check for browser.json fallback
        if os.path.exists("browser.json"):
            auth_file = "browser.json"
        else:
            return None, auth_file

    try:
        from ytmusicapi import YTMusic, OAuthCredentials

        client_id = os.getenv("YTM_CLIENT_ID")
        client_secret = os.getenv("YTM_CLIENT_SECRET")

        if client_id and client_secret and auth_file.endswith(".json"):
            yt = YTMusic(auth_file, oauth_credentials=OAuthCredentials(client_id=client_id, client_secret=client_secret))
        else:
            yt = YTMusic(auth_file)

        return yt, auth_file
    except Exception as e:
        return None, str(e)


def test_ytmusic():
    """Verify YouTube Music authentication."""
    yt, info = get_ytmusic_instance()
    if not yt:
        if not os.path.exists(info):
            print(f"⚠️ YouTube Music auth file '{info}' not found.")
        else:
            print(f"❌ YouTube Music Auth Failed: {info}")
            print("\n💡 Common OAuth fixes:")
            print("   - If using Google OAuth, make sure the consent screen status is 'In Production' (not Testing),")
            print("     otherwise tokens expire strictly every 7 days.")
            print("   - You can re-run `python auth_setup.py` to refresh your token.")
        return None

    try:
        results = yt.search("test", filter="songs", limit=1)
        print(f"✅ YouTube Music Auth Success! Loaded credentials from '{info}'.")
        return yt
    except Exception as e:
        print(f"❌ YouTube Music Auth Error: {e}")
        return None


def setup_ytmusic_interactive():
    print("\nYouTube Music supports two authentication methods:")
    print("  [1] Google OAuth (TV/Device Flow - requires Google Cloud Client ID/Secret)")
    print("  [2] Browser Headers (Copy-paste headers from DevTools - no Google Cloud setup needed)")
    
    choice = input("\nChoose auth method (1 or 2): ").strip()

    if choice == "1":
        client_id = os.getenv("YTM_CLIENT_ID") or input("Enter Google Cloud OAuth Client ID: ").strip()
        client_secret = os.getenv("YTM_CLIENT_SECRET") or input("Enter Google Cloud OAuth Client Secret: ").strip()
        auth_file = os.getenv("YTM_AUTH_FILE", "oauth.json")

        if not client_id or not client_secret:
            print("❌ Client ID and Client Secret are required for OAuth.")
            return

        try:
            from ytmusicapi import setup_oauth
            print(f"\nInitiating OAuth device flow (saving to '{auth_file}')...")
            setup_oauth(client_id=client_id, client_secret=client_secret, filepath=auth_file)
            print(f"✅ Successfully created '{auth_file}'!")
        except Exception as e:
            print(f"❌ OAuth setup failed: {e}")

    elif choice == "2":
        try:
            from ytmusicapi import YTMusic
            print("\nFollow instructions in the browser to extract YouTube Music headers:")
            print("1. Open https://music.youtube.com in your browser (logged in).")
            print("2. Open Developer Tools (F12) -> Network tab.")
            print("3. Look for any POST request (e.g. 'browse' or 'next') and copy Request Headers.")
            YTMusic.setup(filepath="browser.json")
            print("✅ Successfully created 'browser.json'!")
        except Exception as e:
            print(f"❌ Browser setup failed: {e}")


def main():
    print("=" * 60)
    print("🎵 Spotify to YouTube Music - Authentication Setup & Test")
    print("=" * 60)

    print("\n[1/2] Checking Spotify Authentication...")
    sp = test_spotify()

    print("\n[2/2] Checking YouTube Music Authentication...")
    yt = test_ytmusic()

    if not yt:
        setup_choice = input("\nWould you like to set up YouTube Music credentials now? (y/n): ").strip().lower()
        if setup_choice == "y":
            setup_ytmusic_interactive()
            print("\nRe-testing YouTube Music connection...")
            test_ytmusic()


if __name__ == "__main__":
    main()
