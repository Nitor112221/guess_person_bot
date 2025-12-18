import secrets
from typing import Optional, Dict, Any


class LobbyManager:
    def __init__(self, db_manager):
        self.db = db_manager

    def generate_invite_code(self) -> str:
        """Генерация уникального кода приглашения"""
        return secrets.token_urlsafe(8).upper().replace("_", "").replace("-", "")[:8]

    def create_lobby(
        self, host_id: int, max_players: int = 4, is_private: bool = False
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

    def get_lobby_by_code(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """Получение информации о лобби по коду приглашения"""
        self.db.cursor.execute(
            """
            SELECT lobby_id, status, max_players, current_players, 
                    is_private, host_id, invite_code
            FROM lobbies 
            WHERE invite_code = ? AND status = 'waiting'
            """,
            (invite_code,),
        )

        row = self.db.cursor.fetchone()
        if not row:
            return None

        lobby = {
            "lobby_id": row[0],
            "status": row[1],
            "max_players": row[2],
            "current_players": row[3],
            "is_private": row[4],
            "host_id": row[5],
            "invite_code": row[6],
        }

        return lobby

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
            if lobby["is_private"]:
                ...
                # TODO

            # Проверяем, не присоединен ли уже пользователь
            self.db.cursor.execute(
                """
                SELECT user_id FROM lobby_players 
                WHERE lobby_id = ? AND user_id = ?
                """,
                (lobby["lobby_id"], user_id),
            )

            if self.db.cursor.fetchone():
                return {"success": False, "message": "Вы уже находитесь в этом лобби"}

            # Проверяем количество игроков
            if lobby["current_players"] >= lobby["max_players"]:
                return {"success": False, "message": "Лобби заполнено"}

            # Добавляем игрока в лобби
            self.db.cursor.execute(
                """
                INSERT INTO lobby_players (lobby_id, user_id)
                VALUES (?, ?)
                """,
                (lobby["lobby_id"], user_id),
            )

            # Обновляем счетчик игроков
            self.db.cursor.execute(
                """
                UPDATE lobbies 
                SET current_players = current_players + 1 
                WHERE lobby_id = ?
                """,
                (lobby["lobby_id"],),
            )

            self.db._connection.commit()

            return {
                "success": True,
                "lobby_id": lobby["lobby_id"],
                "message": "Вы успешно присоединились к лобби",
            }

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при присоединении к лобби",
            }

    def get_lobby_info(self, lobby_id: int) -> Dict[str, Any]:
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

        lobby = {
            "lobby_id": row[0],
            "status": row[1],
            "created_at": row[2],
            "max_players": row[3],
            "current_players": row[4],
            "is_private": row[5],
            "host_id": row[6],
            "invite_code": row[7],
        }

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

        lobby["players"] = players
        return lobby

    def leave_lobby(self, user_id: int, lobby_id: int) -> Dict[str, Any]:
        """Выход из лобби"""
        try:
            # Удаляем игрока из лобби
            self.db.cursor.execute(
                """
                DELETE FROM lobby_players 
                WHERE lobby_id = ? AND user_id = ?
                """,
                (lobby_id, user_id),
            )

            if self.db.cursor.rowcount == 0:
                return {"success": False, "message": "Игрок не найден в лобби"}

            # Обновляем счетчик игроков
            self.db.cursor.execute(
                """
                UPDATE lobbies 
                SET current_players = current_players - 1 
                WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            # Проверяем, остались ли игроки в лобби
            self.db.cursor.execute(
                """
                SELECT current_players FROM lobbies WHERE lobby_id = ?
                """,
                (lobby_id,),
            )

            remaining_players = self.db.cursor.fetchone()[0]

            # Если лобби пустое, удаляем его
            if remaining_players == 0:
                self.db.cursor.execute(
                    "DELETE FROM lobbies WHERE lobby_id = ?", (lobby_id,)
                )
            # Если вышел хост, назначаем нового хоста
            else:
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

            return {"success": True, "message": "Вы вышли из лобби"}

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при выходе из лобби",
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

    def end_game(self, lobby_id: int) -> Dict[str, Any]:
        """Завершение игры"""
        try:
            ...
            # TODO

        except Exception as e:
            self.db._connection.rollback()
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при начале игры",
            }

    def get_lobby_by_used_id(self, user_id: int):
        # TODO: требуется реализация
        pass
