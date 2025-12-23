import random
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class ResponseQuestion:
    question: str
    is_guess: bool


class BotPlayer:
    """Игрок-бот с искусственным интеллектом"""

    def __init__(self, bot_id: int, role: str):
        self.id = bot_id  # Отрицательный ID для ботов
        self.history: List[Tuple[str, str]] = []
        self.assigned_role: str = ""  # Роль, которая назначена боту (скрыта от него)

    def ask(self) -> ResponseQuestion:
        # TODO: реализация вопроса
        return ResponseQuestion(question="Test", is_guess=False)

    def ans_for_question(self, target_role: str, question: str) -> bool:
        # TODO: реализация ответа
        return random.choice([True, False])

    def add_fact(self, question: str, answer: bool):
        """Добавляет известный факт в историю"""
        self.history.append((question, "Да" if answer else "Нет"))

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            "id": self.id,
            "role": self.assigned_role,
            "history": self.history,
            "is_bot": True
        }