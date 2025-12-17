import threading
import sqlite3


class SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            return cls._instances[cls]


class DatabaseManager(metaclass=SingletonMeta):
    def __init__(self, db_name="data/database.db"):
        if not hasattr(self, "connection"):
            self.db_name = db_name
            self._connection = None
            self.cursor = None
            self._connect()

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
        self._connection.commit()

    def disconnect(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
