# Agent overview

This repo prepares **RSS.com drafts only** — never publish live episodes via the API.

## User-facing workflow

1. User config: `.env` (secrets) + `podcast.config.yaml` (show defaults)
2. Episode content: one folder per episode under `episodes/`
3. Publishing: `make dry-run` then `make publish` — never skip dry-run

## Episode folder contract

Each episode folder contains:

- `episode.yaml` — short metadata (title, audio filename, optional overrides)
- `script.md` — host planning doc (NOT uploaded to RSS.com)
- `description.md` — show notes (uploaded as RSS.com description)
- `corrections.yaml` — optional transcript typo fixes

## Agent rules

- When the user says "new episode", use the `new-episode` skill
- Prefer editing markdown over YAML unless metadata is needed
- Before publish: confirm MP3 exists, description is non-empty, dry-run succeeded
- Print the RSS.com dashboard URL after publish
- Do not commit `.env`

## Commands

```bash
make check                              # Validate setup
make dry-run EPISODE=episodes/my-folder # Preview without uploading
make publish EPISODE=episodes/my-folder # Create draft on RSS.com
```
