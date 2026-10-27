"""Canonical alert levels and source identifiers."""

ALERT_LEVELS = ("yellow", "orange", "red")

ALERT_SOURCES = (
    "rule",
    "ai_stalwart",
    "ai_gan_ae",
    "ai_isolation_forest",
    "ai_dual_confirm",
    "ai_feature_arbitration",
)

AI_ALERT_SOURCES = frozenset(
    source for source in ALERT_SOURCES if source.startswith("ai_")
)
