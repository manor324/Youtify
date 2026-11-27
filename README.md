# spotify-to-ytmusic

Migrate Spotify playlists and Liked Songs to YouTube Music, via a local web dashboard or CLI. Built with [spotipy](https://github.com/spotipy-dev/spotipy), [ytmusicapi](https://github.com/sigma67/ytmusicapi), and [FastAPI](https://fastapi.tiangolo.com/).

## What it does

- Paginates through playlists of any size and pulls Liked Songs directly from your Spotify library.
- Searches YouTube Music under `songs` first and falls back to `videos` when a studio track entry isn't available.
- Retries unmatched tracks using title-only search and writes remaining misses to `failed_tracks.txt`.
- Runs either as a local web UI (`web.py`) with live progress streaming or as a CLI (`main.py`).

## Project layout

```text
spotify-to-ytmusic/
├── web.py             FastAPI server and SSE progress stream
├── static/            Tailwind CSS + vanilla JS frontend
├── main.py            CLI entrypoint
├── migrator.py        Playlist fetching, search, and transfer logic
├── auth_setup.py      Spotify and YouTube Music auth helpers
├── tests/             Unit and web API tests
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

### 1. Install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/spotify-to-ytmusic.git
cd spotify-to-ytmusic

python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Spotify API credentials

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:8080` to **Redirect URIs** and enable **Web API**.
3. Copy `.env.example` to `.env` and fill in `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET`:

```bash
cp .env.example .env
```

### 3. YouTube Music authentication

Run the setup script:

```bash
python auth_setup.py
```

You can authenticate with either:
- **Google OAuth** (`oauth.json`): requires a Google Cloud OAuth client ID/secret configured for *TVs and Limited Input devices*.
- **Browser headers** (`browser.json`): paste request headers copied from `music.youtube.com` in browser DevTools. You can also paste these directly inside the web UI modal.

Note on Google OAuth expiration: Google Cloud projects left in **Testing** mode expire refresh tokens after 7 days. If your OAuth token keeps expiring with `invalid_grant`, set the OAuth consent screen publishing status to **In Production** in Google Cloud Console (personal use does not require verification; just click through the unverified app prompt once).

## Usage

### Web UI

```bash
python web.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) to browse your Spotify playlists, transfer Liked Songs, paste any playlist URL, and watch live transfer progress.

### CLI

Interactive prompt:

```bash
python main.py
```

Direct flags:

```bash
# Single playlist by URL, URI, or ID
python main.py --playlist "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
python main.py --playlist "37i9dQZF1DXcBWIGoYBM5M" --name "My Playlist" --privacy UNLISTED

# Liked Songs
python main.py --liked

# All account playlists
python main.py --all
```

Options:
- `--privacy {PRIVATE,PUBLIC,UNLISTED}`: visibility of created YouTube Music playlists (default: `PRIVATE`)
- `--delay <seconds>`: pause between track additions to avoid rate limiting (default: `0.5`)

## Tests

```bash
python -m unittest discover -s tests -v
```
