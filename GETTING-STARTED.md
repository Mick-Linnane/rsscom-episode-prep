# Getting started

A walkthrough for setting up RSS.com Episode Prep from scratch. No dev experience needed.

## Before you begin

You need:

- An RSS.com account on the **Network plan**
- At least one podcast created in RSS.com
- **Auto-transcription** turned on for that podcast
- An **API key** generated in your account

## Step 1: Get your API key

1. Log in to [RSS.com dashboard](https://dashboard.rss.com)
2. Open the **Account** menu (top-right)
3. Select **API Access**
4. Click **Generate API key** (or copy an existing key)
5. Paste it into `.env` as `RSSCOM_API_KEY=`

[screenshot: RSS.com API settings]

> Keep your API key secret. Never commit `.env` to git or paste it into public chat.

## Step 2: Find your podcast ID

1. In the dashboard, open your podcast
2. Look at the browser URL — the podcast ID is the number in the path
3. Paste it into `.env` as `RSSCOM_PODCAST_ID=`

Example: if the URL is `https://dashboard.rss.com/podcasts/12345/episodes`, your ID is `12345`.

[screenshot: RSS.com podcast URL with ID]

## Step 3: Set your audio folder

In `.env`, set `RSSCOM_AUDIO_DIR` to the folder where your recorded MP3s are saved.

**macOS example:**
```
RSSCOM_AUDIO_DIR=/Users/yourname/Recordings
```

**Windows example:**
```
RSSCOM_AUDIO_DIR=C:\Users\yourname\Recordings
```

You can also put MP3s directly in each episode folder — the audio folder is optional.

## Step 4: Enable auto-transcription

1. Open your podcast in the RSS.com dashboard
2. Go to **Settings** (or podcast settings)
3. Enable **auto-transcription** / AI transcription for new episodes

[screenshot: RSS.com transcription settings]

The prep tool waits for RSS.com to finish transcribing, then applies your typo corrections.

## Step 5: Configure your show

Edit `podcast.config.yaml` (or ask Cursor to help):

```yaml
show:
  name: "My Podcast"
  host: "Alex"

title:
  template: "#{number}: {title}"
```

The title template controls how episode titles appear on RSS.com. Placeholders:

| Placeholder | Source |
|-------------|--------|
| `{number}` | Auto-assigned episode number |
| `{title}` | `episode.yaml` → `title` |
| `{subtitle}` | `episode.yaml` → `subtitle` |
| `{show}` | `podcast.config.yaml` → `show.name` |
| `{season}` | Season number |

## Step 6: Run make check

```bash
make check
```

You should see:

```
✓ .env found
✓ API key valid
✓ Podcast: "My Show" (id 12345)
✓ Audio folder: /Users/.../Recordings
✓ Next episode: Season 1, Episode 12
✓ Auto-transcription: verify enabled in RSS.com dashboard

Ready to publish.
```

If anything fails, the output tells you what to fix.

## Step 7: Create your first episode

In Cursor chat:

```
Create a new episode about [your topic].
```

This creates a folder under `episodes/` with `episode.yaml`, `script.md`, and `description.md`.

1. Edit the script and show notes
2. Drop your MP3 into the audio folder or episode folder
3. Run `make dry-run EPISODE=episodes/your-folder`
4. Run `make publish EPISODE=episodes/your-folder`

## What "draft" means

This tool **never publishes live** to Apple Podcasts, Spotify, or your RSS feed.

It creates a **draft episode** on RSS.com. You review audio, metadata, and transcript in the dashboard, then click **Publish** yourself when ready.

That is intentional — you stay in control of what goes live.

## Dashboard link after publish

After `make publish`, the terminal prints a dashboard URL like:

```
dashboard: https://dashboard.rss.com/podcasts/episodes/67890
```

Open that link to review your draft.

## Need help?

- Copy-paste prompts: [CURSOR-PROMPTS.md](CURSOR-PROMPTS.md)
- Common issues: [README.md#faq](README.md#faq)
- API docs: [api.rss.com/v4/docs](https://api.rss.com/v4/docs)
