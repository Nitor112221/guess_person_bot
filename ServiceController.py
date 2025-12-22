import logging
from typing import Optional
from database_manager import DatabaseManager
from lobby.lobby_manager import LobbyManager
from game.game_logic import GameLogic

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Контейнер сервисов с правильным управлением зависимостями"""

    _instance: Optional['ServiceContainer'] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info("Инициализация ServiceContainer...")

            # Инициализируем зависимости в правильном порядке
            self.db_manager = DatabaseManager()

            # Создаем game_logic временно как None
            self._game_logic: Optional[GameLogic] = None

            # Создаем lobby_manager с game_logic=None
            self.lobby_manager = LobbyManager(self.db_manager, None)

            # Теперь создаем game_logic с lobby_manager
            self._game_logic = GameLogic(self.db_manager, self.lobby_manager)

            # Обновляем ссылку в lobby_manager
            self.lobby_manager.game_manager = self._game_logic

            self._initialized = True
            logger.info("ServiceContainer инициализирован")

    @property
    def game_logic(self) -> GameLogic:
        """Получение game_logic с гарантией инициализации"""
        if self._game_logic is None:
            raise RuntimeError("GameLogic не инициализирован!")
        return self._game_logic

    @property
    def game_manager(self):
        """Алиас для совместимости со старым кодом"""
        return self.game_logic

    def get_game_notifier(self):
        """Получение GameNotifier для тестирования"""
        return self.game_logic.notifier

    def get_game_storage(self):
        """Получение GameStorageManager для тестирования"""
        return self.game_logic.storage
