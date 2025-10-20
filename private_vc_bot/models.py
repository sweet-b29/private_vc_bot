
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class PrivateRoom:
    voice_channel_id: int
    owner_id: int
    panel_channel_id: Optional[int]  # может быть ID voice (Text-in-Voice) или текстового канала
    is_locked: bool
    user_limit: int
