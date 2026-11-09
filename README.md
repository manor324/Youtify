# Spotify to YouTube Music Playlist Migrator

A clean, resilient Python CLI tool to migrate your Spotify playlists and "Liked Songs" directly to YouTube Music.

Built using [`spotipy`](https://github.com/spotipy-dev/spotipy) and [`ytmusicapi`](https://github.com/sigma67/ytmusicapi).

---

## Features

- **Any Playlist Size**: Handles pagination seamlessly (Spotify limits responses to 50–100 tracks per page; this tool retrieves all tracks regardless of playlist length).
- **Liked Songs Support**: Transfers your Spotify "Liked Songs" library (which standard Spotify playlist endpoints don't expose directly).
- **Dual Matching**: Searches YouTube Music's official `songs` catalog first; falls back to `videos` (official music videos/audio) if no direct song entry exists.
- **Auto-Retry & Failure Logging**: Unmatched songs undergo a relaxed retry pass, and any final unresolved items are exported to `failed_tracks.txt`.
- **Anti-Rate-Limiting**: Configurable delay between playlist modifications to keep YouTube from throttling requests.
- **Zero Leaked Secrets**: Strict `.gitignore` and `.env` template so tokens and credentials never get committed to GitHub.

---

## Repository Structure

```text
spotify-to-ytmusic/
├── auth_setup.py      # Verification and setup script for Spotify & YT Music auth
├── migrator.py        # Core transfer engine (search, pagination, retry)
├── main.py            # CLI and interactive menu
├── requirements.txt   # Python dependencies
├── .env.example       # Example configuration file
├── .gitignore         # Prevents accidental token/credential leaks
└── README.md
```

---

## How-to

### 1. Clone the repository & install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/spotify-to-ytmusic.git
cd spotify-to-ytmusic

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

### 2. Configure Spotify Credentials

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and sign in.
2. Click **Create app**:
   - **App name**: `Spotify to YTMusic`
   - **Redirect URI**: `http://127.0.0.1:8080` (Important: Add this exact URI).
   - Select **Web API** under "Which API/SDKs are you planning to use?".
3. Save the app, then go to **Settings** to find your **Client ID** and **Client Secret**.
4. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Open `.env` and fill in your keys:
   ```ini
   SPOTIPY_CLIENT_ID=your_client_id_here
   SPOTIPY_CLIENT_SECRET=your_client_secret_here
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080
   ```

---

### 3. Configure YouTube Music Authentication

Run the setup helper:
```bash
python auth_setup.py
```

This will guide you through connecting your YouTube Music account via OAuth or Browser credentials:

#### ⚠️ Understanding the "7-Day OAuth Expiration" Issue (Why it stops working!)
> If you create a Google Cloud OAuth app for YouTube, Google places it in **"Testing"** mode by default.
> **In "Testing" mode, user refresh tokens expire every 7 days!** After 7 days, your script will suddenly fail with `invalid_grant` or token expired errors.
>
> **How to fix this permanently:**
> 1. Go to [Google Cloud Console](https://console.cloud.google.com/) -> **APIs & Services** -> **OAuth consent screen**.
> 2. Under **Publishing status**, click **"Publish App"** (change from *Testing* to *In Production*).
> 3. You do **not** need to submit it for verification if you only use it with your own account; you just accept the unverified app warning when signing in. Once published, your refresh token will last indefinitely.

Alternatively, if you prefer not using Google Cloud OAuth, you can use the browser header extraction method supported by `ytmusicapi` (see [ytmusicapi documentation](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)).

---

## Usage

### Interactive Mode
Simply run without arguments to get a guided interactive prompt:
```bash
python main.py
```

### Transfer a specific Spotify playlist
Pass the playlist link or ID directly:
```bash
python main.py --playlist "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
```
Or with custom playlist name & privacy:
```bash
python main.py --playlist "37i9dQZF1DXcBWIGoYBM5M" --name "My New Playlist" --privacy UNLISTED
```

### Transfer your Spotify "Liked Songs"
```bash
python main.py --liked
```

### Transfer all playlists in your Spotify account
```bash
python main.py --all
```

### Options:
- `--delay <seconds>`: Pause between tracks to prevent rate limiting (default: `0.5`).
- `--privacy {PRIVATE, PUBLIC, UNLISTED}`: Set visibility of created YouTube playlists (default: `PRIVATE`).

---


