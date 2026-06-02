# migshazam

Identify the songs in a DJ mix. Point it at a YouTube/SoundCloud link (or a local
audio file) and it slides a short window across the mix, fingerprints each window
with Shazam (via [ShazamIO](https://github.com/shazamio/ShazamIO)), and returns the
distinct set of songs it could recognize — with rough timestamps and a confidence
count per track.

The goal is **coverage** — identify as many songs as possible — not frame-accurate
boundaries. DJ transitions are blends, so timestamps are approximate (window
granularity); the value is the list of songs and roughly where each one is "in the
clear."

## What it does / doesn't do

- ✅ Free: uses ShazamIO, no API keys.
- ✅ YouTube + SoundCloud ingest via `yt-dlp`, plus any local file.
- ✅ Rescues pitched tracks with an optional **varispeed grid-search** (`--grid`):
  DJ pitch faders move tempo + pitch together, which breaks raw Shazam matching, so
  on a miss we re-query the window at a few speed factors.
- ⚠️ **Catalog ceiling**: unreleased dubs / white-labels / bootleg edits are in no
  Shazam database and will never be identified — they show up as gaps, not songs.
- ⚠️ ShazamIO talks to Shazam's *unofficial* endpoint (IP rate-limited, gray-area,
  can break). We self-throttle (~12 req/min) and back off on errors.

## Setup

ShazamIO's native core (`shazamio-core`) only ships macOS-arm64 wheels for
**Python 3.10–3.12**, so create the venv with 3.12:

Dependencies are managed with [uv](https://docs.astral.sh/uv/). `uv sync` reads
`requires-python` (pinned `<3.13`) and creates the `.venv` for you:

```bash
cd ~/projects/migshazam
uv sync
```

You also need:

- **ffmpeg** (audio slicing) — already on this machine (`ffmpeg 8.0.1`).
- A **JavaScript runtime** for YouTube downloads. `brew install deno` is the
  simplest. (SoundCloud and local files don't need it.)

## Usage

Run via `uv run` (or activate the venv and call `migshazam` directly):

```bash
# YouTube or SoundCloud link
uv run migshazam "https://www.youtube.com/watch?v=..."

# Local file, denser sampling + pitched-track rescue
uv run migshazam mix.mp3 --hop 20 --grid

# Only the first 10 minutes (good for a quick check on a long mix)
uv run migshazam "<url>" --end 10:00

# Gated YouTube video needing cookies
uv run migshazam "<url>" --ytdlp-arg=--cookies-from-browser=chrome
```

Outputs `<name>.tracklist.json` and `<name>.tracklist.md`, and prints the list to
the console. Progress (one line per window) goes to stderr.

### Key options

| Flag | Default | Meaning |
|------|---------|---------|
| `--hop` | `30` | seconds between windows; lower = more coverage, more requests |
| `--start` / `--end` | full | scan only a slice; accepts seconds or `mm:ss` / `h:mm:ss` |
| `--window` | `12` | window length (≤12s; Shazam rejects ≥15s) |
| `--rate` | `12` | max Shazam requests/min (raising risks HTTP 429) |
| `--grid` | off | varispeed-rescue missed windows (tries all speeds, keeps the most-agreed match) |
| `--grid-steps` | `0.94,0.97,1.03,1.06` | speed factors for `--grid` |
| `--grid-min-rms` | `0.02` | skip the grid on near-silent windows (`0` disables) |
| `--min-matches` | `2` | drop songs seen in fewer than N windows (single hits are usually wrong) |
| `--audd` | off | fall back to AudD on unidentified gaps (needs `AUDD_API_TOKEN`) |
| `--audd-gap-min` | `60` | only probe AudD on gaps at least this many seconds long |

A 60-min mix at `--hop 30` is ~120 windows ≈ ~10 min at the default rate (the rate
limit, not the audio, is the bottleneck). `--grid` multiplies requests on misses.

### Filling Shazam's gaps with AudD (optional)

Some tracks just aren't in Shazam's catalog (different pressings/versions, obscure
artists) — no amount of pitch/tempo correction recovers them. `--audd` runs
[AudD](https://audd.io) (a different catalog) **only on the gaps Shazam left**,
probing a few short clips per unidentified stretch, so it stays cheap. AudD-found
tracks are kept even on a single hit and tagged `via AudD` in the output.

**Getting a token:** sign up at <https://dashboard.audd.io/> (free tier: 300
requests, no card needed). Put it in a gitignored `.env` at the project root:

```
AUDD_API_TOKEN=your_token_here
```

(or export `AUDD_API_TOKEN`, or pass `--audd-token ...`). Then:

```bash
uv run migshazam "<url>" --grid --audd
```

**It's optional and degrades gracefully.** migshazam runs Shazam-only unless you
pass `--audd`. If the token is missing/invalid or you run out of AudD requests, it
prints a warning and finishes with the Shazam results — the run never fails:

```
WARNING: AudD fallback unavailable (...the provided api_token is incorrect...);
continuing with Shazam results only.
```

## How it's structured

```
ingest.py     yt-dlp download (URL -> local file)
audioio.py    ffmpeg: probe duration, extract mono windows (+ varispeed)
recognize.py  ShazamIO wrapper: throttle + retry/backoff + parse
scan.py       slide window across the mix, grid-search on misses; find_gaps()
cluster.py    group detections into distinct songs (by Shazam track key)
audd.py       AudD fallback backend for unidentified gaps
output.py     console / JSON / Markdown
cli.py        glue
```

Shazam (free, primary) and AudD (paid catalog, gap fallback) sit behind the same
detection model, so additional backends (e.g. ACRCloud) could be slotted in the
same way if catalog coverage demands it.

## Development

```bash
uv run pytest        # unit tests (deterministic logic; no network)
uv run ruff check .  # lint
```

Dev dependencies (`pytest`, `ruff`) live in the `dev` dependency group and are
installed by `uv sync`. The tests cover the pure logic — clustering, grid
arbitration, response parsing, the energy gate, time parsing — and skip anything
that needs the Shazam network or (for the windowing test) ffmpeg if it's absent.
