"""Optional private-foundry overlay contract.

The tracked manifest defines names and precedence only.  Actual foundry files
are resolved from an environment-selected absolute directory and never from
Git-tracked profile data.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


class OracleOverlayError(ValueError):
    """Raised when a private overlay manifest is unsafe or malformed."""


@dataclass(frozen=True)
class OracleOverlay:
    profile: str
    status: str
    authority: str
    root_environment: str
    artifacts: tuple[tuple[str, str], ...]

    @property
    def installed(self) -> bool:
        return self.status == "active"

    def root(self, environ: dict[str, str] | None = None) -> Path | None:
        values = os.environ if environ is None else environ
        value = values.get(self.root_environment)
        if not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise OracleOverlayError(
                f"{self.root_environment} must point to an absolute private overlay root"
            )
        return path

    def artifact_paths(self, environ: dict[str, str] | None = None) -> dict[str, Path]:
        root = self.root(environ)
        if root is None:
            return {}
        return {name: root / relative for name, relative in self.artifacts}


def load_oracle_overlay(document: dict[str, Any], profile: str) -> OracleOverlay:
    if document.get("schema_version") != 1:
        raise OracleOverlayError("schema_version must be 1")
    if document.get("profile") != profile:
        raise OracleOverlayError(
            f"profile {document.get('profile')!r} does not match {profile!r}"
        )
    if document.get("authority") != "foundry_private":
        raise OracleOverlayError("oracle overlay authority must be foundry_private")
    root_environment = document.get("root_environment")
    if not isinstance(root_environment, str) or not root_environment:
        raise OracleOverlayError("root_environment is required")
    artifacts: list[tuple[str, str]] = []
    for name, raw in (document.get("artifacts") or {}).items():
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            raise OracleOverlayError(f"artifact {name!r} needs relative_path")
        relative = Path(raw["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise OracleOverlayError(
                f"artifact {name!r} must remain relative to the private overlay root"
            )
        artifacts.append((str(name), str(relative)))
    return OracleOverlay(
        profile=profile,
        status=str(document.get("status") or "optional_not_installed"),
        authority="foundry_private",
        root_environment=root_environment,
        artifacts=tuple(sorted(artifacts)),
    )
