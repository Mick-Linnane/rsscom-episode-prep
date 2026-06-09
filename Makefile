PYTHON ?= python3
SCRIPT := prepare_episode.py
EPISODE ?= episodes/example
SEASON ?= 1
TIMEOUT ?= 3600

.PHONY: help check dry-run publish fix-transcript next-episode

help:
	@echo "RSS.com Episode Prep — from script to draft, one folder, one command."
	@echo ""
	@echo "Setup (once):"
	@echo "  cp .env.example .env           # paste API key, podcast id, audio folder"
	@echo "  edit podcast.config.yaml       # show name, title template, defaults"
	@echo "  make check                     # verify everything is ready"
	@echo ""
	@echo "Every episode:"
	@echo "  make dry-run EPISODE=episodes/my-episode    Preview title and payload"
	@echo "  make publish EPISODE=episodes/my-episode    Upload and create draft"
	@echo ""
	@echo "Other:"
	@echo "  make fix-transcript EPISODE_ID=123 CORRECTIONS=episodes/foo/corrections.yaml"
	@echo ""
	@echo "Variables:"
	@echo "  EPISODE      Episode folder (default: $(EPISODE))"
	@echo "  MP3          Audio filename or path (optional)"
	@echo "  TIMEOUT      Processing timeout in seconds (default: $(TIMEOUT))"
	@echo "  EPISODE_ID   RSS.com episode id (fix-transcript)"
	@echo "  CORRECTIONS  Path to corrections file (fix-transcript)"

check:
	$(PYTHON) $(SCRIPT) check

dry-run:
	$(PYTHON) $(SCRIPT) --dry-run --timeout $(TIMEOUT) prepare $(EPISODE) \
		$(if $(MP3),--mp3 "$(MP3)",)

publish:
	$(PYTHON) $(SCRIPT) --timeout $(TIMEOUT) prepare $(EPISODE) \
		$(if $(MP3),--mp3 "$(MP3)",)

fix-transcript:
	@test -n "$(EPISODE_ID)" || (echo "Set EPISODE_ID=..." && exit 1)
	@test -n "$(CORRECTIONS)" || (echo "Set CORRECTIONS=path/to/corrections.yaml" && exit 1)
	$(PYTHON) $(SCRIPT) correct-transcript $(EPISODE_ID) $(CORRECTIONS)

next-episode:
	$(PYTHON) $(SCRIPT) next-episode --season $(SEASON)
