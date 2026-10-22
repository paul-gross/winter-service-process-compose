"""Manifest errors."""

from __future__ import annotations


class ManifestError(Exception):
    """The manifest cannot be read, parsed, or accepted by this provider."""


class ManifestNotFoundError(ManifestError):
    """No ``config.toml`` exists in the config directory."""
