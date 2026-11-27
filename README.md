![Too long; didn't watch](assets/social-preview.jpg)

# tldw

Too long; didn't watch. A Claude Code skill that watches a video for you.

Give Claude a link to an Instagram Reel, a YouTube video, a TikTok or a local file. The skill downloads the video, cuts frames, transcribes the speech, and Claude reads both to tell you what is in it or answer a question about it.

Everything runs on your machine. There are no API keys, the skill never reads your browser, and nothing is uploaded to a third-party service.

![A 12-minute film turned into 60 frames, 46 transcript lines and one answer](assets/demo.jpg)

## Install

You need [`uv`](https://docs.astral.sh/uv/) and `ffmpeg`. On macOS:

```bash
brew install uv ffmpeg
```

Then, in Claude Code:

```
/plugin marketplace add VsevolodEpinetov/tldw
/plugin install tldw@tldw
```

There is no Python setup. The script declares its dependencies inline, and `uv` installs them on the first run.

## Use

Ask in plain words:

> watch https://www.instagram.com/reel/... and list the books he recommends

or call it directly: `/tldw:tldw <link or path>`.

What it is good for:

- A friend sends a reel with "ten things to buy for your home". You get the ten things as a list, with the moment each one appears.
- A 40-minute conference talk. You get the three points that matter and where to jump to.
- A recipe video. You get the ingredients and the steps as text.
- A screen recording of a bug. Claude reads the error on the screen and tells you what broke.
- A video in a language you don't speak. You get the gist in yours.

The first run downloads the Whisper `small` model from Hugging Face and takes a few minutes. After that a one-minute clip takes seconds to download and cut, plus transcription time on your CPU.

## How it works

One script, [`skills/tldw/watch.py`](skills/tldw/watch.py), about 280 lines:

1. `yt-dlp` downloads the video, capped at 720p and 500 MB.
2. `ffmpeg` cuts evenly spaced frames, 16 to 60 depending on the length.
3. Near-identical neighbouring frames are dropped by perceptual hash.
4. `faster-whisper` transcribes the audio on the CPU, with silence filtered out.
5. Frames, `transcript.md` and `meta.json` land in `~/.tldw/runs/<timestamp>/`, and Claude reads them.

You can run the script without Claude:

```bash
uv run skills/tldw/watch.py "https://www.instagram.com/reel/<id>/"
uv run skills/tldw/watch.py clip.mp4 --lang ru --frames 30
uv run skills/tldw/watch.py --selftest
```

## Login walls

When a site demands a login, you have two options.

Download the video yourself and pass the file. This is the safe default.

Or export cookies for that one site to a Netscape-format `cookies.txt` with a browser extension and pass it:

```bash
uv run skills/tldw/watch.py "https://www.instagram.com/reel/<id>/" --cookies ~/cookies.txt
```

The script works on a temporary copy of the file and deletes the copy when the download ends, so your file is not modified. Two things to know before you do this: a cookies file is a live login session, so store it like a password, and sites can restrict accounts that make automated requests, so use a spare account.

## Security

A skill is someone else's code and instructions running inside your agent, so this one is kept small enough to read in one sitting, and it is scanned with [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector).

- Static scan: risk score 16 out of 100, recommendation `SAFE`, 100% coverage. CI repeats this scan on every push.
- Scan with LLM semantic analysis: same score, no additional findings.
- The remaining findings are two medium ones for calling `ffmpeg` through `subprocess` (argument lists, no shell) and one low one for the declared permissions.

The full reports are in [`docs/`](docs/).

What the skill does not do, on purpose:

- It does not read your browser's cookie store or look for credentials on its own. The only login material it ever touches is a cookies file you pass explicitly with `--cookies`.
- It does not send audio, frames or transcripts anywhere. Transcription is local.
- It does not read environment variables.

The caption, transcript and on-screen text of a video are untrusted content. The skill tells the agent to treat them as data and not to follow instructions found there.

## Limits

- Videos behind a login wall are not downloaded by default. YouTube, for one, may answer "Sign in to confirm you're not a bot" after a couple of downloads from the same address. See [Login walls](#login-walls).
- Whisper `small` gets occasional words wrong, mostly names. On-screen text in the frames usually fills the gap.
- Language auto-detection is unreliable on very short clips. Pass `--lang`.
- Tested on macOS with Apple Silicon. Linux should work; Windows is untested.

## Credits

The demo frames are from [Tears of Steel](https://mango.blender.org/), (CC) Blender Foundation, licensed under CC BY 3.0.

## License

MIT
