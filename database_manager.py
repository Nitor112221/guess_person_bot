import threading
import sqlite3
from typing import Optional


class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, db_name: str = "data/database.db"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.db_name = db_name
                cls._instance._connection = None
                cls._instance.cursor = None
            return cls._instance

    def __init__(self, db_name="data/database.db"):
        if hasattr(self, "_initialized") and self._initialized:
            return

        with self._lock:
            if not self._initialized:
                self._connect()
                self._initialized = True

    def _connect(self):
        # flag = False
        # if not os.path.exists(self.db_name):
        #     flag = True

        if self._connection is None:
            self._connection = sqlite3.connect(self.db_name, check_same_thread=False)
            self.cursor = self._connection.cursor()

        # if flag:
        #     self.create_tables()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lobbies (
                lobby_id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                max_players INTEGER DEFAULT 4,
                current_players INTEGER DEFAULT 1,
                is_private BOOLEAN DEFAULT FALSE,
                has_bots BOOLEAN DEFAULT FALSE,
                invite_code TEXT DEFAULT '',
                host_id INTEGER
            )
            """
        )

        # Создадим также таблицу для игроков в лобби
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lobby_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lobby_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                player_character TEXT DEFAULT '',
                FOREIGN KEY (lobby_id) REFERENCES lobbies(lobby_id) ON DELETE CASCADE
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS question_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lobby_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                asked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                votes_yes INTEGER DEFAULT 0,
                votes_no INTEGER DEFAULT 0,
                FOREIGN KEY (lobby_id) REFERENCES lobbies(lobby_id) ON DELETE CASCADE
            )
            """
        )

        self._connection.commit()

    def disconnect(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
