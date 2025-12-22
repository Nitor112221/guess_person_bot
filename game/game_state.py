from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class GameStatus(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    VOTING = "voting"
    FINISHED = "finished"


@dataclass
class PlayerData:
    user_id: int
    role: str
    has_voted: bool = False
    questions_asked: int = 0


@dataclass
class VoteData:
    question: str
    votes: Dict[int, str] = field(default_factory=dict)  # user_id -> vote
    total_players: int = 0
    question_owner_id: int = 0


class GameState:
    """Управление состоянием одной игровой сессии"""

    def __init__(self, lobby_id: int):
        self.lobby_id = lobby_id
        self.status = GameStatus.WAITING
        self.players: Dict[int, PlayerData] = {}
        self.current_player_index = 0
        self.current_vote: Optional[VoteData] = None
        self.questions_history: List[Dict[str, Any]] = []
        self.winner_id: Optional[int] = None

    def add_player(self, user_id: int, role: str) -> None:
        """Добавление игрока в игру"""
        self.players[user_id] = PlayerData(user_id=user_id, role=role)

    def remove_player(self, user_id: int, next_player: int) -> bool:
        """Удаление игрока из игры"""
        if user_id in self.players:
            del self.players[user_id]

            # Если удалили текущего игрока, нужно пересчитать индекс
            player_ids = list(self.players.keys())
            self.current_player_index = player_ids.index(next_player)
            return True
        return False

    def get_current_player(self) -> Optional[int]:
        """Получение ID текущего игрока"""
        player_ids = list(self.players.keys())
        if not player_ids:
            return None
        return player_ids[self.current_player_index]

    def get_player_role(self, user_id: int) -> Optional[str]:
        """Получение роли игрока"""
        if user_id in self.players:
            return self.players[user_id].role
        return None

    def next_player(self) -> Optional[int]:
        """Переход к следующему игроку"""
        player_ids = list(self.players.keys())
        if not player_ids:
            return None

        self.current_player_index = (self.current_player_index + 1) % len(player_ids)
        return self.get_current_player()

    def start_vote(self, question: str, question_owner_id: int) -> None:
        """Начало голосования"""
        self.status = GameStatus.VOTING
        self.current_vote = VoteData(
            question=question,
            total_players=len(self.players) - 1,  # минус спрашивающий
            question_owner_id=question_owner_id
        )

    def add_vote(self, user_id: int, vote: str) -> bool:
        """Добавление голоса"""
        if not self.current_vote or user_id == self.current_vote.question_owner_id:
            return False

        self.current_vote.votes[user_id] = vote
        return True

    def is_voting_complete(self) -> bool:
        """Проверка завершения голосования"""
        if not self.current_vote:
            return False
        return len(self.current_vote.votes) >= self.current_vote.total_players

    def get_vote_results(self) -> Dict[str, int]:
        """Получение результатов голосования"""
        if not self.current_vote:
            return {"yes": 0, "no": 0}

        yes_votes = sum(1 for v in self.current_vote.votes.values() if v == "yes")
        no_votes = len(self.current_vote.votes) - yes_votes
        return {"yes": yes_votes, "no": no_votes}

    def end_vote(self) -> None:
        """Завершение голосования"""
        self.status = GameStatus.PLAYING
        self.current_vote = None

        # Увеличиваем счетчик вопросов у текущего игрока
        current_player = self.get_current_player()
        if current_player and current_player in self.players:
            self.players[current_player].questions_asked += 1

    def finish_game(self, winner_id: int) -> None:
        """Завершение игры"""
        self.status = GameStatus.FINISHED
        self.winner_id = winner_id

    def get_remaining_players_count(self) -> int:
        """Количество оставшихся игроков"""
        return len(self.players)

    def has_player(self, user_id: int) -> bool:
        """Проверка наличия игрока"""
        return user_id in self.players

    def get_all_players(self) -> List[int]:
        """Получение списка всех игроков"""
        return list(self.players.keys())

    def get_player_count(self) -> int:
        """Количество игроков"""
        return len(self.players)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь (для сериализации)"""
        return {
            "lobby_id": self.lobby_id,
            "status": self.status.value,
            "players": {
                str(user_id): {
                    "role": data.role,
                    "questions_asked": data.questions_asked
                }
                for user_id, data in self.players.items()
            },
            "current_player_index": self.current_player_index,
            "current_vote": self.current_vote.to_dict() if self.current_vote else None,
            "winner_id": self.winner_id
        }
