import json
import random
from typing import List, Dict, Any, Optional
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database_manager


logger = logging.getLogger(__name__)


class GameManager(metaclass=database_manager.SingletonMeta):
    def __init__(self, db_manager=None):
        if not hasattr(self, "initialized"):
            self.db = db_manager
            self.active_games = dict()  # lobby_id -> game_state
            self.initialized = True

    def prepare_player_exit(self, lobby_id: int, exiting_player_id: int) -> Dict[str, Any]:
        """Подготовка к выходу игрока: сбор информации до удаления"""
        if lobby_id not in self.active_games:
            return {"has_game": False, "needs_cleanup": False}

        game_state = self.active_games[lobby_id]
        result = {
            "has_game": True,
            "was_current_player": False,
            "had_voted": False,
            "was_last_vote": False,
            "remaining_players_count": len(game_state['players']) - 1,
            "next_player": None
        }

        # Проверяем, был ли игрок текущим
        current_player = self.get_current_player(lobby_id)
        if current_player == exiting_player_id:
            result["was_current_player"] = True
            # Определяем следующего игрока ДО удаления
            if len(game_state['players']) - 1:
                # Находим индекс следующего игрока в оригинальном списке
                current_idx = game_state['players'].index(exiting_player_id)
                # Ищем следующего существующего игрока
                next_idx = (current_idx + 1) % len(game_state['players'])
                result["next_player"] = game_state['players'][next_idx]
        else:
            result["next_player"] = current_player

        # Проверяем, голосовал ли игрок
        if exiting_player_id in game_state.get('votes', {}):
            result["had_voted"] = True
        else:
            # Проверяем, был ли это последний голос
            total_voters = len(game_state['players']) - 1  # минус спрашивающий
            if len(game_state['votes']) == total_voters - 1: # минус человек, который выходит
                result["was_last_vote"] = True
        logger.info(f"Prepare_Player_exit result: {result}")
        return result

    async def process_player_exit(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            lobby_id: int,
            exiting_player_id: int,
            exit_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обработка выхода игрока после сбора информации"""
        if lobby_id not in self.active_games:
            return {"end_game": False}

        game_state = self.active_games[lobby_id]

        # Удаляем игрока из структур
        if exiting_player_id in game_state['players']:
            game_state['players'].remove(exiting_player_id)

        if exiting_player_id in game_state['roles']:
            del game_state['roles'][exiting_player_id]

        if exiting_player_id in game_state['votes']:
            del game_state['votes'][exiting_player_id]

        # Обрабатываем сценарии
        result = {"end_game": False}

        # 1. Если игрок был текущим
        if exit_info.get("was_current_player"):
            if exit_info.get("next_player"):
                # Находим нового текущего игрока
                if exit_info["next_player"] in game_state['players']:
                    next_player_idx = game_state['players'].index(exit_info["next_player"])
                    game_state['current_player_index'] = next_player_idx
                    result["next_player"] = exit_info["next_player"]

                    # Удаляем текущий вопрос
                    if 'current_question' in game_state:
                        del game_state['current_question']
        else:
            next_player_idx = game_state['players'].index(exit_info["next_player"])
            game_state['current_player_index'] = next_player_idx
            result["next_player"] = exit_info["next_player"]

        logger.info(f"Game_state after was_current_player: {game_state}")
        # 2. Проверяем, остался ли 1 игрок
        if len(game_state['players']) == 1:
            result["end_game"] = True
            result["winner_id"] = game_state['players'][0]
            result["winner_role"] = game_state['roles'].get(result["winner_id"])

        # 3. Отправляем уведомления
        await self.send_exit_notifications(
            context, lobby_id, exiting_player_id, result, exit_info
        )
        if len(game_state['players']) - 1 == len(game_state['votes']):
            await self.announce_results(context, lobby_id)
        logger.info(f"Process_Player_exit result: {result}")
        return result

    async def send_exit_notifications(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            lobby_id: int,
            exiting_player_id: int,
            game_result: Dict[str, Any],
            exit_info: Dict[str, Any]
    ):
        """Отправка уведомлений о выходе игрока"""
        if lobby_id not in self.active_games:
            return

        game_state = self.active_games[lobby_id]
        exiting_player_name = await self.get_username_from_id(context, exiting_player_id)

        notification_text = f"⚠️ {exiting_player_name} вышел из игры!\n\n"

        # Если игра завершилась
        if game_result.get("end_game"):
            winner_id = game_result.get("winner_id")
            if winner_id:
                winner_name = await self.get_username_from_id(context, winner_id)
                winner_role = game_result.get("winner_role", "Неизвестно")

                notification_text += (
                    f"🏆 Поздравляем! {winner_name} победил(а)!\n"
                    f"🎭 Ваша роль была: {winner_role}\n"
                    f"🎮 Игра завершена!"
                )

                # Раскрываем все роли
                notification_text += "\n\n📋 Все роли:\n"
                for player_id, role in game_state['roles'].items():
                    player_name = await self.get_username_from_id(context, player_id)
                    notification_text += f"{player_name}: {role}\n"
        else:
            # Игра продолжается
            notification_text += f"👥 Осталось игроков: {len(game_state['players'])}\n"

            # Если выходящий игрок был текущим
            if exit_info.get("was_current_player"):
                next_player = game_result.get("next_player")
                if next_player:
                    next_player_name = await self.get_username_from_id(context, next_player)
                    notification_text += f"\n🎮 Следующий ход у: {next_player_name}"

            # Если выходящий игрок голосовал
            elif exit_info.get("had_voted"):
                votes_count = len(game_state.get('votes', {}))
                total_voters = len(game_state['players']) - 1
                notification_text += f"\n🗳️ Проголосовало: {votes_count}/{total_voters}"

        # Отправляем уведомление всем оставшимся игрокам
        for player_id in game_state['players']:
            try:
                await context.bot.send_message(
                    chat_id=player_id,
                    text=notification_text
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление игроку {player_id}: {e}")

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

    def distribution_roles(self, num_players: int) -> List[str]:
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
            lobby_info = self.get_lobby_info(lobby_id)
            if not lobby_info:
                return {"success": False, "message": "Лобби не найдено"}

            num_players = lobby_info['current_players']
            player_ids = [player['user_id'] for player in lobby_info['players']]

            # Распределяем роли
            roles = self.distribution_roles(num_players)
            random.shuffle(roles)

            # Сохраняем роли игрокам в базу
            for i, player_id in enumerate(player_ids):
                # TODO: вынести запрос в менеджер
                self.db.cursor.execute(
                    """
                    UPDATE lobby_players
                    SET player_character = ?
                    WHERE lobby_id = ? AND user_id = ?
                    """,
                    (roles[i], lobby_id, player_id),
                )
            roles = dict(zip(player_ids, roles))
            logger.info(str(roles))
            # Создаем состояние игры
            game_state = {
                'lobby_id': lobby_id,
                'players': player_ids,
                'roles': roles,
                'current_player_index': 0,
                'question_count': 0,
                'votes': {},
                'game_started': True,
                'questions_history': [],
            }

            self.active_games[lobby_id] = game_state
            self.db._connection.commit()

            return {
                "success": True,
                "message": "Игра началась",
                "game_state": game_state,
            }

        except Exception as e:
            logger.error(f"Ошибка начала игры: {e}")
            return {"success": False, "message": f"Ошибка начала игры: {str(e)}"}

    def get_lobby_info(self, lobby_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о лобби"""
        self.db.cursor.execute(
            """
            SELECT lobby_id, status, current_players, host_id
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
            "current_players": row[2],
            "host_id": row[3],
        }

        # Список игроков
        self.db.cursor.execute(
            """
            SELECT user_id, player_character
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
                    "player_character": player_row[1],
                }
            )

        lobby["players"] = players
        return lobby

    async def send_roles_to_players(
        self, context: ContextTypes.DEFAULT_TYPE, lobby_id: int
    ):
        """Рассылает роли игрокам"""
        if lobby_id not in self.active_games:
            return

        game_state = self.active_games[lobby_id]

        for player_id in game_state['players']:
            # Получаем роли всех игроков, кроме себя
            other_players_roles = []
            for other_id, role in game_state['roles'].items():
                if other_id != player_id:
                    other_players_roles.append(
                        f"Игрок {await self.get_username_from_id(context, other_id)}: {role}"
                    )

            # Создаем сообщение для игрока
            message_text = (
                "🎮 Игра началась!\n\n"
                "📋 Роли других игроков:\n"
                + "\n".join(other_players_roles)
                + "\n\n❓ Ваша роль скрыта от вас!\n"
                "Задавайте вопросы, чтобы угадать, кто вы!"
            )

            # Отправляем сообщение
            try:
                await context.bot.send_message(chat_id=player_id, text=message_text)
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")

    async def get_username_from_id(
        self, context: ContextTypes.DEFAULT_TYPE, user_id: int
    ) -> str:
        """Получает username по ID"""
        try:
            # Попробуем получить из контекста бота
            chat = await context.bot.get_chat(user_id)
            return f"@{chat.username}" if chat.username else f"Игрок {user_id}"
        except:
            return f"Игрок {user_id}"

    def get_current_player(self, lobby_id: int) -> Optional[int]:
        """Получает ID текущего игрока"""
        if lobby_id in self.active_games:
            game_state = self.active_games[lobby_id]
            current_index = game_state['current_player_index']
            return game_state['players'][current_index]

        return None

    def next_player(self, lobby_id: int):
        """Передает ход следующему игроку"""
        if lobby_id in self.active_games:
            game_state = self.active_games[lobby_id]
            game_state['current_player_index'] = (
                game_state['current_player_index'] + 1
            ) % len(game_state['players'])
            game_state['votes'] = {}
            game_state['question_count'] = 0

    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка вопроса игрока"""
        user_id = update.effective_user.id

        # Находим лобби игрока
        for lobby_id, game_state in self.active_games.items():
            if user_id in game_state['players']:
                # Проверяем, что это ход текущего игрока
                current_player = self.get_current_player(lobby_id)
                if current_player != user_id:
                    await update.message.reply_text("Сейчас не ваш ход!")
                # TODO: если игрок уже задал вопрос и он находится на голосовании блокировать возможность задать новый вопрос
                question = update.message.text.strip()

                # Проверяем, не является ли вопрос финальной догадкой
                if question.lower().startswith("я ") and "!" == question[-1]:
                    # Это финальная догадка
                    await self.process_final_guess(
                        update, context, lobby_id, user_id, question
                    )
                    return

                # Обычный вопрос
                game_state['current_question'] = question
                game_state['question_count'] += 1

                # Рассылаем вопрос другим игрокам для голосования
                await self.send_vote_question(update, context, lobby_id, question)
                return

        await update.message.reply_text("Вы не в активной игре!")

    async def send_vote_question(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        lobby_id: int,
        question: str,
    ):
        """Рассылает вопрос для голосования"""
        game_state = self.active_games[lobby_id]
        asking_player = self.get_current_player(lobby_id)

        # Создаем клавиатуру для голосования
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"vote_yes_{lobby_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"vote_no_{lobby_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем вопрос всем игрокам, кроме спрашивающего
        for player_id in game_state['players']:
            if player_id != asking_player:
                try:
                    await context.bot.send_message(
                        chat_id=player_id,
                        text=f"❓ Вопрос от {await self.get_username_from_id(context, asking_player)}:\n\n"
                        f"«{question}»\n\n"
                        f"Ответьте на вопрос с точки зрения ВАШЕГО персонажа.",
                        reply_markup=reply_markup,
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить вопрос игроку {player_id}: {e}")

        # Уведомляем спрашивающего
        await update.message.reply_text(
            "✅ Ваш вопрос отправлен другим игрокам!\n" f"Ждем ответов..."
        )

    async def process_vote(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        lobby_id: int,
        vote: str,
    ):
        """Обработка голоса"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        game_state = self.active_games.get(lobby_id)

        if not game_state:
            await query.edit_message_text("Игра не найдена!")
            return

        # Проверяем, что это не спрашивающий игрок
        current_player = self.get_current_player(lobby_id)
        if user_id == current_player:
            await query.edit_message_text("Вы не можете голосовать на свой вопрос!")
            return

        # Записываем голос
        game_state['votes'][user_id] = vote

        await query.edit_message_text(
            f"✅ Ваш голос: {'Да' if vote == 'yes' else 'Нет'}"
        )

        # Проверяем, все ли проголосовали
        total_players = len(game_state['players']) - 1  # минус спрашивающий
        if len(game_state['votes']) == total_players:
            # Все проголосовали, подсчитываем результаты
            await self.announce_results(context, lobby_id)

    async def announce_results(
        self, context: ContextTypes.DEFAULT_TYPE, lobby_id: int
    ):
        """Объявляет результаты голосования"""
        game_state = self.active_games[lobby_id]
        if "current_question" not in game_state:
            return

        # Подсчитываем голоса
        yes_votes = sum(1 for vote in game_state['votes'].values() if vote == 'yes')
        no_votes = len(game_state['votes']) - yes_votes

        result_text = (
            f"📊 Результаты голосования:\n\n"
            f"Вопрос: «{game_state['current_question']}»\n"
            f"✅ Да: {yes_votes}\n"
            f"❌ Нет: {no_votes}\n"
        )

        if yes_votes > no_votes:
            result_text += "\n✅ Большинство ответило ДА!"
            result_text += "\nВы можете задать еще один вопрос."

            # Текущий игрок остается тем же, сбрасываем голоса
            game_state['votes'] = {}

            # Уведомляем текущего игрока, что он может задать еще вопрос
            current_player = self.get_current_player(lobby_id)
            await context.bot.send_message(
                chat_id=current_player,
                text=result_text + "\n\nЗадайте следующий вопрос:",
            )

            # Уведомляем других игроков
            for player_id in game_state['players']:
                if player_id != current_player:
                    await context.bot.send_message(
                        chat_id=player_id,
                        text=result_text + "\n\nОжидаем следующий вопрос...",
                    )
        else:
            result_text += "\n❌ Большинство ответило НЕТ!"
            result_text += "\nХод переходит следующему игроку."

            # Передаем ход следующему игроку
            self.next_player(lobby_id)
            next_player = self.get_current_player(lobby_id)

            # Рассылаем результаты всем
            for player_id in game_state['players']:
                await context.bot.send_message(
                    chat_id=player_id,
                    text=result_text
                    + f"\n\nСледующий ход: {await self.get_username_from_id(context, next_player)}",
                )

            # Просим следующего игрока задать вопрос
            await context.bot.send_message(
                chat_id=next_player, text="🎮 Ваш ход! Задайте вопрос:"
            )

    async def process_final_guess(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        lobby_id: int,
        user_id: int,
        guess: str,
    ):
        """Обработка финальной догадки"""
        game_state = self.active_games[lobby_id]

        # Извлекаем предполагаемого персонажа из вопроса
        guess_text = guess.strip()[2:][:-1]
        actual_role = game_state['roles'][user_id]

        if guess_text.lower() == actual_role.lower():
            # Игрок угадал!
            await self.end_game(update, context, lobby_id, user_id, True)
            return

        # Игрок не угадал
        result_text = (
            f"❌ {await self.get_username_from_id(context, user_id)}, вы не угадали!\n"
            f"Вы не {guess_text}.\n\n"
            f"Ход переходит следующему игроку."
        )

        # Передаем ход следующему игроку
        self.next_player(lobby_id)
        next_player = self.get_current_player(lobby_id)

        # Рассылаем результаты
        for player_id in game_state['players']:
            await context.bot.send_message(
                chat_id=player_id,
                text=result_text
                + f"\n\nСледующий ход: {await self.get_username_from_id(context, next_player)}",
            )

        # Просим следующего игрока задать вопрос
        await context.bot.send_message(
            chat_id=next_player, text="🎮 Ваш ход! Задайте вопрос:"
        )

    async def end_game(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        lobby_id: int,
        winner_id: int,
        guessed: bool,
    ):
        """Завершение игры"""
        game_state = self.active_games[lobby_id]

        if guessed:
            winner_name = await self.get_username_from_id(context, winner_id)
            winner_role = game_state['roles'][winner_id]

            # Раскрываем все роли
            roles_reveal = "📋 Все роли:\n"
            for player_id, role in game_state['roles'].items():
                player_name = await self.get_username_from_id(context, player_id)
                roles_reveal += f"{player_name}: {role}\n"

            end_message = (
                f"🎉 Поздравляем! {winner_name} угадал(а) своего персонажа!\n\n"
                f"{winner_name} был(а): {winner_role}\n\n"
                f"{roles_reveal}\n"
                f"Игра завершена!"
            )
        else:
            end_message = "Игра завершена!"

        # Рассылаем сообщение о завершении
        for player_id in game_state['players']:
            await context.bot.send_message(chat_id=player_id, text=end_message)

        # Возвращаем лобби в состояние ожидания
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

        # Удаляем состояние игры
        if lobby_id in self.active_games:
            del self.active_games[lobby_id]

        self.db._connection.commit()
