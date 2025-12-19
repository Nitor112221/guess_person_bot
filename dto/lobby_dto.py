from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class LobbyDTO:
    lobby_id: int
    status: str
    created_at: str
    max_players: int
    current_players: int
    is_private: bool
    host_id: int
    invite_code: str
    players: List[Dict[str, Any]] = field(default_factory=list)
