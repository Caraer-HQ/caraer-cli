from __future__ import annotations

from dataclasses import dataclass

from caraer_cli.api.client import CaraerApiClient, RequestContext
from caraer_cli.state.config import CliConfig, ProfileConfig


@dataclass
class AppContext:
    config: CliConfig
    profile_name: str
    profile: ProfileConfig
    token: str | None
    output: str
    debug: bool

    def api_client(self) -> CaraerApiClient:
        return CaraerApiClient(
            RequestContext(
                base_url=self.profile.base_url,
                token=self.token,
                company_uuid=self.profile.company_uuid,
                sandbox_uuid=self.profile.sandbox_uuid,
                timeout_seconds=self.profile.timeout_seconds,
                verify_ssl=self.profile.verify_ssl,
                debug=self.debug,
            )
        )
