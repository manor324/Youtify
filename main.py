#!/usr/bin/env python3
"""
CLI for transferring playlists and liked songs from Spotify to YouTube Music.
"""

import argparse
import sys
from dotenv import load_dotenv

from auth_setup import get_ytmusic_instance, test_spotify
from migrator import PlaylistMigrator

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
        help="Transfer all Spotify Liked Songs to YouTube Music"
    )
    group.add_argument(
        "-a", "--all",
        action="store_true",
        help="Transfer all public and private playlists from your Spotify account"
    )
    parser.add_argument(
        "-n", "--name",
        help="Custom name for the created YouTube Music playlist"
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
        help="Delay in seconds between song additions (default: 0.5)"
    )
    return parser.parse_args()


def interactive_menu(sp, migrator):
    print("\nSelect an action:")
    print("  [1] Transfer a single Spotify playlist by link/ID")
    print("  [2] Transfer all Liked Songs from Spotify")
    print("  [3] Transfer all playlists from your Spotify account")
    print("  [4] Exit")

    choice = input("\nChoice (1-4): ").strip()
    if choice == "1":
        link = input("Spotify playlist link or ID: ").strip()
        if not link:
            print("No link provided.")
            return
        transfer_single_playlist(sp, migrator, link)
    elif choice == "2":
        transfer_liked_songs(migrator)
    elif choice == "3":
        transfer_all_playlists(sp, migrator)
    else:
        sys.exit(0)


def transfer_single_playlist(sp, migrator, playlist_input, custom_name=None, privacy="PRIVATE"):
    playlist_id = PlaylistMigrator.extract_spotify_id(playlist_input)
    try:
        sp_playlist = sp.playlist(playlist_id)
        name = custom_name or sp_playlist.get("name", "Transferred Spotify Playlist")
        desc = sp_playlist.get("description") or "Imported from Spotify"
    except Exception as e:
        print(f"Failed to fetch playlist from Spotify: {e}")
        return

    print(f"\nPlaylist: '{name}' ({playlist_id})")
    tracks = migrator.get_playlist_tracks(playlist_id)
    print(f"Found {len(tracks)} songs.")

    if not tracks:
        print("Empty playlist, skipping.")
        return

    migrator.transfer_tracks(tracks, yt_playlist_name=name, yt_playlist_desc=desc, privacy_status=privacy)


def transfer_liked_songs(migrator, custom_name=None, privacy="PRIVATE"):
    print("\nFetching Spotify Liked Songs...")
    tracks = migrator.get_liked_songs()
    print(f"Found {len(tracks)} liked songs.")

    if not tracks:
        print("No liked songs found, skipping.")
        return

    name = custom_name or "Spotify Liked Songs"
    migrator.transfer_tracks(
        tracks,
        yt_playlist_name=name,
        yt_playlist_desc="Imported from Spotify Liked Songs",
        privacy_status=privacy,
    )


def transfer_all_playlists(sp, migrator, privacy="PRIVATE"):
    print("\nFetching Spotify playlists...")
    playlists = migrator.get_user_playlists()

    print(f"Found {len(playlists)} playlists.")
    for idx, p in enumerate(playlists, 1):
        name = p["name"]
        print(f"\n[{idx}/{len(playlists)}] '{name}'")
        tracks = migrator.get_playlist_tracks(p["id"])
        if not tracks:
            print("Empty playlist, skipping.")
            continue
        migrator.transfer_tracks(
            tracks,
            yt_playlist_name=name,
            yt_playlist_desc=p.get("description") or "Imported from Spotify",
            privacy_status=privacy,
        )


def main():
    args = parse_args()

    sp = test_spotify()
    if not sp:
        print("Configure Spotify credentials in .env first.")
        sys.exit(1)

    yt, info = get_ytmusic_instance()
    if not yt:
        print(f"YouTube Music authentication failed ({info}). Run `python auth_setup.py` first.")
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
