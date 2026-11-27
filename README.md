![tl;dw. Skip the video. Keep the answer.](assets/social-preview.jpg)

# tldw

A friend sends you a reel. "You HAVE to see this." It is ninety seconds of someone pointing at text bubbles about ten things to buy for your home. You don't want the pointing. You want the ten things.

`tldw` (too long; didn't watch) is a Claude Code skill that watches the video so you don't have to. You hand Claude a link to a Reel, a YouTube video, a TikTok or a local file, ask your question, and get an answer with timestamps.

![A 12-minute film turned into 60 frames, 46 transcript lines and one answer](assets/demo.jpg)

## Why this exists

Video is a terrible container for information you only want to extract. You can't skim it, you can't search it, and the one sentence you need is always at 7:42, right after the sponsor read.

Claude Code has the opposite problem. It reads text and images very well and cannot open a video at all. Give it a link and it will politely tell you so.

So `tldw` does the boring conversion. It turns the video into the two things Claude is good at, frames and text, and gets out of the way.

It also does it on your machine. No API keys, nothing uploaded anywhere, and it never touches your browser. More on that in [Security](#security), because a skill you install is a stranger's code running inside your agent, and you should be at least a little suspicious of mine.

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

That's the whole setup. There is no virtualenv to babysit: the script lists its own dependencies, and `uv` installs them the first time it runs.

## Use

Ask the way you would ask a person:

> watch https://www.instagram.com/reel/... and list the books he recommends

Or call it directly: `/tldw:tldw <link or path>`.

Things it turns out to be good for:

- **The reel with "ten things to buy for your home".** You get the ten things as a list, with the moment each one shows up.
- **The 40-minute conference talk.** You get the three points that matter and where to jump to.
- **The recipe video.** You get ingredients and steps as text, which is how recipes should have been delivered in the first place.
- **The video in a language you don't speak.** You get the gist in yours.

One heads-up: the first run downloads the Whisper `small` model from Hugging Face and takes a few minutes. Go get a coffee. After that, a one-minute clip is seconds to download and cut, plus however long your CPU needs to transcribe it.

## How it works

One script, [`skills/tldw/watch.py`](skills/tldw/watch.py), about 280 lines. You can read all of it faster than you can watch most of the videos you'll feed it.

1. `yt-dlp` downloads the video, capped at 720p and 500 MB.
2. `ffmpeg` cuts evenly spaced frames, 16 to 60 depending on the length.
3. Frames that look almost the same as their neighbour get dropped, so Claude doesn't read the same talking head twelve times.
4. `faster-whisper` transcribes the audio on your CPU and skips the silence.
5. Frames, `transcript.md` and `meta.json` land in `~/.tldw/runs/<timestamp>/`, and Claude reads them.

The frames matter more than you'd think. Speech gives you "this one is great, this one I'd skip". The names, prices and titles are usually on the screen.

You don't need Claude to run it:

```bash
uv run skills/tldw/watch.py "https://www.instagram.com/reel/<id>/"
uv run skills/tldw/watch.py clip.mp4 --lang ru --frames 30
uv run skills/tldw/watch.py --selftest
```

## Login walls

Sooner or later a site will refuse to hand over the video. Instagram wants you logged in for some reels. YouTube, after a couple of downloads from the same address, starts answering "Sign in to confirm you're not a bot", which is a fair question to ask a script.

You have two ways out.

**Download the video yourself and pass the file.** Boring, safe, and what I'd do.

**Or hand the script a cookies file.** Export cookies for that one site to a Netscape-format `cookies.txt` with a browser extension and pass it:

```bash
uv run skills/tldw/watch.py "https://www.instagram.com/reel/<id>/" --cookies ~/cookies.txt
```

The script works on a temporary copy and deletes it when the download ends, so your file is left alone. Before you do this, know what you're holding: a cookies file is a live login session, so treat it like a password, and sites do restrict accounts that make automated requests, so use a spare account and not the one with ten years of your photos on it.

## Security

A skill is someone else's code and someone else's instructions running inside your agent, with your files and your shell. That should make you uneasy. Here is what I did about it.

I kept it small enough to read in one sitting, and I run it through [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector), a scanner built for exactly this question.

- **Static scan:** risk score 16 out of 100, recommendation `SAFE`, 100% coverage. CI repeats it on every push, so I can't quietly make it worse.
- **Scan with LLM semantic analysis:** same score, no additional findings.
- **What's left:** two medium findings for calling `ffmpeg` through `subprocess` (argument lists, no shell) and one low one for the permissions the skill declares.

The full reports are in [`docs/`](docs/). Don't take my word for the numbers; run the scanner yourself.

What the skill refuses to do, on purpose:

- It does not read your browser's cookie store or go looking for credentials. The only login material it ever touches is a cookies file you pass yourself with `--cookies`.
- It does not send audio, frames or transcripts anywhere. Transcription happens on your machine.
- It does not read environment variables.

One more thing worth knowing. The caption, the transcript and the text on screen are written by whoever made the video, and that person is not you. The skill tells Claude to treat all of it as data about the video and never as instructions.

## Limits

I'd rather you hear these from me.

- Videos behind a login wall are not downloaded unless you help. See [Login walls](#login-walls).
- Whisper `small` mishears things, mostly names. The frames usually save it, because the name is on the screen.
- Language auto-detection is shaky on very short clips. Pass `--lang`.
- Tested on macOS with Apple Silicon. Linux should work. Windows is untested, and I won't pretend otherwise.

## Bottom line

You were never going to watch that video. Now you don't have to feel bad about it.

## Credits

The demo frames are from [Tears of Steel](https://mango.blender.org/), (CC) Blender Foundation, licensed under CC BY 3.0.

## License

MIT
