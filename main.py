#!/usr/bin/env python3
"""
Spotify to YouTube Music Playlist Transfer Tool.
"""

import os
import sys
import argparse
from dotenv import load_dotenv

from migrator import PlaylistMigrator
from auth_setup import test_spotify, get_ytmusic_instance

load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Transfer playlists and liked songs from Spotify to YouTube Music."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-p", "--playlist",
        help="Spotify playlist URL, URI, or ID to transfer"
    )
    group.add_argument(
        "-l", "--liked",
        action="store_true",
        help="Transfer all Spotify 'Liked Songs' to YouTube Music"
    )
    group.add_argument(
        "-a", "--all",
        action="store_true",
        help="Transfer all public & private playlists from your Spotify account"
    )
    parser.add_argument(
        "-n", "--name",
        help="Custom name for the created YouTube Music playlist (defaults to Spotify name)"
    )
    parser.add_argument(
        "--privacy",
        choices=["PRIVATE", "PUBLIC", "UNLISTED"],
        default="PRIVATE",
        help="Privacy status of the created YouTube playlist (default: PRIVATE)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between song additions to prevent rate limits (default: 0.5s)"
    )
    return parser.parse_args()


def interactive_menu(sp, migrator):
    print("\nSelect an action:")
    print(" [1] Transfer a single Spotify playlist by link/ID")
    print(" [2] Transfer all 'Liked Songs' from Spotify")
    print(" [3] Transfer all playlists from my Spotify account")
    print(" [4] Exit")

    choice = input("\nEnter choice (1-4): ").strip()
    if choice == "1":
        link = input("Paste Spotify playlist link or ID: ").strip()
        if not link:
            print("No link provided. Aborting.")
            return
        transfer_single_playlist(sp, migrator, link)
    elif choice == "2":
        transfer_liked_songs(migrator)
    elif choice == "3":
        transfer_all_playlists(sp, migrator)
    else:
        print("Goodbye!")
        sys.exit(0)


def transfer_single_playlist(sp, migrator, playlist_input, custom_name=None, privacy="PRIVATE"):
    playlist_id = PlaylistMigrator.extract_spotify_id(playlist_input)
    try:
        sp_playlist = sp.playlist(playlist_id)
        name = custom_name or sp_playlist.get("name", "Transferred Spotify Playlist")
        desc = sp_playlist.get("description") or "Imported from Spotify"
    except Exception as e:
        print(f"❌ Failed to fetch playlist from Spotify: {e}")
        return

    print(f"\n📂 Spotify Playlist: '{name}' (ID: {playlist_id})")
    tracks = migrator.get_playlist_tracks(playlist_id)
    print(f"📊 Found {len(tracks)} songs.")

    if not tracks:
        print("No songs found in playlist. Skipping.")
        return

    migrator.transfer_tracks(tracks, yt_playlist_name=name, yt_playlist_desc=desc, privacy_status=privacy)


def transfer_liked_songs(migrator, custom_name=None, privacy="PRIVATE"):
    print("\n❤️  Fetching your Spotify 'Liked Songs'...")
    tracks = migrator.get_liked_songs()
    print(f"📊 Total liked songs found: {len(tracks)}")

    if not tracks:
        print("No liked songs found. Skipping.")
        return

    name = custom_name or "Spotify Liked Songs"
    desc = "Imported from Spotify Liked Songs collection"
    migrator.transfer_tracks(tracks, yt_playlist_name=name, yt_playlist_desc=desc, privacy_status=privacy)


def transfer_all_playlists(sp, migrator, privacy="PRIVATE"):
    print("\n📋 Fetching your Spotify playlists...")
    playlists = []
    results = sp.current_user_playlists()

    while results:
        playlists.extend(results.get("items", []))
        if results.get("next"):
            results = sp.next(results)
        else:
            break

    print(f"Found {len(playlists)} playlists in your account.")
    for idx, p in enumerate(playlists, 1):
        name = p["name"]
        p_id = p["id"]
        print(f"\n[{idx}/{len(playlists)}] Processing: '{name}'...")
        tracks = migrator.get_playlist_tracks(p_id)
        if not tracks:
            print("  Empty playlist. Skipping.")
            continue
        migrator.transfer_tracks(
            tracks,
            yt_playlist_name=name,
            yt_playlist_desc=p.get("description") or "Imported from Spotify",
            privacy_status=privacy
        )


def main():
    args = parse_args()

    print("=" * 60)
    print("🎵 Spotify -> YouTube Music Transfer CLI")
    print("=" * 60)

    # Check Spotify
    sp = test_spotify()
    if not sp:
        print("\nPlease configure your Spotify credentials in .env first.")
        sys.exit(1)

    # Check YouTube Music
    yt, info = get_ytmusic_instance()
    if not yt:
        print(f"\n❌ YouTube Music authentication failed ({info}).")
        print("Please run `python auth_setup.py` to authenticate with YouTube Music.")
        sys.exit(1)

    migrator = PlaylistMigrator(sp, yt, rate_limit_delay=args.delay)

    if args.playlist:
        transfer_single_playlist(sp, migrator, args.playlist, args.name, args.privacy)
    elif args.liked:
        transfer_liked_songs(migrator, args.name, args.privacy)
    elif args.all:
        transfer_all_playlists(sp, migrator, args.privacy)
    else:
        interactive_menu(sp, migrator)


if __name__ == "__main__":
    main()
