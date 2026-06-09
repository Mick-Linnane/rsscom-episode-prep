#!/usr/bin/env python3
"""
Prepare podcast episode drafts on RSS.com via the v4 API.

Uploads audio, sets metadata, waits for auto-transcription, applies typo corrections.
Episodes are always created as drafts for manual review in the RSS.com dashboard.

Requires: Python 3.10+, .env with RSSCOM_API_KEY and RSSCOM_PODCAST_ID.

Example:
  make check
  make dry-run EPISODE=episodes/example
  make publish EPISODE=episodes/my-episode
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.rss.com"
DASHBOARD_BASE = "https://dashboard.rss.com"
TIMESTAMP_LINE = re.compile(
    r"^\d{2}:\d{2}(:\d{2})?([.,]\d{3})?\s*-->\s*\d{2}:\d{2}"
)
TITLE_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class RssComClient:
    def __init__(self, api_key: str, podcast_id: int, dry_run: bool = False) -> None:
        self.api_key = api_key
        self.podcast_id = podcast_id
        self.dry_run = dry_run

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{API_BASE}{path}"
        headers = {"X-Api-Key": self.api_key}
        if extra_headers:
            headers.update(extra_headers)

        data: bytes | None = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.dry_run and method != "GET":
            print(f"[dry-run] {method} {url}")
            if body is not None:
                print(json.dumps(body, indent=2))
            elif raw_body is not None:
                print(f"[dry-run] binary payload ({len(raw_body)} bytes)")
            return {}

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                if not payload:
                    return {}
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                error_body = json.loads(detail)
                field_errors = error_body.get("field_errors") or {}
                if field_errors:
                    parts = [
                        f"{field}: {', '.join(messages)}"
                        for field, messages in field_errors.items()
                        if field.strip()
                    ]
                    if parts:
                        detail = "; ".join(parts)
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"{method} {path} failed ({exc.code}): {detail}") from exc

    def get_podcast(self) -> dict[str, Any]:
        return self._request("GET", f"/v4/podcasts/{self.podcast_id}")

    def upload_audio(self, mp3_path: Path) -> str:
        mime, _ = mimetypes.guess_type(mp3_path.name)
        expected_mime = mime or "audio/mpeg"
        presigned = self._request(
            "POST",
            f"/v4/podcasts/{self.podcast_id}/assets/presigned-uploads",
            body={
                "asset_type": "audio",
                "expected_mime": expected_mime,
                "filename": mp3_path.name,
            },
        )
        upload_id = presigned["id"]
        upload_url = presigned["url"]
        audio_bytes = mp3_path.read_bytes()

        if self.dry_run:
            print(f"[dry-run] PUT {upload_url} ({len(audio_bytes)} bytes)")
            return upload_id

        put_request = urllib.request.Request(
            upload_url,
            data=audio_bytes,
            headers={"Content-Type": expected_mime},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(put_request, timeout=600):
                pass
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Audio upload failed ({exc.code}): {detail}") from exc

        return upload_id

    def list_keywords(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return []
        return self._request("GET", f"/v4/podcasts/{self.podcast_id}/keywords")

    def create_keyword(self, label: str) -> dict[str, Any]:
        if self.dry_run:
            return {"id": abs(hash(label)) % 10000, "label": label}
        return self._request(
            "POST",
            f"/v4/podcasts/{self.podcast_id}/keywords",
            body={"label": label},
        )

    def list_episodes(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return [{"itunes_season": 1, "itunes_episode": 11, "title": "dry-run latest"}]

        episodes: list[dict[str, Any]] = []
        page = 1
        limit = 100
        while True:
            batch = self._request(
                "GET",
                f"/v4/podcasts/{self.podcast_id}/episodes?page={page}&limit={limit}&order=newest",
            )
            if not batch:
                break
            episodes.extend(batch)
            if len(batch) < limit:
                break
            page += 1
        return episodes

    def episode_numbers_in_season(self, season: int = 1) -> set[int]:
        return {
            episode["itunes_episode"]
            for episode in self.list_episodes()
            if (episode.get("itunes_season") or 1) == season
            and isinstance(episode.get("itunes_episode"), int)
        }

    def assert_episode_number_available(self, season: int, episode_number: int) -> None:
        if episode_number in self.episode_numbers_in_season(season):
            next_number, _latest = self.next_episode_number(season)
            raise SystemExit(
                f"Season {season}, Episode {episode_number} already exists on RSS.com. "
                f"Remove itunes_episode from episode.yaml to auto-assign Episode {next_number}, "
                f"or pick a different number."
            )

    def next_episode_number(self, season: int = 1) -> tuple[int, int | None]:
        numbers = [
            episode["itunes_episode"]
            for episode in self.list_episodes()
            if (episode.get("itunes_season") or 1) == season
            and isinstance(episode.get("itunes_episode"), int)
        ]
        if not numbers:
            return 1, None
        latest = max(numbers)
        return latest + 1, latest

    def resolve_episode_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(metadata)
        season = resolved.get("itunes_season", 1)

        if "itunes_episode" in resolved:
            episode_number = resolved["itunes_episode"]
            self.assert_episode_number_available(season, episode_number)
            print(
                f"Episode number: Season {season}, Episode {episode_number} "
                "(from episode.yaml override)"
            )
            return resolved

        next_number, latest = self.next_episode_number(season)
        resolved["itunes_episode"] = next_number
        if latest is None:
            print(f"Episode number: Season {season}, Episode {next_number} (first in season)")
        else:
            print(
                f"Episode number: Season {season}, Episode {next_number} "
                f"(latest on RSS.com: Episode {latest})"
            )
        return resolved

    def resolve_keyword_ids(self, labels: list[str]) -> list[int]:
        existing = {item["label"].lower(): item["id"] for item in self.list_keywords()}
        ids: list[int] = []
        for label in labels:
            found = existing.get(label.lower())
            if found is not None:
                ids.append(found)
                continue
            created = self.create_keyword(label)
            ids.append(created["id"])
            existing[label.lower()] = created["id"]
        return ids

    def search_locations(self, query: str) -> list[dict[str, Any]]:
        if self.dry_run:
            return [{"id": f"dry-run-{query}", "name": query, "type": "Region"}]
        encoded = urllib.parse.quote(query)
        return self._request("GET", f"/v4/locations?filter={encoded}")

    def resolve_location_id(self, spec: str | dict[str, str]) -> str:
        if isinstance(spec, str):
            return spec
        query = spec["search"]
        expected_type = spec.get("type")
        results = self.search_locations(query)
        if not results:
            raise SystemExit(
                f"No location found for search {query!r}. "
                "Check defaults.locations in podcast.config.yaml."
            )

        if expected_type:
            typed = [
                item
                for item in results
                if item.get("type", "").lower() == expected_type.lower()
            ]
            if typed:
                for item in typed:
                    if query.lower() in item.get("name", "").lower():
                        return item["id"]
                return typed[0]["id"]

        return results[0]["id"]

    def resolve_location_ids(self, locations: dict[str, Any] | None) -> dict[str, str]:
        if not locations:
            return {}
        subject = self.resolve_location_id(locations["subject"])
        creator = self.resolve_location_id(locations["creator"])
        print(f"Locations: subject={subject}, creator={creator}")
        return {"subject": subject, "creator": creator}

    def create_episode(self, metadata: dict[str, Any], audio_upload_id: str) -> dict[str, Any]:
        body = {
            "title": metadata["title"],
            "description": metadata["description"],
            "itunes_explicit": metadata.get("itunes_explicit", False),
            "itunes_episode": metadata.get("itunes_episode"),
            "itunes_season": metadata.get("itunes_season", 1),
            "itunes_episode_type": metadata.get("itunes_episode_type", "full"),
            "audio_upload_id": audio_upload_id,
        }
        if metadata.get("custom_link"):
            body["custom_link"] = metadata["custom_link"]
        if metadata.get("keywords"):
            body["keyword_ids"] = self.resolve_keyword_ids(metadata["keywords"])
        if metadata.get("location_ids"):
            body["location_ids"] = metadata["location_ids"]

        return self._request(
            "POST",
            f"/v4/podcasts/{self.podcast_id}/episodes",
            body=body,
        )

    def get_episode(self, episode_id: int) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v4/podcasts/{self.podcast_id}/episodes/{episode_id}",
        )

    def wait_for_processing(
        self,
        episode_id: int,
        job: str,
        *,
        timeout_seconds: int = 3600,
        poll_seconds: int = 15,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            episode = self.get_episode(episode_id)
            status = episode.get("processing", {}).get(job, {}).get("status", "pending")
            details = episode.get("processing", {}).get(job, {}).get("details", "")
            print(f"  {job}: {status}" + (f" ({details})" if details else ""))
            if status in {"completed", "complete", "done", "success"}:
                return episode
            if status in {"failed", "error"}:
                raise RuntimeError(f"{job} failed for episode {episode_id}: {details}")
            if self.dry_run:
                return episode
            time.sleep(poll_seconds)
        raise TimeoutError(
            f"Timed out waiting for {job} on episode {episode_id} after {timeout_seconds}s. "
            "Increase TIMEOUT= or check the episode in your RSS.com dashboard."
        )

    def get_transcript(self, episode_id: int) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v4/podcasts/{self.podcast_id}/episodes/{episode_id}/transcript",
        )

    def put_transcript(self, episode_id: int, transcription: str, fmt: str) -> dict[str, Any]:
        return self._request(
            "PUT",
            f"/v4/podcasts/{self.podcast_id}/episodes/{episode_id}/transcript",
            body={"transcription": transcription, "format": fmt},
        )


def load_dotenv() -> None:
    """Load RSSCOM_* variables from .env in the cwd or beside this script."""
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_yaml_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return _strip_quotes(value)


def _yaml_block_lines(lines: list[str], start: int) -> tuple[list[str], int]:
    block: list[str] = []
    base_indent = len(lines[start]) - len(lines[start].lstrip(" "))
    index = start
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            block.append(line)
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent < base_indent:
            break
        block.append(line)
        index += 1
    return block, index


def _parse_yaml_value(raw: str) -> Any:
    value = raw.strip()
    if value == "{}":
        return {}
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(part.strip()) for part in inner.split(",")]
    return _parse_yaml_scalar(value)


def _parse_yaml_block(block: list[str]) -> Any:
    meaningful = [
        line
        for line in block
        if line.strip() and not line.strip().startswith("#")
    ]
    if not meaningful:
        return {}

    first = meaningful[0]
    first_indent = len(first) - len(first.lstrip(" "))
    first_stripped = first.strip()

    if first_stripped.startswith("- "):
        items: list[Any] = []
        index = 0
        while index < len(block):
            line = block[index]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                index += 1
                continue
            if not stripped.startswith("- "):
                break
            item_indent = len(line) - len(line.lstrip(" "))
            content = stripped[2:].strip()
            if content and content.endswith(":") and not content.startswith('"'):
                nested_block, next_index = _yaml_block_lines(block, index + 1)
                key = content[:-1].strip()
                nested = _parse_yaml_block(nested_block)
                if isinstance(nested, dict):
                    nested = {key: nested.get(key, nested)}
                items.append(nested)
                index = next_index
            elif ":" in content and not content.startswith('"'):
                key, value = content.split(":", 1)
                item: dict[str, Any] = {key.strip(): _parse_yaml_value(value)}
                nested_block, next_index = _yaml_block_lines(block, index + 1)
                if nested_block:
                    nested = _parse_yaml_block(nested_block)
                    if isinstance(nested, dict):
                        item.update(nested)
                items.append(item)
                index = next_index
            else:
                items.append(_parse_yaml_scalar(content))
                index += 1
            _ = item_indent
        return items

    result: dict[str, Any] = {}
    index = 0
    while index < len(block):
        line = block[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent > first_indent:
            index += 1
            continue
        if ":" not in stripped:
            index += 1
            continue
        key, value = stripped.split(":", 1)
        key = _strip_quotes(key.strip())
        value = value.strip()
        if not value:
            nested_block, next_index = _yaml_block_lines(block, index + 1)
            result[key] = _parse_yaml_block(nested_block)
            index = next_index
        else:
            result[key] = _parse_yaml_value(value)
            index += 1
    return result


def load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    return _parse_yaml_block(lines)


def load_structured_file(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    return load_yaml(path)


def find_config_file(repo_root: Path, basename: str) -> Path | None:
    for suffix in (".yaml", ".yml", ".json"):
        candidate = repo_root / f"{basename}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def load_podcast_config() -> dict[str, Any]:
    root = repo_root()
    path = find_config_file(root, "podcast.config")
    if not path:
        raise SystemExit(
            "podcast.config.yaml not found. Copy podcast.config.example.yaml to "
            "podcast.config.yaml and edit your show details."
        )
    return load_structured_file(path)


def load_json_or_yaml(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_structured_file(path)


def find_episode_metadata_file(episode_dir: Path) -> Path:
    for name in ("episode.yaml", "episode.yml", "episode.json"):
        candidate = episode_dir / name
        if candidate.is_file():
            return candidate
    raise SystemExit(
        f"No episode.yaml or episode.json found in {episode_dir}. "
        "Create one from templates/episode/."
    )


def find_corrections_file(episode_dir: Path) -> Path | None:
    for name in ("corrections.yaml", "corrections.yml", "corrections.json"):
        candidate = episode_dir / name
        if candidate.is_file():
            return candidate
    return None


def merge_corrections(
    global_corrections: dict[str, str],
    episode_corrections: dict[str, str],
) -> dict[str, str]:
    merged = dict(global_corrections)
    merged.update(episode_corrections)
    return merged


def build_title(template: str, context: dict[str, Any]) -> str:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context or context[key] in (None, ""):
            missing.append(key)
            return match.group(0)
        return str(context[key])

    title = TITLE_PLACEHOLDER.sub(replace, template)
    if missing:
        unique = sorted(set(missing))
        fields = ", ".join(unique)
        raise SystemExit(
            f"Your title template uses {{{unique[0]}}} "
            f"but episode.yaml has no {fields} field. "
            f"Add {fields} to episode.yaml or change title.template in podcast.config.yaml."
        )
    return title


def get_audio_base() -> Path | None:
    value = os.environ.get("RSSCOM_AUDIO_DIR", "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise SystemExit(
            f"RSSCOM_AUDIO_DIR is not a directory: {path}\n"
            "Fix the path in .env — use the folder where your recorded MP3s are saved."
        )
    return path


def resolve_audio_path(path: Path, audio_base: Path | None) -> Path:
    if path.is_file():
        return path.resolve()

    if not path.is_absolute() and audio_base:
        candidate = (audio_base / path).resolve()
        if candidate.is_file():
            return candidate

    candidate = path.resolve()
    if candidate.is_file():
        return candidate

    locations = [str(path)]
    if audio_base:
        locations.append(str(audio_base / path.name))
    raise SystemExit(
        f"MP3 not found: {path.name}\n"
        f"Put your file in {audio_base or 'the episode folder'} "
        f"or set audio: \"{path.name}\" in episode.yaml."
    )


def find_audio_file(
    episode_dir: Path,
    raw: dict[str, Any],
    override: Path | None,
    audio_base: Path | None,
) -> Path:
    if override:
        return resolve_audio_path(override, audio_base)

    if raw.get("audio"):
        filename = Path(str(raw["audio"]))
        for base in (episode_dir, audio_base):
            if base is None:
                continue
            candidate = (base / filename).resolve()
            if candidate.is_file():
                return candidate
        checked = f"{episode_dir}"
        if audio_base:
            checked += f" and {audio_base}"
        raise SystemExit(
            f"MP3 not found: {raw['audio']} (checked {checked}).\n"
            "Drop the MP3 into the episode folder or your RSSCOM_AUDIO_DIR, "
            "or pass MP3= when running make."
        )

    mp3_files = sorted(episode_dir.glob("*.mp3"))
    if len(mp3_files) == 1:
        return mp3_files[0].resolve()
    if len(mp3_files) > 1:
        raise SystemExit(
            f"Multiple MP3 files in {episode_dir}. "
            'Set audio: "filename.mp3" in episode.yaml or pass MP3= when running make.'
        )

    if audio_base:
        raise SystemExit(
            f"No MP3 in {episode_dir}.\n"
            f"Drop your recording into {audio_base} and set audio: \"filename.mp3\" "
            "in episode.yaml, or put the MP3 directly in the episode folder."
        )
    raise SystemExit(
        f"No MP3 in {episode_dir}.\n"
        "Add an MP3 to the episode folder, set RSSCOM_AUDIO_DIR in .env, or pass MP3=."
    )


def episode_season(raw: dict[str, Any], podcast_config: dict[str, Any]) -> int:
    if "season" in raw:
        return int(raw["season"])
    if "itunes_season" in raw:
        return int(raw["itunes_season"])
    episode_defaults = podcast_config.get("episode", {})
    env_default = os.environ.get("RSSCOM_DEFAULT_SEASON", "").strip()
    if env_default:
        return int(env_default)
    return int(episode_defaults.get("season", 1))


def episode_explicit(raw: dict[str, Any], podcast_config: dict[str, Any]) -> bool:
    if "explicit" in raw:
        return bool(raw["explicit"])
    if "itunes_explicit" in raw:
        return bool(raw["itunes_explicit"])
    episode_defaults = podcast_config.get("episode", {})
    return bool(episode_defaults.get("explicit", False))


def episode_type(raw: dict[str, Any], podcast_config: dict[str, Any]) -> str:
    if raw.get("type"):
        return str(raw["type"])
    if raw.get("itunes_episode_type"):
        return str(raw["itunes_episode_type"])
    episode_defaults = podcast_config.get("episode", {})
    return str(episode_defaults.get("type", "full"))


def episode_keywords(raw: dict[str, Any], podcast_config: dict[str, Any]) -> list[str]:
    defaults = podcast_config.get("defaults", {}).get("keywords", [])
    episode_keywords = raw.get("keywords") or []
    if episode_keywords:
        return list(dict.fromkeys([*episode_keywords, *defaults]))
    return list(defaults)


def load_episode_folder(
    episode_dir: Path,
    client: RssComClient,
    podcast_config: dict[str, Any],
    *,
    mp3_override: Path | None = None,
    audio_base: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], dict[str, str], Path]:
    episode_dir = episode_dir.resolve()
    metadata_path = find_episode_metadata_file(episode_dir)
    description_md = episode_dir / "description.md"

    if not description_md.is_file():
        raise SystemExit(
            f"description.md not found in {episode_dir}.\n"
            "Write your show notes there — that text is sent to RSS.com."
        )

    raw = load_json_or_yaml(metadata_path)
    if not isinstance(raw, dict):
        raise SystemExit(f"{metadata_path.name} must be a mapping of fields.")

    corrections_path = find_corrections_file(episode_dir)
    episode_corrections = (
        load_json_or_yaml(corrections_path) if corrections_path else {}
    )
    if not isinstance(episode_corrections, dict):
        raise SystemExit(f"{corrections_path} must be a mapping of wrong: right pairs.")

    global_corrections = podcast_config.get("corrections", {}) or {}
    corrections = merge_corrections(global_corrections, episode_corrections)

    if "title" not in raw:
        raise SystemExit(
            f'{metadata_path.name} missing required field: title\n'
            'Add something like: title: "Interview with Jane Doe"'
        )

    max_length = int(podcast_config.get("description", {}).get("max_length", 4000))
    description = description_md.read_text(encoding="utf-8").strip()
    if not description:
        raise SystemExit(
            f"description.md is empty in {episode_dir}.\n"
            "Add your show notes before publishing."
        )
    if len(description) > max_length:
        print(
            f"Warning: description.md is {len(description)} chars; truncating to {max_length}.",
            file=sys.stderr,
        )
        description = description[:max_length]

    season = episode_season(raw, podcast_config)
    api_metadata: dict[str, Any] = {
        "itunes_season": season,
        "itunes_explicit": episode_explicit(raw, podcast_config),
        "itunes_episode_type": episode_type(raw, podcast_config),
    }
    if "itunes_episode" in raw:
        api_metadata["itunes_episode"] = int(raw["itunes_episode"])

    print("Resolving episode number...")
    api_metadata = client.resolve_episode_metadata(api_metadata)
    episode_number = api_metadata["itunes_episode"]

    title_context: dict[str, Any] = {
        "number": episode_number,
        "title": raw.get("title", ""),
        "subtitle": raw.get("subtitle", ""),
        "show": podcast_config.get("show", {}).get("name", ""),
        "season": season,
    }
    for key, value in raw.items():
        if key not in title_context:
            title_context[key] = value

    title_template = podcast_config.get("title", {}).get("template", "#{number}: {title}")
    title = build_title(title_template, title_context)
    print(f"Title: {title}")

    locations = podcast_config.get("defaults", {}).get("locations")
    location_ids: dict[str, str] = {}
    if locations:
        print("Resolving locations...")
        location_ids = client.resolve_location_ids(locations)

    metadata = {
        "title": title,
        "description": description,
        "itunes_explicit": api_metadata["itunes_explicit"],
        "itunes_episode": episode_number,
        "itunes_season": season,
        "itunes_episode_type": api_metadata["itunes_episode_type"],
        "location_ids": location_ids,
        "keywords": episode_keywords(raw, podcast_config),
        "transcript": podcast_config.get("transcript", {}),
    }
    if raw.get("custom_link"):
        metadata["custom_link"] = raw["custom_link"]

    try:
        mp3_path = find_audio_file(episode_dir, raw, mp3_override, audio_base)
    except SystemExit:
        if dry_run:
            if mp3_override:
                mp3_path = Path(mp3_override.name)
            elif raw.get("audio"):
                mp3_path = Path(str(raw["audio"]))
            else:
                mp3_path = Path("episode.mp3")
        else:
            raise

    return metadata, corrections, mp3_path


def apply_corrections(
    text: str, corrections: dict[str, str]
) -> tuple[str, list[tuple[str, str, int]]]:
    changed: list[tuple[str, str, int]] = []
    lines = text.splitlines(keepends=True)
    output: list[str] = []

    for line in lines:
        stripped = line.rstrip("\n")
        if (
            stripped.startswith("WEBVTT")
            or stripped.startswith("NOTE")
            or TIMESTAMP_LINE.match(stripped)
            or stripped.isdigit()
        ):
            output.append(line)
            continue

        updated = stripped
        for wrong, right in corrections.items():
            count = updated.count(wrong)
            if count:
                changed.append((wrong, right, count))
                updated = updated.replace(wrong, right)
        output.append(updated + ("\n" if line.endswith("\n") else ""))

    return "".join(output), changed


def dashboard_url(episode_id: int) -> str:
    return f"{DASHBOARD_BASE}/podcasts/episodes/{episode_id}"


def default_timeout() -> int:
    value = os.environ.get("RSSCOM_TRANSCRIBE_TIMEOUT", "").strip()
    return int(value) if value else 3600


def prepare(args: argparse.Namespace) -> int:
    episode_dir = Path(args.episode_dir).resolve()
    podcast_config = load_podcast_config()

    client = RssComClient(args.api_key, args.podcast_id, dry_run=args.dry_run)
    mp3_override = Path(args.mp3) if args.mp3 else None
    audio_base = get_audio_base()

    metadata, corrections, mp3_path = load_episode_folder(
        episode_dir,
        client,
        podcast_config,
        mp3_override=mp3_override,
        audio_base=audio_base,
        dry_run=args.dry_run,
    )

    print(f"Description preview ({len(metadata['description'])} chars):")
    preview = metadata["description"][:300]
    print(preview + ("..." if len(metadata["description"]) > 300 else ""))

    if not mp3_path.is_file() and not args.dry_run:
        raise SystemExit(f"MP3 not found: {mp3_path}")

    print(f"Uploading {mp3_path.name}...")
    if args.dry_run and not mp3_path.is_file():
        audio_upload_id = "dry-run-upload-id"
        print("[dry-run] skipping presigned upload (MP3 file not present)")
    else:
        audio_upload_id = client.upload_audio(mp3_path)
    print(f"  audio_upload_id: {audio_upload_id}")

    print("Creating draft episode...")
    episode = client.create_episode(metadata, audio_upload_id)
    episode_id = episode.get("id", 0)
    print(f"  episode_id: {episode_id}")
    url = episode.get("dashboard_url") or (dashboard_url(episode_id) if episode_id else "")
    if url:
        print(f"  dashboard: {url}")

    if args.dry_run:
        print("[dry-run] stopping before polling/transcription")
        print("Ready to publish for real? Run: make publish EPISODE=" + str(episode_dir))
        return 0

    print("Waiting for audio transcode...")
    client.wait_for_processing(episode_id, "transcode", timeout_seconds=args.timeout)

    transcript_cfg = metadata.get("transcript") or {}
    wait_for_transcript = transcript_cfg.get("wait", True)
    if not wait_for_transcript:
        print("Skipping transcript wait (transcript.wait: false in podcast config).")
        print(f"Draft ready — review and publish: {url}")
        return 0

    print("Waiting for auto transcription (enable in RSS.com dashboard)...")
    client.wait_for_processing(episode_id, "transcribe", timeout_seconds=args.timeout)

    should_apply_corrections = transcript_cfg.get("apply_corrections", True)
    if not corrections or not should_apply_corrections:
        print(f"Draft ready — review transcript and publish: {url}")
        return 0

    transcript = client.get_transcript(episode_id)
    fmt = transcript["format"]
    original = transcript["transcription"]
    corrected, changes = apply_corrections(original, corrections)

    if changes:
        print("Applying transcript corrections:")
        for wrong, right, count in changes:
            print(f"  {wrong!r} -> {right!r} ({count}x)")
        client.put_transcript(episode_id, corrected, fmt)
        print("Transcript saved.")
    else:
        print("No transcript corrections matched.")

    print(f"Draft ready — review and publish: {url}")
    return 0


def show_next_episode(args: argparse.Namespace) -> int:
    client = RssComClient(args.api_key, args.podcast_id, dry_run=args.dry_run)
    next_number, latest = client.next_episode_number(args.season)
    if latest is None:
        print(f"Season {args.season}, Episode {next_number} (no existing episodes in season)")
    else:
        print(
            f"Season {args.season}, Episode {next_number} "
            f"(latest on RSS.com: Episode {latest})"
        )
    return 0


def run_check(args: argparse.Namespace) -> int:
    root = repo_root()
    env_path = root / ".env"
    if not env_path.is_file():
        print("✗ .env not found")
        print("  Fix: cp .env.example .env and paste your API key and podcast ID.")
        return 1
    print("✓ .env found")

    if not args.api_key:
        print("✗ RSSCOM_API_KEY missing in .env")
        print("  Fix: Account menu → API Access in RSS.com dashboard.")
        return 1

    if not args.podcast_id:
        print("✗ RSSCOM_PODCAST_ID missing in .env")
        print("  Fix: open your podcast in RSS.com — the ID is in the URL.")
        return 1

    try:
        podcast_config = load_podcast_config()
    except SystemExit as exc:
        print(f"✗ {exc}")
        return 1
    print("✓ podcast.config found")

    client = RssComClient(args.api_key, args.podcast_id)
    try:
        podcast = client.get_podcast()
    except RuntimeError as exc:
        print(f"✗ API key or podcast ID invalid: {exc}")
        print("  Fix: regenerate your key at https://dashboard.rss.com (Account → API Access).")
        return 1
    print("✓ API key valid")

    show_name = podcast.get("title") or podcast_config.get("show", {}).get("name", "Unknown")
    print(f'✓ Podcast: "{show_name}" (id {args.podcast_id})')

    try:
        audio_base = get_audio_base()
    except SystemExit as exc:
        print(f"✗ {exc}")
        return 1
    if audio_base:
        print(f"✓ Audio folder: {audio_base}")
    else:
        print("○ Audio folder: not set (MP3s can live in each episode folder instead)")
        print("  Tip: set RSSCOM_AUDIO_DIR in .env to your recordings folder.")

    season = episode_season({}, podcast_config)
    next_number, latest = client.next_episode_number(season)
    if latest is None:
        print(f"✓ Next episode: Season {season}, Episode {next_number} (first in season)")
    else:
        print(f"✓ Next episode: Season {season}, Episode {next_number}")

    print("✓ Auto-transcription: verify enabled in RSS.com dashboard")
    print("  Settings → Transcription for your podcast.")
    print("")
    print("Ready to publish.")
    return 0


def correct_transcript(args: argparse.Namespace) -> int:
    corrections_path = Path(args.corrections).resolve()
    corrections = load_json_or_yaml(corrections_path)
    if not isinstance(corrections, dict):
        raise SystemExit(f"{corrections_path} must be a mapping of wrong: right pairs.")

    client = RssComClient(args.api_key, args.podcast_id, dry_run=args.dry_run)

    transcript = client.get_transcript(args.episode_id)
    fmt = transcript["format"]
    corrected, changes = apply_corrections(transcript["transcription"], corrections)

    if not changes:
        print("No corrections matched.")
        return 0

    print("Corrections to apply:")
    for wrong, right, count in changes:
        print(f"  {wrong!r} -> {right!r} ({count}x)")

    if args.dry_run:
        print("[dry-run] transcript not uploaded")
        return 0

    client.put_transcript(args.episode_id, corrected, fmt)
    print("Transcript updated.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare RSS.com episode drafts (upload, metadata, transcription).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("RSSCOM_API_KEY", ""),
        help="RSS.com API key (or RSSCOM_API_KEY env var)",
    )
    parser.add_argument(
        "--podcast-id",
        type=int,
        default=int(os.environ.get("RSSCOM_PODCAST_ID", "0") or 0),
        help="RSS.com podcast id (or RSSCOM_PODCAST_ID env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print API calls without sending them",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=default_timeout(),
        help="Max seconds to wait for transcode/transcription (default: from .env or 3600)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Validate .env, config, and API connectivity",
    )
    check_parser.set_defaults(func=run_check)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Upload MP3, create draft, wait for auto transcript, apply corrections",
    )
    prepare_parser.add_argument(
        "episode_dir",
        help="Episode folder with episode.yaml, description.md, and MP3",
    )
    prepare_parser.add_argument(
        "--mp3",
        help="MP3 filename or path (resolved against RSSCOM_AUDIO_DIR when set)",
    )
    prepare_parser.set_defaults(func=prepare)

    next_parser = subparsers.add_parser(
        "next-episode",
        help="Show the next episode number for a season",
    )
    next_parser.add_argument(
        "--season",
        type=int,
        default=1,
        help="Season number (default: 1)",
    )
    next_parser.set_defaults(func=show_next_episode)

    fix_parser = subparsers.add_parser(
        "correct-transcript",
        help="Re-apply typo corrections to an existing episode transcript",
    )
    fix_parser.add_argument("episode_id", type=int, help="RSS.com episode id")
    fix_parser.add_argument("corrections", help="Path to corrections.yaml or .json")
    fix_parser.set_defaults(func=correct_transcript)

    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    if args.command != "check":
        if not args.api_key:
            print(
                "Missing API key. Add RSSCOM_API_KEY to .env or pass --api-key.",
                file=sys.stderr,
            )
            return 2
        if not args.podcast_id:
            print(
                "Missing podcast id. Add RSSCOM_PODCAST_ID to .env or pass --podcast-id.",
                file=sys.stderr,
            )
            return 2

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
