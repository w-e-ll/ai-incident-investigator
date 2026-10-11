"""Create local configuration and strong Docker passwords without printing secrets."""

import secrets
from pathlib import Path

from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if not path.exists():
    path.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
values = dotenv_values(path)
with path.open("a", encoding="utf-8") as handle:
    for key in ("POSTGRES_ADMIN_PASSWORD", "APP_DB_PASSWORD"):
        if not values.get(key):
            handle.write(f"\n{key}={secrets.token_urlsafe(32)}\n")
print(
    "Local configuration is ready. Existing credentials were preserved; generated secrets were not printed."
)
