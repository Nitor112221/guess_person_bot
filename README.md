# guess_person_bot
bot for game guess who 

self.db.cursor.execute(
                """
                UPDATE lobbies
                SET current_players = current_players + ?
                WHERE lobby_id = ?
                """,
                (bot_count, lobby_id,)
            )

self.db.cursor.execute(
                    """
                    INSERT INTO lobby_players (lobby_id, user_id)
                    VALUES (?, ?)
                    """,
                    (lobby_id, -bot_index)
                )