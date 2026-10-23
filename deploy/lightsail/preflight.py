"""Fail closed if the initial Lightsail soak configuration changes; never log secrets."""
import os
from pathlib import Path


def main():
    required = {
        "ENABLE_OPENAI_ANALYST": "false",
        "ENABLE_LOCAL_RETENTION": "false",
        "ENABLE_SUPABASE_SYNC": "true",
        "ENABLE_CLOUD_LIFECYCLE": "true",
        "FASTAPI_HOST": "127.0.0.1",
        "FASTAPI_PORT": "8000",
        "FASTAPI_RELOAD": "false",
        "SQLITE_DB_PATH": "data/btc_intelligence.db",
    }
    for key, expected in required.items():
        if os.environ.get(key) != expected:
            raise SystemExit(f"Initial soak configuration refused: {key}")
    for key in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "POLYMARKET_KEY_ID", "POLYMARKET_SECRET_KEY"):
        if not os.environ.get(key):
            raise SystemExit(f"Required configuration missing: {key}")
    if any(os.environ.get(key) for key in ("OPENAI_API_KEY", "OPENAPIKEY", "OPENAI_KEY")):
        raise SystemExit("OpenAI credentials must be absent from the initial deployment")
    if not Path(required["SQLITE_DB_PATH"]).is_file():
        raise SystemExit("Migrate and verify SQLite before starting services")
    print("Initial soak configuration verified: OpenAI off, retention off")


if __name__ == "__main__":
    main()
