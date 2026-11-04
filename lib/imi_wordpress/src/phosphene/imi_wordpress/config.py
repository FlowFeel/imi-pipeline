"""WordPress connection configuration.

All connection parameters are sourced from environment variables via
``from_env()``. The env-var pattern (WP_URL, WP_USERNAME, WP_APP_PASSWORD)
exists because credentials must never appear in code, config files, or
commit history. Environment injection is the standard 12-factor approach
and the only pattern the deploy pipeline supports.

@dft
- A1 (pure-io-separation): imports ``os`` for env vars (allowed in config).
- A2 (determinism): no datetime/random/uuid. Frozen dataclass.
- A6 (check-result): ``from_env()`` returns a WPConfig (the proof).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WPConfig:
    """Immutable WordPress connection configuration.

    Attributes:
        url: WordPress site URL (e.g. https://independentmediainstitute.org).
        username: WordPress username for REST API authentication.
        app_password: Application password for REST API authentication.
    """

    url: str
    username: str
    app_password: str

    @classmethod
    def from_env(cls) -> WPConfig:
        """Construct WPConfig from environment variables.

        Reads WP_URL, WP_USERNAME, WP_APP_PASSWORD from the environment.

        Returns:
            A configured WPConfig instance.

        Raises:
            EnvironmentError: If any required variable is missing.
        """
        required = {"WP_URL": None, "WP_USERNAME": None, "WP_APP_PASSWORD": None}
        missing: list[str] = []
        for var in required:
            val = os.environ.get(var)
            if not val:
                missing.append(var)
            else:
                required[var] = val

        if missing:
            raise OSError(f"Missing required environment variables: {', '.join(missing)}")

        return cls(
            url=required["WP_URL"],  # type: ignore[arg-type]
            username=required["WP_USERNAME"],  # type: ignore[arg-type]
            app_password=required["WP_APP_PASSWORD"],  # type: ignore[arg-type]
        )
