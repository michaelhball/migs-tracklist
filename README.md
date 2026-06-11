# migshazam

Identify the songs in a DJ mix. Point it at a YouTube/SoundCloud link (or a local
audio file) and it slides a short window across the mix, fingerprints each window
with Shazam (via [ShazamIO](https://github.com/shazamio/ShazamIO)), and returns the
distinct set of songs it could recognize — with rough timestamps and a confidence
count per track.

It optimizes for **coverage** (identifying as many songs as possible) rather than
precise boundaries: DJ transitions are blends, so timestamps are approximate
(window-granularity).

## What it does / doesn't do

- Free, no API key required (Shazam via ShazamIO).
- YouTube + SoundCloud ingest via `yt-dlp`, plus any local file.
- Optional **varispeed grid-search** (`--grid`): re-query missed windows at several
  speed factors to rescue pitch-shifted tracks.
- Optional **AudD fallback** (`--audd`) to identify tracks missing from Shazam's
  catalog (different catalog; needs a token).
- Optional **acoustic verification** (`--verify`): fetches a ~30s preview of each
  claimed track (Apple/Deezer) and aligns it against the mix audio to confirm it
  actually plays there; wrong identifications are flagged `rejected`.
- A free **offset-consistency check** on every run: the positions *within the
  matched track* that Shazam reports should advance like a song playing through —
  songs that fail are flagged in the output as likely misidentifications.
- **Catalog ceiling**: tracks in neither catalog appear as gaps, not songs —
  pitch/tempo correction cannot recover them.
- ShazamIO uses Shazam's *unofficial* endpoint (IP rate-limited, can break); the
  client self-throttles (~12 req/min) and backs off on errors.

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

This creates `.venv` and installs everything. The project pins Python `<3.13`
because `shazamio-core` only ships macOS-arm64 wheels for Python 3.10–3.12; uv
selects a matching interpreter automatically.

Also required:

- **ffmpeg** — audio decoding, slicing, and resampling.
- A **JavaScript runtime** for YouTube downloads (`brew install deno`); not needed
  for SoundCloud or local files.

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

Outputs `<name>.tracklist.json` and `<name>.tracklist.md` (override the prefix with
`--out`), and prints the list to the console. Progress goes to stderr.

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
| `--audd-clip-every` | `45` | AudD probe spacing within a gap (seconds); lower catches more, costs more |
| `--verify` | off | acoustically verify each song against the mix (needs the `verify` extra) |
| `--verify-threshold` | `0.055` | DTW match-cost cutoff for `--verify`; lower is stricter |

A 60-min mix at `--hop 30` is ~120 windows ≈ ~10 min at the default rate (the rate
limit, not the audio, is the bottleneck). `--grid` multiplies requests on misses.

### Filling Shazam's gaps with AudD (optional)

Some tracks just aren't in Shazam's catalog (different pressings/versions, obscure
artists) — no amount of pitch/tempo correction recovers them. `--audd` runs
[AudD](https://audd.io) (a different catalog) **only on the gaps Shazam left**,
probing one short clip roughly every `--audd-clip-every` seconds (default 45) so a
short track inside a long gap isn't stepped over. AudD-found tracks are kept even
on a single hit and tagged `via AudD` in the output.

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

### Verifying the tracklist acoustically (optional)

Shazam/AudD sometimes return plausible-but-wrong matches (wrong version, false
positives on transitions, gap-fill guesses). `--verify` cross-checks every
identified song against the mix audio itself:

1. fetch a ~30s preview of the *claimed* track — from the preview URL Shazam/AudD
   already returned, falling back to the iTunes and Deezer search APIs;
2. align it against the mix around the claimed position with subsequence DTW over
   chroma features — robust to varispeed (±10%+), EQ filtering, crossfade overlap,
   and ±1-semitone key shifts;
3. report a verdict per song: `verified` (preview aligned), `rejected` (it
   didn't — likely wrong), or `unverifiable` (no usable preview could be fetched
   or decoded, common for white labels/bootlegs — distinct from wrong; the JSON's
   `verify_note` says why).

It needs `librosa`, installed via the `verify` extra:

```bash
uv sync --extra verify
uv run migshazam "<url>" --grid --verify
```

Verdicts appear in the console, as a `Verified` column in the Markdown, and as
`verification`/`verify_note` (the raw match cost) in the JSON. Rejected songs are
flagged, not removed — the call is yours.

Independently of `--verify`, every run now records where *within the matched
track* each window hit landed (Shazam's match offset / AudD's timecode). For a
track genuinely playing through the mix these advance linearly; songs that fail
this are tagged `offsets!` in the console, `_(offset mismatch)_` in the Markdown,
and `"offsets_consistent": false` in the JSON — at zero extra cost or requests.

## How it's structured

```
ingest.py     yt-dlp download (URL -> local file)
audioio.py    ffmpeg: probe duration, extract mono windows (+ varispeed), RMS
recognize.py  ShazamIO wrapper: throttle + retry/backoff + parse
scan.py       slide windows across the mix; grid-search on misses; find_gaps()
cluster.py    group detections into distinct songs; merge same-title entries
audd.py       AudD fallback backend for unidentified gaps
verify.py     acoustic verification: preview fetch + chroma-DTW alignment
models.py     Detection / Song data structures (incl. offset-consistency check)
output.py     console / JSON / Markdown
cli.py        argument parsing and orchestration
```

Shazam (primary) and AudD (gap fallback) sit behind the same detection model, so
another backend (e.g. ACRCloud) could be added the same way.

## Development

```bash
uv run pytest        # unit tests (deterministic logic; no network)
uv run ruff check .  # lint
```

Dev dependencies (`pytest`, `ruff`) live in the `dev` dependency group and are
installed by `uv sync`. The tests cover the pure logic — clustering, grid
arbitration, response parsing, the energy gate, time parsing, offset consistency,
and the DTW verifier (on synthetic audio) — and skip anything that needs the
Shazam network, ffmpeg, or (for the verifier) librosa if it's absent.
