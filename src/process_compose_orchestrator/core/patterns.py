"""Pure helpers over ``<scope>[/<service-glob>]`` patterns."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass(frozen=True)
class ScopePattern:
    """One parsed pattern. A bare ``<scope>`` expands to ``<scope>/*``."""

    scope: str
    service: str

    @classmethod
    def parse(cls, token: str) -> ScopePattern:
        if "/" not in token:
            return cls(token, "*")
        scope, service = token.split("/", 1)
        return cls(scope, service or "*")

    @property
    def scope_is_concrete(self) -> bool:
        return bool(self.scope) and "*" not in self.scope and "?" not in self.scope and "[" not in self.scope

    @property
    def covers_whole_scope(self) -> bool:
        return self.service == "*"


def matches(patterns: list[ScopePattern], scope: str, service: str) -> bool:
    """True when *service* in *scope* matches any pattern; an empty list matches everything."""
    if not patterns:
        return True
    return any(fnmatch.fnmatchcase(scope, p.scope) and fnmatch.fnmatchcase(service, p.service) for p in patterns)
