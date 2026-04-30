# Makefile for cppcheck_misra_agents_bundle_v2
# Usage: make release

SHELL := /bin/bash
ROOT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

# Read version from cli/VERSION (strip leading 'v' if present)
VERSION_RAW := $(shell cat $(ROOT_DIR)/cli/VERSION 2>/dev/null || echo "unknown")
VERSION := $(VERSION_RAW)

# Distribution directory
DIST_DIR := $(ROOT_DIR)/dist
RELEASE_NAME := agents-$(VERSION)
RELEASE_ARCHIVE := $(DIST_DIR)/$(RELEASE_NAME).tar.gz

# Files and directories to include in the release archive
RELEASE_INCLUDES := \
	cli/ \
	.agents/config/ \
	.agents/compat/ \
	.agents/prompts/ \
	.agents/skills/ \
	.agents/tools/ \
	README.md \
	AGENTS.md \
	install.sh \
	install.bat

# Git remote URL for tag push
GIT_REMOTE ?= origin

.PHONY: help version test clean release tag check

help:
	@echo "MISRA Pipeline CLI - Release Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make version       Show current version from cli/VERSION"
	@echo "  make test          Run all tests"
	@echo "  make check         Pre-release checks (tests + version valid)"
	@echo "  make release       Build release archive: $(RELEASE_ARCHIVE)"
	@echo "  make tag           Create and push git tag v$(VERSION)"
	@echo "  make clean         Remove dist/ directory"
	@echo ""
	@echo "Variables:"
	@echo "  VERSION=$(VERSION)"
	@echo "  DIST_DIR=$(DIST_DIR)"
	@echo "  GIT_REMOTE=$(GIT_REMOTE)"

version:
	@echo "$(VERSION)"

test:
	@echo "Running tests..."
	@cd $(ROOT_DIR) && python3 -m pytest tests/ -v --tb=short

check: test
	@if [ "$(VERSION)" = "unknown" ]; then \
		echo "Error: Could not read version from cli/VERSION"; \
		exit 1; \
	fi
	@echo "Pre-release checks passed."
	@echo "Version: $(VERSION)"

$(DIST_DIR):
	@mkdir -p $(DIST_DIR)

release: check $(DIST_DIR)
	@echo "Building release archive: $(RELEASE_ARCHIVE)"
	@echo "Version: $(VERSION)"
	@echo ""
	@echo "Including:"
	@for item in $(RELEASE_INCLUDES); do \
		echo "  $$item"; \
	done
	@echo ""
	@echo "Excluding: __pycache__, .pytest_cache, .agents/runs/, .agents/staging/, .agents/runtime/, .agents/reports/"
	@echo ""
	@cd $(ROOT_DIR) && tar -czf $(RELEASE_ARCHIVE) \
		--exclude='__pycache__' \
		--exclude='.pytest_cache' \
		--exclude='.agents/runs' \
		--exclude='.agents/staging' \
		--exclude='.agents/runtime' \
		--exclude='.agents/reports' \
		$(RELEASE_INCLUDES)
	@echo "Release archive created:"
	@echo "  $(RELEASE_ARCHIVE)"
	@echo ""
	@ls -lh $(RELEASE_ARCHIVE)
	@echo ""
	@echo "Next steps:"
	@echo "  1. git tag $(VERSION)"
	@echo "  2. git push $(GIT_REMOTE) $(VERSION)"
	@echo "  3. Upload $(RELEASE_ARCHIVE) to GitHub/GitLab Release"

tag:
	@if [ "$(VERSION)" = "unknown" ]; then \
		echo "Error: Could not read version from cli/VERSION"; \
		exit 1; \
	fi
	@echo "Creating git tag: $(VERSION)"
	@cd $(ROOT_DIR) && git tag -a "$(VERSION)" -m "Release $(VERSION)"
	@echo "Pushing tag to $(GIT_REMOTE)..."
	@cd $(ROOT_DIR) && git push $(GIT_REMOTE) "$(VERSION)"
	@echo "Tag $(VERSION) created and pushed."

clean:
	@echo "Cleaning dist directory..."
	@rm -rf $(DIST_DIR)
	@echo "Done."
