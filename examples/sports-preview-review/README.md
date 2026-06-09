# Sports Preview/Review Recipe

This is an **optional reference recipe** for sports match preview and review episodes. It is not required for the core workflow.

Copy ideas from here into your own `podcast.config.yaml` and episode templates if you host a similar show.

## Title template

```yaml
title:
  template: "#{number}: {home_team} vs {away_team} — {tournament} {match_type}"
```

## Episode fields (episode.yaml)

```yaml
title: "Home Hawks vs Away Eagles"
home_team: "Home Hawks (H)"
away_team: "Away Eagles"
tournament: "Championship"
match_type: "Preview"
audio: "your-recording.mp3"
keywords: ["Sports", "Preview"]
```

## Script templates

- `templates/scripts/sports-preview.md` — generic sports preview scaffold
- See the templates in this folder's `templates/` directory for full preview and review scripts

## Global corrections

```yaml
corrections:
  "Match Day Pod": "Match Day Podcast"
  "home hawks": "Home Hawks"
  "away eagles": "Away Eagles"
```
