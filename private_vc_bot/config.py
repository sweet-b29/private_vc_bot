
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# Список ролей, которым разрешено управлять чужими приватками
ALLOWED_ROLE: set[int] = {
    int(x) for x in os.getenv("ALLOWED_ROLE", "").replace(" ", "").split(",") if x.isdigit()
}

# Core
DISCORD_TOKEN: str | None = os.getenv("DISCORD_TOKEN")
GUILD_ID: int = int(os.getenv("GUILD_ID", "0"))
PRIVATE_CATEGORY_ID: int = int(os.getenv("PRIVATE_CATEGORY_ID", "0"))
HUB_VOICE_CHANNEL_ID: int = int(os.getenv("HUB_VOICE_CHANNEL_ID", "0"))
LOG_CHANNEL_ID: int | None = int(os.getenv("LOG_CHANNEL_ID", "0") or "0") or None
OWNER_ROLE_ID: int | None = int(os.getenv("PRIVATE_OWNER_ROLE_ID", "0") or "0") or None

# Style
BRAND_COLOR: int = int(os.getenv("BRAND_COLOR", "0x9B59B6"), 16) if os.getenv("BRAND_COLOR") else 0x9B59B6
PANEL_TITLE: str = os.getenv("PANEL_TITLE", "⚙️ Управление приваткой")

# Behavior
DEFAULT_LIMIT: int = int(os.getenv("DEFAULT_LIMIT", "3"))
DELETE_AFTER_EMPTY_SEC: int = int(os.getenv("DELETE_AFTER_EMPTY_SEC", "180"))  # 3 мин

# Anti-spam
ANTISPAM_THRESHOLD: int = int(os.getenv("ANTISPAM_THRESHOLD", "3"))      # сколько комнат за окно
ANTISPAM_WINDOW_MIN: int = int(os.getenv("ANTISPAM_WINDOW_MIN", "10"))   # окно, минут
ANTISPAM_COOLDOWN_MIN: int = int(os.getenv("ANTISPAM_COOLDOWN_MIN", "5"))# бан после достижения порога

# Storage
DB_PATH: str = os.getenv("DB_PATH", "private_vc.sqlite3")

def require_token():
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN не задан в .env")

ALLOW_FALLBACK_TEXT_PANEL: bool = bool(int(os.getenv("ALLOW_FALLBACK_TEXT_PANEL", "0")))