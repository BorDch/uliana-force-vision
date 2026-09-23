"""ULIANA fusion module - push-up technique assessment.

Provides assessment functions for all five criteria from the scientific rationale:

1. Body alignment (lower back deflection) - ASSESSED
   assess_body_alignment()
   Reference: https://doi.org/10.1519/SSC.0b013e31826d877b

2. Elbow-to-torso flare - ASSESSED  
   assess_elbow_to_torso_flare()
   Reference: https://doi.org/10.4085/1062-6050-48.5.08

3. Head/neck alignment - ASSESSED
   assess_head_neck_alignment()
   Reference: https://doi.org/10.1519/SSC.0b013e31826d877b

4. Range of motion (depth) - ASSESSED
   assess_depth_proxy()
   Reference: https://doi.org/10.1519/jsc.0000000000004415

5. Hand placement - ASSESSED
   assess_hand_placement()
   References: https://pubmed.ncbi.nlm.nih.gov/2334780/, https://doi.org/10.1016/0021-9290(93)90026-b

Pressure-based assessments (require smart mat):
- assess_pressure_balance()
- assess_hand_pressure_stability()
- assess_pressure_signal_quality()
"""

from .assessments import (
    assess_body_alignment,
    assess_depth_proxy,
    assess_pressure_balance,
    assess_pressure_signal_quality,
    assess_hand_pressure_stability,
)
from .criteria_v2 import (
    assess_head_neck_alignment,
    assess_elbow_to_torso_flare,
    assess_hand_placement,
)
from .reliability import condition_gate, pressure_condition_gate

__all__ = [
    # Camera-based technique assessments (all 5 criteria)
    "assess_body_alignment",        # Criterion 1: Lower back deflection
    "assess_depth_proxy",           # Criterion 4: Range of motion
    "assess_head_neck_alignment",   # Criterion 3: Head/neck position
    "assess_elbow_to_torso_flare",  # Criterion 2: Elbow angle
    "assess_hand_placement",        # Criterion 5: Hand position
    
    # Pressure-based assessments (require smart mat)
    "assess_pressure_balance",
    "assess_hand_pressure_stability",
    "assess_pressure_signal_quality",
    
    # Utility functions
    "condition_gate",
    "pressure_condition_gate",
]
