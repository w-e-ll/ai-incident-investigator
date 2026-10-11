"""Backend-only configuration; credentials never cross the UI API."""

from decimal import Decimal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///var/incidents.db"
    openai_api_key: SecretStr = SecretStr("")
    investigation_model: str = "gpt-4.1-mini"
    input_usd_per_million: Decimal | None = Field(default=None, ge=0)
    output_usd_per_million: Decimal | None = Field(default=None, ge=0)
    price_as_of: str = ""

    @model_validator(mode="after")
    def published_pricing(self):
        if (
            self.investigation_model in {"gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"}
            and self.input_usd_per_million is None
            and self.output_usd_per_million is None
            and not self.price_as_of
        ):
            self.input_usd_per_million = Decimal("0.40")
            self.output_usd_per_million = Decimal("1.60")
            self.price_as_of = "2026-10-08"
        return self
