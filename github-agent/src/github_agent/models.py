from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    scanner: str
    finding_id: str
    title: str
    severity: str
    target: str
    package_name: str | None = None
    installed_version: str | None = None
    fixed_version: str | None = None
    description: str | None = None
    references: tuple[str, ...] = ()

    @property
    def normalized_severity(self) -> str:
        return self.severity.strip().lower() or "unknown"

    @property
    def dedupe_key(self) -> str:
        parts = [
            self.scanner.strip().lower(),
            self.finding_id.strip().lower(),
            self.target.strip().lower(),
            (self.package_name or "").strip().lower(),
        ]
        return ":".join(parts)


@dataclass(frozen=True)
class IssueProposal:
    title: str
    body: str
    labels: list[str] = field(default_factory=list)
    dedupe_key: str = ""

