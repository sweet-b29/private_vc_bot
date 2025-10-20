
from __future__ import annotations
from typing import Tuple, Optional
from datetime import datetime
from .. import config
from ..db import DB

def check_can_create(db: DB, user_id: int) -> Tuple[bool, Optional[str]]:
    """Return (allowed, reason_if_denied). Also sets cooldown if needed."""
    db.clear_expired_blocks()
    blocked_until = db.get_block_until(user_id)
    if blocked_until and blocked_until > datetime.utcnow():
        wait = int((blocked_until - datetime.utcnow()).total_seconds() // 60) + 1
        return False, f"⏳ Антиспам: вы временно ограничены. Подождите ~{wait} мин."

    count = db.count_creations_since(user_id, config.ANTISPAM_WINDOW_MIN)
    if count >= config.ANTISPAM_THRESHOLD:
        # достигнут порог за окно — блокируем на cooldown
        db.set_block(user_id, config.ANTISPAM_COOLDOWN_MIN)
        return False, f"⏳ Антиспам: за {config.ANTISPAM_WINDOW_MIN} мин вы уже создали {count} канал(а). Новый можно через {config.ANTISPAM_COOLDOWN_MIN} мин."
    return True, None

def after_created(db: DB, user_id: int):
    db.record_creation(user_id)
    # Если это было третье создание за окно — сразу ставим блок
    count = db.count_creations_since(user_id, config.ANTISPAM_WINDOW_MIN)
    if count >= config.ANTISPAM_THRESHOLD:
        db.set_block(user_id, config.ANTISPAM_COOLDOWN_MIN)
