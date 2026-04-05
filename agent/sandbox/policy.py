from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List


@dataclass
class CircuitBreaker:
    window_seconds: int = 60
    failure_threshold: int = 5
    open_seconds: int = 30
    _failure_timestamps: List[datetime] = field(default_factory=list)
    _open_until: datetime | None = None

    def allow(self) -> bool:
        now = datetime.now(timezone.utc)
        if self._open_until and now < self._open_until:
            return False
        if self._open_until and now >= self._open_until:
            self._open_until = None
        return True

    def record_success(self) -> None:
        self._trim()
        if self._failure_timestamps:
            self._failure_timestamps.pop(0)

    def record_failure(self) -> None:
        self._trim()
        self._failure_timestamps.append(datetime.now(timezone.utc))
        if len(self._failure_timestamps) >= self.failure_threshold:
            self._open_until = datetime.now(timezone.utc) + timedelta(seconds=self.open_seconds)

    def _trim(self) -> None:
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=self.window_seconds)
        self._failure_timestamps = [item for item in self._failure_timestamps if item >= threshold]


@dataclass(frozen=True)
class AutoscalingPolicy:
    max_instances: int = 1000
    scale_out_cpu_utilization_le: float = 0.80
    scale_in_cpu_utilization_ge: float = 0.35

    def should_scale_out(self, cpu_utilization: float, current_instances: int) -> bool:
        return current_instances < self.max_instances and cpu_utilization <= self.scale_out_cpu_utilization_le

    def should_scale_in(self, cpu_utilization: float, current_instances: int) -> bool:
        return current_instances > 1 and cpu_utilization >= self.scale_in_cpu_utilization_ge
