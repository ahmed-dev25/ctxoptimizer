"""License checks (SPEC section 19).

v1 ships a stub with enforcement disabled (ADR 0002). Nothing outside this
module may import its internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LICENSE_ENFORCEMENT: Literal["on", "off"] = "off"


@dataclass(frozen=True, slots=True)
class LicenseStatus:
    """Result of a license check."""

    tier: str
    valid: bool
    enforcement: Literal["on", "off"]
    reason: str


def is_active_mode_allowed() -> bool:
    """Return whether active mode may run.

    Enforcement is disabled in this build, so active mode is always allowed.
    """
    return True


def license_status() -> LicenseStatus:
    """Return the current license status."""
    return LicenseStatus(
        tier="unlicensed",
        valid=False,
        enforcement=LICENSE_ENFORCEMENT,
        reason="license enforcement disabled in this build",
    )
