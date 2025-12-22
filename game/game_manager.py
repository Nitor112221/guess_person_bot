from typing import Dict, Any, Optional, List
import logging
from game.game_state import GameState, GameStatus
from database_manager import DatabaseManager

logger = logging.getLogger(__name__)


class GameStorageManager:
    """Управление хранением игровых состояний и работа с БД"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.active_games: Dict[int, GameState] = {}

    # ===== Работа с активными играми (in-memory) =====

    def create_game(self, lobby_id: int, players_data: Dict[int, str]) -> GameState:
        """Создание новой игровой сессии"""
        game_state = GameState(lobby_id)
        game_state.status = GameStatus.PLAYING

        for user_id, role in players_data.items():
            game_state.add_player(user_id, role)

        self.active_games[lobby_id] = game_state
        return game_state

    def get_game(self, lobby_id: int) -> Optional[GameState]:
        """Получение состояния игры"""
        return self.active_games.get(lobby_id)

    def remove_game(self, lobby_id: int) -> bool:
        """Удаление игры из памяти"""
        if lobby_id in self.active_games:
            del self.active_games[lobby_id]
            return True
        return False

    def get_game_by_player(self, user_id: int) -> Optional[GameState]:
        """Поиск игры по ID игрока"""
        for game_state in self.active_games.values():
            if game_state.has_player(user_id):
                return game_state
        return None

    # ===== Работа с историей вопросов (БД) =====

    def save_question_history(
            self,
            lobby_id: int,
            user_id: int,
            question_text: str
    ) -> int:
        """Сохранение вопроса в историю"""
        try:
            self.db.cursor.execute(
                """
                INSERT INTO question_history (lobby_id, user_id, question_text)
                VALUES (?, ?, ?)
                """,
                (lobby_id, user_id, question_text)
            )
            self.db._connection.commit()
            question_id = self.db.cursor.lastrowid
            logger.info(f"Вопрос сохранен: ID={question_id}, user={user_id}")
            return question_id
        except Exception as e:
            logger.error(f"Ошибка сохранения вопроса: {e}")
            return -1

    def update_question_votes(
            self,
            question_id: int,
            yes_votes: int,
            no_votes: int
    ) -> bool:
        """Обновление результатов голосования для вопроса"""
        try:
            self.db.cursor.execute(
                """
                UPDATE question_history 
                SET votes_yes = ?, votes_no = ?
                WHERE id = ?
                """,
                (yes_votes, no_votes, question_id)
            )
            self.db._connection.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления голосов: {e}")
            return False

    def get_player_question_history(
            self,
            user_id: int,
            lobby_id: int,
            limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Получение истории вопросов игрока"""
        try:
            self.db.cursor.execute(
                """
                SELECT id, question_text, asked_at, votes_yes, votes_no
                FROM question_history
                WHERE user_id = ? AND lobby_id = ?
                ORDER BY asked_at DESC
                LIMIT ?
                """,
                (user_id, lobby_id, limit)
            )

            rows = self.db.cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "text": row[1],
                    "asked_at": row[2],
                    "yes_votes": row[3],
                    "no_votes": row[4]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}")
            return []

    def cleanup_game_history(self, lobby_id: int) -> bool:
        """Очистка истории игры"""
        try:
            self.db.cursor.execute(
                "DELETE FROM question_history WHERE lobby_id = ?",
                (lobby_id,)
            )
            self.db._connection.commit()
            logger.info(f"История очищена для лобби {lobby_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки истории: {e}")
            return False

    # ===== Работа с ролями (БД) =====

    def save_player_roles(
            self,
            lobby_id: int,
            roles: Dict[int, str]
    ) -> bool:
        """Сохранение ролей игроков в БД"""
        try:
            for user_id, role in roles.items():
                self.db.cursor.execute(
                    """
                    UPDATE lobby_players
                    SET player_character = ?
                    WHERE lobby_id = ? AND user_id = ?
                    """,
                    (role, lobby_id, user_id)
                )
            self.db._connection.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения ролей: {e}")
            return False

    def clear_player_roles(self, lobby_id: int) -> bool:
        """Очистка ролей игроков"""
        try:
            self.db.cursor.execute(
                """
                UPDATE lobby_players
                SET player_character = ''
                WHERE lobby_id = ?
                """,
                (lobby_id,)
            )
            self.db._connection.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка очистки ролей: {e}")
            return False

    # ===== Статистика и метрики =====

    def get_active_games_count(self) -> int:
        """Количество активных игр"""
        return len(self.active_games)

    def get_total_players_online(self) -> int:
        """Общее количество игроков онлайн"""
        total = 0
        for game_state in self.active_games.values():
            total += game_state.get_player_count()
        return total
