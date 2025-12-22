import logging
import secrets
from typing import Optional, Dict, Any

from telegram.ext import ContextTypes

from dto.lobby_dto import LobbyDTO

logger = logging.getLogger(__name__)

class LobbyManager:
    def __init__(self, db_manager, game_manager):
        self.db = db_manager
        self.game_manager = game_manager

    def generate_invite_code(self) -> str:
        """Генерация уникального кода приглашения"""
        return secrets.token_urlsafe(8).upper().replace("_", "").replace("-", "")[:8]

    def create_lobby(
            self, host_id: int, max_players: int = 10, is_private: bool = False
    ) -> Dict[str, Any]:
        """Создание нового лобби"""
        try:
            invite_code = self.generate_invite_code()

            self.db.cursor.execute(
                """
                INSERT INTO lobbies
                (status, max_players, is_private,
                    host_id, invite_code)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("waiting", max_players, is_private, host_id, invite_code),
            )

            lobby_id = self.db.cursor.lastrowid

            # Добавляем хоста в лобби
            self.db.cursor.execute(
                """
                INSERT INTO lobby_players (lobby_id, user_id)
                VALUES (?, ?)
                """,
                (lobby_id, host_id),
            )

            self.db._connection.commit()

            return {
                "success": True,
                "lobby_id": lobby_id,
                "invite_code": invite_code,
                "message": "Лобби успешно создано",
            }

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при создании лобби",
            }

    def get_lobby_by_code(self, invite_code: str) -> Optional[LobbyDTO]:
        """Получение информации о лобби по коду приглашения"""
        # TODO: сделать возвращаение только idшника, информацию о лобби надо узнавать только по id этого лобби
        self.db.cursor.execute(
            """
            SELECT lobby_id, status, created_at, max_players,
                    current_players, is_private, host_id, invite_code
            FROM lobbies
            WHERE invite_code = ?
            """,
            (invite_code,),
        )

        row = self.db.cursor.fetchone()
        if not row:
            return None

        lobby = LobbyDTO(
            **dict(
                zip(
                    [
                        "lobby_id",
                        "status",
                        "created_at",
                        "max_players",
                        "current_players",
                        "is_private",
                        "host_id",
                        "invite_code",
                    ],
                    row,
                )
            )
        )

        return lobby

    def get_user_lobby(self, user_id: int) -> Optional[int]:
        """Получить ID лобби, в котором находится пользователь"""
        try:
            # Ищем лобби пользователя
            self.db.cursor.execute(
                """
                SELECT l.lobby_id
                FROM lobbies l
                JOIN lobby_players lp ON l.lobby_id = lp.lobby_id
                WHERE lp.user_id = ?
                """,
                (user_id,),
            )

            lobby_data = self.db.cursor.fetchone()

            if not lobby_data:
                return None

            return lobby_data[0]

        except:
            return None

    def join_lobby(self, user_id: int, invite_code: str) -> Dict[str, Any]:
        """Присоединение к лобби по коду"""
        try:
            # Получаем информацию о лобби
            lobby = self.get_lobby_by_code(invite_code)
            if not lobby:
                return {
                    "success": False,
                    "message": "Лобби не найдено или код недействителен",
                }

            # Проверка приватности и пароля
            if lobby.is_private:
                ...
                # TODO

            # Проверяем, не присоединен ли уже пользователь
            self.db.cursor.execute(
                """
                SELECT user_id FROM lobby_players
                WHERE lobby_id = ? AND user_id = ?
                """,
                (lobby.lobby_id, user_id),
            )

            if self.db.cursor.fetchone():
                return {"success": False, "message": "Вы уже находитесь в этом лобби"}

            # Проверяем количество игроков
            if lobby.current_players >= lobby.max_players:
                return {"success": False, "message": "Лобби заполнено"}

            # Добавляем игрока в лобби
            self.db.cursor.execute(
                """
                INSERT INTO lobby_players (lobby_id, user_id)
                VALUES (?, ?)
                """,
                (lobby.lobby_id, user_id),
            )

            # Обновляем счетчик игроков
            self.db.cursor.execute(
                """
                UPDATE lobbies
                SET current_players = current_players + 1
                WHERE lobby_id = ?
                """,
                (lobby.lobby_id,),
            )

            self.db._connection.commit()

            return {
                "success": True,
                "lobby_id": lobby.lobby_id,
                "message": "Вы успешно присоединились к лобби",
            }

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при присоединении к лобби",
            }


    def get_lobby_info(self, lobby_id: int) -> Optional[LobbyDTO]:
        """Получение полной информации о лобби"""
        # Информация о лобби
        self.db.cursor.execute(
            """
            SELECT lobby_id, status, created_at, max_players,
                    current_players, is_private, host_id,
                    invite_code
            FROM lobbies
            WHERE lobby_id = ?
            """,
            (lobby_id,),
        )

        row = self.db.cursor.fetchone()
        if not row:
            return None

        lobby = LobbyDTO(
            **dict(
                zip(
                    [
                        "lobby_id",
                        "status",
                        "created_at",
                        "max_players",
                        "current_players",
                        "is_private",
                        "host_id",
                        "invite_code",
                    ],
                    row,
                )
            )
        )

        # Список игроков
        self.db.cursor.execute(
            """
            SELECT user_id, joined_at, player_character
            FROM lobby_players
            WHERE lobby_id = ?
            ORDER BY joined_at
            """,
            (lobby_id,),
        )

        players = []
        for player_row in self.db.cursor.fetchall():
            players.append(
                {
                    "user_id": player_row[0],
                    "joined_at": player_row[1],
                    "player_character": player_row[2],
                }
            )

        lobby.players = players
        return lobby

    def leave_lobby(self, user_id: int, lobby_id: int) -> Dict[str, Any]:
        """Выход из лобби с корректной обработкой игровых состояний"""
        try:
            # Шаг 1: Собираем информацию о состоянии игры ДО удаления
            exit_info = None
            game_processing_result = None

            if self.game_manager:
                # Получаем информацию о роли игрока в игре
                exit_info = self.game_manager.prepare_player_exit(lobby_id, user_id)

            # Шаг 2: Удаляем игрока из базы данных
            self.db.cursor.execute(
                """
                DELETE FROM lobby_players
                WHERE lobby_id = ? AND user_id = ?
                """,
                (lobby_id, user_id),
            )

            if self.db.cursor.rowcount == 0:
                return {"success": False, "message": "Игрок не найден в лобби"}

            # Шаг 3: Обновляем счетчик игроков
            self.db.cursor.execute(
                """
                UPDATE lobbies
                SET current_players = current_players - 1
                WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            # Шаг 4: Получаем информацию об оставшихся игроках
            self.db.cursor.execute(
                """
                SELECT current_players FROM lobbies WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            remaining_players = self.db.cursor.fetchone()[0]

            # Шаг 5: Обрабатываем игровое состояние ПОСЛЕ удаления из базы
            if self.game_manager and exit_info and exit_info.get("has_game"):
                # Здесь мы будем обрабатывать игровое состояние позже,
                # через async метод, так как нужен context
                game_processing_result = {
                    "needs_processing": True,
                    "exit_info": exit_info,
                    "remaining_players": remaining_players
                }

            # Шаг 6: Обрабатываем состояние лобби
            if remaining_players == 0:
                # Если лобби пустое, удаляем его
                self.db.cursor.execute(
                    "DELETE FROM lobbies WHERE lobby_id = ?", (lobby_id,)
                )
            else:
                # Если вышел хост, назначаем нового хоста
                self.db.cursor.execute(
                    """
                    SELECT host_id FROM lobbies WHERE lobby_id = ?
                    """,
                    (lobby_id,),
                )
                current_host = self.db.cursor.fetchone()[0]

                if current_host == user_id:
                    # Находим первого игрока в качестве нового хоста
                    self.db.cursor.execute(
                        """
                        SELECT user_id FROM lobby_players
                        WHERE lobby_id = ?
                        ORDER BY joined_at
                        LIMIT 1
                        """,
                        (lobby_id,),
                    )

                    new_host = self.db.cursor.fetchone()
                    if new_host:
                        # Обновляем хост в таблице лобби
                        self.db.cursor.execute(
                            """
                            UPDATE lobbies
                            SET host_id = ?
                            WHERE lobby_id = ?
                            """,
                            (new_host[0], lobby_id),
                        )

            self.db._connection.commit()

            return {
                "success": True,
                "message": "Вы вышли из лобби",
                "game_processing_result": game_processing_result,
                "remaining_players": remaining_players,
                "user_id": user_id,
                "lobby_id": lobby_id
            }

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при выходе из лобби",
            }

    async def complete_player_exit(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            exit_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Завершение обработки выхода игрока (async часть)"""
        if not exit_result.get("game_processing_result", {}).get("needs_processing"):
            return {"processed": False}

        processing_info = exit_result["game_processing_result"]
        lobby_id = exit_result["lobby_id"]
        user_id = exit_result["user_id"]

        # Обрабатываем игровое состояние
        game_result = await self.game_manager.process_player_exit(
            context, lobby_id, user_id, processing_info["exit_info"]
        )

        # Если игра завершилась, обновляем статус лобби
        if game_result.get("end_game"):
            try:
                self.db.cursor.execute(
                    """
                    UPDATE lobbies
                    SET status = 'waiting'
                    WHERE lobby_id = ?
                    """,
                    (lobby_id,),
                )

                # Очищаем роли у игроков
                self.db.cursor.execute(
                    """
                    UPDATE lobby_players
                    SET player_character = ''
                    WHERE lobby_id = ?
                    """,
                    (lobby_id,),
                )

                self.db._connection.commit()

                # Удаляем состояние игры
                if lobby_id in self.game_manager.active_games:
                    del self.game_manager.active_games[lobby_id]

            except Exception as e:
                logger.error(f"Ошибка при обновлении статуса лобби: {e}")

        return {
            "processed": True,
            "game_result": game_result,
            "notifications_sent": True
        }

    def start_game(self, lobby_id: int, host_id: int) -> Dict[str, Any]:
        """Начало игры"""
        try:
            # Проверяем, что пользователь является хостом
            self.db.cursor.execute(
                """
                SELECT host_id FROM lobbies WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            current_host = self.db.cursor.fetchone()
            if not current_host or current_host[0] != host_id:
                return {"success": False, "message": "Только хост может начать игру"}

            # Проверяем минимальное количество игроков
            self.db.cursor.execute(
                """
                SELECT current_players, max_players FROM lobbies WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            players_info = self.db.cursor.fetchone()
            if players_info[0] < 2:  # Минимум 2 игрока для начала
                return {
                    "success": False,
                    "message": "Для начала игры нужно минимум 2 игрока",
                }

            # Меняем статус лобби
            self.db.cursor.execute(
                """
                UPDATE lobbies
                SET status = 'playing'
                WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            self.db._connection.commit()

            return {"success": True, "message": "Игра начата"}

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при начале игры",
            }
