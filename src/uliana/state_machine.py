from __future__ import annotations

from enum import Enum


class State(str, Enum):
    READY = "ready"
    DESCENDING = "descending"
    DOWN = "down"
    ASCENDING = "ascending"


class PushUpStateMachine:
    def __init__(self, up_angle_deg: float = 150, down_angle_deg: float = 135, hysteresis_deg: float = 5):
        if down_angle_deg >= up_angle_deg:
            raise ValueError("down threshold must be lower than up threshold")
        self.up = up_angle_deg
        self.down = down_angle_deg
        self.hysteresis = hysteresis_deg
        self.state = State.READY
        self.rep_count = 0
        self.previous_angle = up_angle_deg

    def reset(self) -> None:
        """Discard an incomplete cycle after a measurement gap; completed count is retained."""
        self.state = State.READY
        self.previous_angle = self.up

    def update(self, angle: float) -> bool:
        falling = angle < self.previous_angle
        rising = angle > self.previous_angle
        complete = False
        if self.state == State.READY and falling and angle < self.up - self.hysteresis:
            self.state = State.DESCENDING
        elif self.state == State.DESCENDING and angle <= self.down:
            self.state = State.DOWN
        elif self.state == State.DOWN and rising and angle > self.down + self.hysteresis:
            self.state = State.ASCENDING
        elif self.state == State.ASCENDING and angle >= self.up:
            self.state = State.READY
            self.rep_count += 1
            complete = True
        self.previous_angle = angle
        return complete
