"""Stable public constants for the ISAC profile."""

ISAC_PROFILE_VERSION = "1.0.0"

# The detector and the calibration report share one explicit, auditable default.
# Calibration can select a replacement threshold from *calibration* cases only;
# the bundled detector remains deterministic when no override is supplied.
ISAC_DEFAULT_ACTIVATION_THRESHOLD = 0.80
