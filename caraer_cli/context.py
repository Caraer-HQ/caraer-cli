from __future__ import annotations

from dataclasses import dataclass

from caraer_cli.api.client import CaraerApiClient, RequestContext
from caraer_cli.state import session as session_store
from caraer_cli.state.config import CliConfig, ProfileConfig


@dataclass
class AppContext:
    config: CliConfig
    profile_name: str
    profile: ProfileConfig
    token: str | None
    output: str
    debug: bool

    @property
    def pinned_app_file(self) -> str | None:
        """The profile's pinned app, unless you are standing in an app."""
        from caraer_cli.project.paths import app_file_unless_in_workspace

        return app_file_unless_in_workspace(self.profile.app_file)

    def api_client(self) -> CaraerApiClient:
        profile_name = self.profile_name

        def _persist(access: str, refresh: str | None) -> None:
            session_store.set_session_token(
                profile_name, access, refresh_token=refresh
            )
            self.token = access

        return CaraerApiClient(
            RequestContext(
                base_url=self.profile.base_url,
                token=self.token,
                company_uuid=self.profile.company_uuid,
                sandbox_uuid=self.profile.sandbox_uuid,
                timeout_seconds=self.profile.timeout_seconds,
                verify_ssl=self.profile.verify_ssl,
                debug=self.debug,
                profile_name=self.profile_name,
                refresh_token=session_store.get_refresh_token(self.profile_name),
                on_tokens_refreshed=_persist,
            )
        )
