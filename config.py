"""Central configuration. Everything is controlled by environment variables
(set them in Railway > your service > Variables)."""
import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# ---- Secrets -----------------------------------------------------------------
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")

# Optional: your Telegram numeric user id(s), comma separated. If empty, the
# first person who sends /start to the bot becomes the owner (and only owner).
OWNER_IDS = {int(x) for x in _env("OWNER_IDS").replace(" ", "").split(",") if x.isdigit()}

# ---- Storage -----------------------------------------------------------------
# On Railway, attach a Volume and Railway sets RAILWAY_VOLUME_MOUNT_PATH for you.
DATA_DIR = Path(_env("DATA_DIR") or _env("RAILWAY_VOLUME_MOUNT_PATH") or "./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "author.db"
EXPORT_DIR = DATA_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ---- Models (any OpenRouter model slug) ---------------------------------------
MODEL_WRITER = _env("MODEL_WRITER", "anthropic/claude-sonnet-4.5")    # prose
MODEL_PLANNER = _env("MODEL_PLANNER") or MODEL_WRITER                 # bible + outline
MODEL_EDITOR = _env("MODEL_EDITOR") or MODEL_WRITER                   # critic + memory
MODEL_FAST = _env("MODEL_FAST", "anthropic/claude-haiku-4.5")         # cheap repairs

# ---- Craft settings -----------------------------------------------------------
WORDS_PER_CHAPTER = int(_env("WORDS_PER_CHAPTER", "3000"))
MIN_SCORE = float(_env("MIN_SCORE", "8"))          # every craft score must reach this
MAX_REWRITES = int(_env("MAX_REWRITES", "2"))      # editor-driven rewrites per chapter
LENGTHS = {"short": 18, "standard": 26, "long": 34}  # chapters per book


def validate() -> None:
    missing = [k for k, v in (("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
                              ("TELEGRAM_TOKEN", TELEGRAM_TOKEN)) if not v]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
