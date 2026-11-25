"""Runtime feature flags (the actions kill switch), stored on app.state like the bank flags so
the demo panel toggles them live without a restart. The env default (ACTIONS_ENABLED) applies
until the first toggle."""

from dataclasses import dataclass

from env.assistant import env as assistant_env


@dataclass
class FeatureFlags:
    actions_enabled: bool = True


def feature_flags_holder(request) -> FeatureFlags:
    flags = getattr(request.app.state, "feature_flags", None)
    if flags is None:
        flags = FeatureFlags(actions_enabled=assistant_env.actions_enabled)
        request.app.state.feature_flags = flags
    return flags
