"""Clock alignment and sampled-signal matching, with the legacy API preserved."""

from .alignment import Alignment, estimate_alignment
from .diagnostics import synchronization_report
from .matching import AlignedPressureFrame, interpolate_pressure
from .matching import legacy_nearest_synchronize as synchronize

__all__ = ["AlignedPressureFrame", "Alignment", "estimate_alignment", "interpolate_pressure",
           "synchronize", "synchronization_report"]
