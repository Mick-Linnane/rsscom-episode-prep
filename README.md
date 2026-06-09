# RSS.com Episode Prep

**From script to RSS.com draft — one folder, one command.**

A minimal, beginner-friendly tool that takes you from an episode idea or script to a draft episode on RSS.com with audio, metadata, and corrected transcript. No Python or API knowledge required — Cursor chat and a single `make publish` command do the heavy lifting.

## What this does

You write your script and show notes in markdown, drop your MP3, and run one command. The tool uploads audio, sets episode metadata, waits for RSS.com auto-transcription, applies typo corrections, and leaves everything as a **draft** for you to review and publish manually in the RSS.com dashboard.

## What you need

- **RSS.com Network plan** with API access ([API Access help](https://help.rss.com/en/support/solutions/articles/44002648949-api-access))
- **Auto-transcription enabled** on your podcast (RSS.com dashboard → Settings)
- **Python 3.10+** (pre-installed on macOS; [python.org](https://www.python.org/downloads/) on Windows)
- **Cursor** (recommended) for chat-guided episode creation
- Recorded episodes as **MP3** files

## 5-minute setup

1. **Clone this repo** (or use GitHub "Use this template")
2. **Open the folder in Cursor**
3. **Copy config files:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` — paste your API key, podcast ID, and the folder where your MP3s are saved.
4. **Edit `podcast.config.yaml`** — set your show name, host, title template, and default keywords. Ask Cursor: *"Set up my podcast — my show is called X, host is Y…"*
5. **Verify setup:**
   ```bash
   make check
   ```

See [GETTING-STARTED.md](GETTING-STARTED.md) for dashboard screenshots and step-by-step detail.

## Your first episode with Cursor

Paste these prompts into Cursor chat (more in [CURSOR-PROMPTS.md](CURSOR-PROMPTS.md)):

```
Create a new episode about [your topic].
```

Edit `script.md` and `description.md` in the new folder. Drop your MP3 into your audio folder or the episode folder.

```
Dry run episodes/[your-folder] and tell me if anything is wrong.
```

```
Publish this episode — run dry-run first, then publish if it looks good.
```

Open the dashboard link printed in the terminal → review → publish manually.

## Commands

| Command | What it does |
|---------|--------------|
| `make check` | Validate `.env`, config, API key, and next episode number |
| `make dry-run EPISODE=episodes/my-folder` | Preview title, description, and API payload (no upload) |
| `make publish EPISODE=episodes/my-folder` | Full flow → RSS.com draft |
| `make fix-transcript EPISODE_ID=123 CORRECTIONS=episodes/foo/corrections.yaml` | Re-apply transcript corrections |
| `make help` | Plain-English list of all targets |

Optional variables: `MP3=path/to/file.mp3`, `TIMEOUT=3600`.

## Episode folder structure

```
episodes/2026-06-09-jane-doe/
├── episode.yaml       # Title, audio filename, optional overrides
├── script.md          # Your planning doc (NOT sent to RSS.com)
├── description.md     # Show notes → RSS.com description
└── corrections.yaml   # Optional transcript typo fixes
```

## FAQ

**MP3 not found**

Put your file in the episode folder, or in the folder set as `RSSCOM_AUDIO_DIR` in `.env`, and set `audio: "filename.mp3"` in `episode.yaml`.

**Transcription timed out**

RSS.com may still be processing. Open the dashboard link and check status. Increase wait time: `make publish TIMEOUT=7200 EPISODE=...`.

**Wrong episode number**

Remove `itunes_episode` from `episode.yaml` to auto-assign the next number. Run `make check` to see what number is next.

**Transcript typos**

Add find/replace pairs to `corrections.yaml` (per episode) or `podcast.config.yaml` (show-wide). Re-run publish, or use `make fix-transcript` on an existing episode ID.

**Description too long**

RSS.com limits descriptions to 4000 characters. The tool truncates with a warning — edit `description.md` to shorten it.

## Optional recipes

- **[Sports preview/review example](examples/sports-preview-review/)** — match preview/review title templates, script templates, and corrections. Reference only; not required for the core workflow.

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Secrets only: API key, podcast ID, audio folder path |
| `podcast.config.yaml` | Show name, title template, default keywords, global corrections |

Episode-level overrides live in each folder's `episode.yaml`.

## Contributing

Issues and pull requests welcome. Keep the core tool generic — show-specific recipes belong in `examples/`.

## License

MIT — see [LICENSE](LICENSE).
