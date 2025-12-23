import json
import random
import logging
from typing import Dict, Any, Optional, List
from telegram import Update
from telegram.ext import ContextTypes

from database_manager import DatabaseManager
from game.bot_player import BotPlayer
from game.game_state import GameState, GameStatus
from game.game_manager import GameStorageManager
from game.game_notifier import GameNotifier
from lobby.lobby_manager import LobbyManager

logger = logging.getLogger(__name__)


class GameLogic:
    """Основная игровая логика - координация всех компонентов"""

    _instance: Optional['GameLogic'] = None

    def __new__(
            cls, db_manager: DatabaseManager = None, lobby_manager: LobbyManager = None
    ):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
            self, db_manager: DatabaseManager = None, lobby_manager: LobbyManager = None
    ):
        # Защита от повторной инициализации
        if hasattr(self, "_initialized"):
            return

        if not db_manager or not lobby_manager:
            raise ValueError(
                "GameLogic требует db_manager и lobby_manager при первой инициализации"
            )

        self.db = db_manager
        self.lobby_manager = lobby_manager
        self.storage = GameStorageManager(db_manager)
        self.notifier = GameNotifier()

        self.bots: Dict[int, Dict[int, BotPlayer]] = {}

        # для совместимости с текущим кодом
        self.active_games = self.storage.active_games

        self._initialized = True

    # ===== Инициализация игры =====

    def load_roles(self) -> List[str]:
        """Загрузка ролей из файла"""
        try:
            with open('data/roles.json', 'r', encoding='utf-8') as f:
                roles = json.load(f)
            return roles
        except FileNotFoundError:
            logger.error("Файл roles.json не найден")
            return [
                "Гарри Поттер",
                "Шерлок Холмс",
                "Супермен",
                "Человек-паук",
                "Бэтмен",
                "Джеймс Бонд",
            ]
        except json.JSONDecodeError:
            logger.error("Ошибка чтения roles.json")
            return []

    def distribute_roles(self, num_players: int) -> List[str]:
        """Распределение ролей между игроками"""
        all_roles = self.load_roles()

        if len(all_roles) < num_players:
            logger.warning(
                f"Недостаточно ролей. Нужно {num_players}, есть {len(all_roles)}"
            )
            # Дублируем роли если недостаточно
            all_roles = all_roles * (num_players // len(all_roles) + 1)

        selected_roles = random.sample(all_roles, num_players)
        return selected_roles

    def start_game_session(self, lobby_id: int) -> Dict[str, Any]:
        """Начинает игровую сессию"""
        try:
            # Получаем информацию о лобби
            lobby_info = self.lobby_manager.get_lobby_info(lobby_id)
            if not lobby_info:
                return {"success": False, "message": "Лобби не найдено"}

            num_players = lobby_info.current_players
            player_ids = [player['user_id'] for player in lobby_info.players]

            # Распределяем роли
            roles_list = self.distribute_roles(num_players)
            random.shuffle(roles_list)

            # Создаем словарь player_id -> role
            roles_dict = dict(zip(player_ids, roles_list))

            logger.info(roles_dict)

            for player_id, role in roles_dict.items():
                if player_id < 0:  # Это бот
                    bot = self.create_bot_player(lobby_id, player_id, role)
                    bot.assigned_role = role

            # Сохраняем роли в БД
            self.storage.save_player_roles(lobby_id, roles_dict)

            # Создаем состояние игры
            game_state = self.storage.create_game(lobby_id, roles_dict)

            # TODO: вынести в game_manager
            # Обновляем статус лобби
            self.lobby_manager.db.cursor.execute(
                """
                UPDATE lobbies
                SET status = 'playing'
                WHERE lobby_id = ?
                """,
                (lobby_id,),
            )
            self.lobby_manager.db._connection.commit()

            return {
                "success": True,
                "message": "Игра началась",
                "game_state": game_state,
            }

        except Exception as e:
            logger.error(f"Ошибка начала игры: {e}")
            return {"success": False, "message": f"Ошибка начала игры: {str(e)}"}

    # ===== Обработка игровых действий =====

    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка вопроса игрока"""
        user_id = update.effective_user.id

        # Находим игру игрока
        game_state = self.storage.get_game_by_player(user_id)
        if not game_state:
            await update.message.reply_text("Вы не в активной игре!")
            return

        # Проверяем, что это ход текущего игрока
        if game_state.get_current_player() != user_id:
            await update.message.reply_text("Сейчас не ваш ход!")
            return

        question = update.message.text.strip()

        # Проверяем, не является ли вопрос финальной догадкой
        if question.lower().startswith("я ") and "!" == question[-1]:
            await self.process_final_guess(
                update,
                context,
                game_state,
                user_id,
                question,
            )
            return

        # Сохраняем вопрос в историю
        question_id = self.storage.save_question_history(
            game_state.lobby_id, user_id, question
        )

        # Начинаем голосование
        player_role = game_state.get_player_role(user_id)
        game_state.start_vote(question, user_id)

        # Рассылаем вопрос для голосования
        success = await self.notifier.send_vote_question(
            context, game_state, user_id, question, player_role
        )

        if success:
            await update.message.reply_text(
                "✅ Ваш вопрос отправлен другим игрокам!\n" "Ждем ответов..."
            )
            # обрабатывает голоса ботов
            await self.process_bot_votes(context, game_state, user_id, question, player_role)
        else:
            await update.message.reply_text(
                "❌ Не удалось отправить вопрос. Попробуйте еще раз."
            )

    async def process_vote(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            lobby_id: int,
            vote_type: str,
    ):
        """Обработка голоса"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        game_state = self.storage.get_game(lobby_id)

        if not game_state:
            await query.edit_message_text("Игра не найдена!")
            return

        # Проверяем, что идет голосование
        if game_state.status != GameStatus.VOTING:
            await query.edit_message_text("Сейчас нет активного голосования!")
            return

        # Добавляем голос
        success = game_state.add_vote(user_id, vote_type)
        if not success:
            await query.edit_message_text("Вы не можете голосовать на свой вопрос!")
            return

        await query.edit_message_text(
            f"✅ Ваш голос: {'Да' if vote_type == 'yes' else 'Нет'}"
        )

        # Проверяем, все ли проголосовали
        if game_state.is_voting_complete():
            await self.announce_results(context, game_state)

    async def announce_results(
            self, context: ContextTypes.DEFAULT_TYPE, game_state: GameState
    ):
        """Объявляет результаты голосования"""
        # Получаем результаты
        results = game_state.get_vote_results()
        yes_votes = results["yes"]
        no_votes = results["no"]

        # Получаем текущий вопрос
        if not game_state.current_vote:
            return
        question = game_state.current_vote.question
        question_owner_id = game_state.current_vote.question_owner_id

        # Обновляем результаты в истории
        # Находим ID последнего вопроса этого игрока
        history = self.storage.get_player_question_history(
            question_owner_id, game_state.lobby_id, limit=1
        )
        if history:
            self.storage.update_question_votes(history[0]["id"], yes_votes, no_votes)

        # Определяем результат
        majority_yes = yes_votes > no_votes

        # Обрабатываем результат
        game_state.end_vote()
        if majority_yes:
            # Игрок остается текущим
            player = game_state.get_current_player()
        else:
            # Передаем ход следующему игроку
            player = game_state.next_player()

        # Рассылаем результаты
        await self.notifier.send_vote_results(
            context, game_state, question, yes_votes, no_votes, majority_yes
        )
        if player and player < 0:
            self.bots[game_state.lobby_id][player].add_fact(question, majority_yes)
            await self.process_bot_turn(context, game_state, player)
        else:
            await self.notifier.send_turn_notification(context, game_state, player)

    async def process_final_guess(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            game_state: GameState,
            user_id: int,
            guess: str,
    ):
        """Обработка финальной догадки"""
        # Извлекаем предполагаемого персонажа
        guess_text = guess.strip()[2:][:-1].strip()
        actual_role = game_state.get_player_role(user_id)

        if guess_text.lower() == actual_role.lower():
            # Игрок угадал!
            await self.end_game(context, game_state, user_id, True)
        else:
            # Игрок не угадал
            game_state.end_vote()
            next_player = game_state.next_player()

            if next_player:
                # Уведомляем о неудачной попытке
                await self.notifier.broadcast_to_game(
                    context,
                    game_state,
                    f"❌ {await self.notifier.get_username(context, user_id)} не угадал(а)!\n"
                    f"Ход переходит следующему игроку.",
                )

                # Передаем ход следующему
                await self.notifier.send_turn_notification(
                    context, game_state, next_player
                )

    async def end_game(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            game_state: GameState,
            winner_id: int,
            guessed: bool,
    ):
        """Завершение игры"""
        if not guessed:
            return

        winner_role = game_state.get_player_role(winner_id)

        # Рассылаем уведомление о завершении
        await self.notifier.send_game_end_notification(
            context, game_state, winner_id, winner_role
        )
        # TODO: вынести в game_manager
        # Обновляем статус лобби в БД
        self.lobby_manager.db.cursor.execute(
            """
            UPDATE lobbies
            SET status = 'waiting'
            WHERE lobby_id = ?
            """,
            (game_state.lobby_id,),
        )

        # Очищаем роли
        self.storage.clear_player_roles(game_state.lobby_id)

        # Очищаем историю вопросов
        self.storage.cleanup_game_history(game_state.lobby_id)

        # Очищаем ботов для этого лобби
        if game_state.lobby_id in self.bots:
            del self.bots[game_state.lobby_id]

        # Удаляем состояние игры из памяти
        self.storage.remove_game(game_state.lobby_id)

        self.lobby_manager.db._connection.commit()

    # ===== Обработка хода бота =====

    async def process_bot_turn(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            game_state: GameState,
            bot_id: int
    ):
        """Обработка хода бота"""
        bot = self.bots.get(game_state.lobby_id, {}).get(bot_id)
        logger.info(f"AI bot {bot_id} turn")
        if not bot:
            logger.error(f"Бот {bot_id} не найден в лобби {game_state.lobby_id}")
            return

        try:
            # Бот задает вопрос
            response = bot.ask()

            if response.is_guess:
                # Бот делает предположение
                await self.process_bot_final_guess(
                    context, game_state, bot_id, response.question
                )
            else:
                # Бот задает обычный вопрос
                question = response.question

                # Сохраняем вопрос в историю
                question_id = self.storage.save_question_history(
                    game_state.lobby_id, bot_id, question
                )

                # Начинаем голосование
                player_role = game_state.get_player_role(bot_id)
                game_state.start_vote(question, bot_id)

                # Рассылаем вопрос для голосования
                success = await self.notifier.send_vote_question(
                    context, game_state, bot_id, question, player_role
                )

                if success:
                    # Автоматически голосуем за ботов (если они есть)
                    await self.process_bot_votes(context, game_state, bot_id, question, player_role)

        except Exception as e:
            logger.error(f"Ошибка обработки хода бота {bot_id}: {e}")

    async def process_bot_votes(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            game_state: GameState,
            asking_bot_id: int,
            question: str,
            target_role: str
    ):
        """Обработка голосования ботов"""
        # Получаем всех игроков
        for player_id in game_state.get_all_players():
            if player_id == asking_bot_id:
                continue  # Бот не голосует за свой вопрос

            if player_id > 0:  # Это человек
                continue

            bot = self.bots.get(game_state.lobby_id, {}).get(player_id)
            if bot:
                # Бот отвечает на вопрос
                answer = bot.ans_for_question(target_role, question)
                vote_type = "yes" if answer else "no"

                # Добавляем голос
                game_state.add_vote(player_id, vote_type)

        # Проверяем, все ли проголосовали
        if game_state.is_voting_complete():
            await self.announce_results(context, game_state)

    async def process_bot_final_guess(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            game_state: GameState,
            bot_id: int,
            guess: str
    ):
        """Обработка финальной догадки бота"""
        # Извлекаем предполагаемого персонажа
        guess_text = guess.strip().strip()
        actual_role = game_state.get_player_role(bot_id)

        if guess_text.lower() == actual_role.lower():
            # Бот угадал!
            await self.end_game(context, game_state, bot_id, True)
        else:
            # Бот не угадал
            game_state.end_vote()
            next_player = game_state.next_player()

            if next_player:
                # Уведомляем о неудачной попытке
                await self.notifier.broadcast_to_game(
                    context,
                    game_state,
                    f"🤖 AI Бот не угадал!\nХод переходит следующему игроку.",
                )

                # Проверяем, не бот ли следующий
                if next_player < 0:
                    await self.process_bot_turn(context, game_state, next_player)
                else:
                    await self.notifier.send_turn_notification(
                        context, game_state, next_player
                    )

    # ===== Управление игроками =====

    def prepare_player_exit(
            self, lobby_id: int, exiting_player_id: int
    ) -> Dict[str, Any]:
        """Подготовка к выходу игрока: сбор информации до удаления"""
        game_state = self.storage.get_game(lobby_id)
        if not game_state:
            return {"has_game": False, "needs_cleanup": False}

        result = {
            "has_game": True,
            "was_current_player": False,
            "had_voted": False,
            "was_last_vote": False,
            "remaining_players_count": game_state.get_player_count() - 1,
            "next_player": None,
        }

        # Проверяем, был ли игрок текущим
        current_player = game_state.get_current_player()
        if current_player == exiting_player_id:
            result["was_current_player"] = True
            # Определяем следующего игрока
            if game_state.get_player_count() > 1:
                # Получаем список игроков без выходящего
                player_ids = [
                    pid
                    for pid in game_state.get_all_players()
                    if pid != exiting_player_id
                ]
                if player_ids:
                    # Берем следующего по кругу
                    current_idx = 0  # выходящий был текущим
                    next_idx = current_idx % len(player_ids)
                    result["next_player"] = player_ids[next_idx]
        else:
            result["next_player"] = current_player

        # Проверяем, голосовал ли игрок
        if (
                game_state.status == GameStatus.VOTING
                and game_state.current_vote
                and exiting_player_id in game_state.current_vote.votes
        ):
            result["had_voted"] = True

        logger.info(f"Prepare_Player_exit result: {result}")
        return result

    async def process_player_exit(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            lobby_id: int,
            exiting_player_id: int,
            exit_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Обработка выхода игрока после сбора информации"""
        game_state = self.storage.get_game(lobby_id)
        if not game_state:
            return {"end_game": False}

        result: Dict[str, Any] = {"end_game": False}

        # Обрабатываем сценарии
        if exit_info.get("was_current_player"):
            next_player = exit_info.get("next_player")
            if next_player:
                result["next_player"] = next_player
        else:
            result["next_player"] = game_state.get_current_player()

        # Удаляем игрока из состояния
        game_state.remove_player(exiting_player_id, result["next_player"])

        if exit_info.get("had_voted"):
            del game_state.current_vote.votes[exiting_player_id]
            game_state.current_vote.total_players -= 1

        # Проверяем, остался ли 1 игрок
        if game_state.get_player_count() == 1:
            result["end_game"] = True
            winner_id = game_state.get_all_players()[0]
            result["winner_id"] = winner_id
            result["winner_role"] = game_state.get_player_role(winner_id)

        # Отправляем уведомления
        await self.notifier.send_player_exit_notification(
            context, game_state, exiting_player_id, exit_info, result
        )

        # Если все проголосовали, объявляем результаты
        if game_state.status == GameStatus.VOTING and game_state.is_voting_complete():
            await self.announce_results(context, game_state)

        logger.info(f"Process_Player_exit result: {result}")
        return result

    def create_bot_player(self, lobby_id: int, bot_index: int, role: str) -> BotPlayer:
        """Создание бота-игрока"""
        # Используем отрицательные ID для ботов
        bot = BotPlayer(bot_index, role)

        # Сохраняем бота в общем хранилище
        if lobby_id not in self.bots:
            self.bots[lobby_id] = {}
        self.bots[lobby_id][bot_index] = bot

        return bot

    # ===== Вспомогательные методы =====

    def get_current_player(self, lobby_id: int) -> Optional[int]:
        """Получает ID текущего игрока (для совместимости)"""
        game_state = self.storage.get_game(lobby_id)
        return game_state.get_current_player() if game_state else None

    async def get_question_history(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Показывает историю вопросов пользователя"""
        user_id = update.effective_user.id

        # Находим игру игрока
        game_state = self.storage.get_game_by_player(user_id)
        if not game_state:
            await update.message.reply_text(
                "Вы не находитесь в активной игре. "
                "История вопросов доступна только во время игры."
            )
            return

        # Получаем историю
        history = self.storage.get_player_question_history(user_id, game_state.lobby_id)

        if not history:
            await update.message.reply_text(
                "У вас пока нет заданных вопросов в этой игре."
            )
            return

        # Формируем сообщение
        history_text = "📝 История ваших вопросов в текущей игре:\n\n"

        for i, item in enumerate(history):
            if item["yes_votes"] is not None and item["no_votes"] is not None:
                vote_result = f"✅{item['yes_votes']} ❌{item['no_votes']}"
            else:
                vote_result = "⏳ Ожидает голосования"

            history_text += f"{len(history) - i}. {item['text']}\n"
            history_text += f"  {vote_result}\n\n"

        await update.message.reply_text(
            f"{history_text}\n" f"📊 Всего вопросов: {len(history)}"
        )
