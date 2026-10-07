from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GatewayResult:
    success: bool
    reason: str | None = None
