---
name: new-episode
description: Create a new episode folder from templates for RSS.com episode prep. Use when the user says new episode, prepare episode, or start episode about a topic.
---

# New Episode

Scaffold a new episode folder under `episodes/` for RSS.com draft publishing.

## Trigger phrases

- "new episode"
- "prepare episode"
- "start episode about …"
- "create episode for …"

## Steps

### 1. Gather details

Ask or infer from the user's message:

- **Topic** or guest name
- **Episode type** (interview, solo, news, sports preview — default: generic interview/solo)
- **Title** (short, for `episode.yaml`)

If the user already gave enough context, skip questions.

### 2. Create folder

Folder name format: `episodes/YYYY-MM-DD-short-slug/`

- Date: today's date
- Slug: lowercase, hyphens, no spaces (e.g. `jane-doe-interview`)

### 3. Copy templates

Copy all files from `templates/episode/` into the new folder:

- `episode.yaml`
- `script.md`
- `description.md`
- `corrections.yaml`

### 4. Fill episode.yaml

Set at minimum:

```yaml
title: "Interview with Jane Doe"
subtitle: ""
audio: "recording.mp3"
keywords: []
explicit: false
season: 1
```

Add extra fields if the show uses a structured title template (e.g. `guest`, `topic`, `home_team`).

### 5. Draft script.md

Use `templates/scripts/generic-script.md` as the base (or `templates/scripts/sports-preview.md` for sports previews).

Replace placeholders using values from `podcast.config.yaml` (`show.name`, `show.host`) and the user's topic.

### 6. Draft description.md

Use `templates/descriptions/generic-description.md` as style guide.

Write 2–3 opening paragraphs plus 3–4 bullet topics with emoji. Keep under 4000 characters.

### 7. Remind user of next steps

Tell the user:

1. Review and edit `script.md` and `description.md`
2. Drop their MP3 into `RSSCOM_AUDIO_DIR` or the episode folder (update `audio:` in `episode.yaml` if needed)
3. Run `make dry-run EPISODE=episodes/...` — offer to run this in the terminal
4. Run `make publish EPISODE=episodes/...` after dry-run passes
5. Open the RSS.com dashboard link to review and publish manually

## Do not

- Publish without a successful dry-run
- Commit `.env`
- Put API keys in episode files
