from typing import Dict, Any, List, Optional
import logging
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class GameNotifier:
    """Сервис отправки уведомлений и сообщений"""

    def __init__(self):
        self._username_cache: Dict[int, str] = {}

    # ===== Утилиты =====

    async def get_username(
        self, context: ContextTypes.DEFAULT_TYPE, user_id: int
    ) -> str:
        """Получение username с кэшированием"""
        if user_id in self._username_cache:
            return self._username_cache[user_id]

        if user_id < 0:
            return f"AI Bot {-user_id}"

        try:
            chat = await context.bot.get_chat(user_id)
            username = f"@{chat.username}" if chat.username else f"Игрок {user_id}"
            self._username_cache[user_id] = username
            return username
        except Exception as e:
            logger.error(f"Ошибка получения username: {e}")
            return f"Игрок {user_id}"

    # ===== Основные уведомления =====

    async def send_to_player(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> bool:
        """Отправка сообщения конкретному игроку"""

        if user_id < 0:
            return True

        try:
            await context.bot.send_message(
                chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение игроку {user_id}: {e}")
            return False

    async def broadcast_to_game(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        text: str,
        exclude_users: List[int] = None,
    ) -> Dict[int, bool]:
        """Рассылка сообщения всем игрокам игры"""
        results = {}
        exclude_users = exclude_users or []

        for user_id in game_state.get_all_players():
            if user_id in exclude_users or user_id < 0:
                continue

            success = await self.send_to_player(context, user_id, text)
            results[user_id] = success

        return results

    # ===== Игровые уведомления =====
    async def send_game_rules(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        user_id: int,
        other_players_roles: Dict[int, str],
    ) -> bool:
        """Отправка правил игры"""
        if user_id < 0:
            return True

        try:
            # Формируем список ролей других игроков
            roles_text = "📋 Роли других игроков:\n"
            for other_id, role in other_players_roles.items():
                if other_id != user_id:
                    username = await self.get_username(context, other_id)
                    roles_text += f"👤 {username}: {role}\n"

            rules_text = (
                "🎮 Игра началась!\n\n"
                f"{roles_text}\n"
                "❓ Ваша роль скрыта от вас!\n\n"
                "📝 Правила игры:\n"
                "1. Ваша цель - угадать, кто вы, задавая вопросы другим игрокам\n"
                "2. Вы можете задавать вопросы о своем персонаже\n"
                "3. Другие игроки голосуют, согласны ли они с вопросом\n"
                "4. Если большинство ответит «Да» - вы можете задать еще вопрос\n"
                "5. Если большинство ответит «Нет» - ход переходит следующему игроку\n"
                "6. Для финальной догадки используйте формат: «Я [персонаж]!» (с восклицательным знаком)\n\n"
                "Удачи!"
            )

            return await self.send_to_player(context, user_id, rules_text)
        except Exception as e:
            logger.error(f"Ошибка отправки правил: {e}")
            return False

    async def send_vote_question(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        asking_player_id: int,
        question: str,
        asking_player_role: str,
    ) -> bool:
        """Рассылка вопроса для голосования"""
        try:
            asking_username = await self.get_username(context, asking_player_id)

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Да", callback_data=f"vote_yes_{game_state.lobby_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Нет", callback_data=f"vote_no_{game_state.lobby_id}"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message_text = (
                f"❓ Вопрос от {asking_username}:\n\n"
                f"«{question}»\n\n"
                f"Ответьте на вопрос о персонаже {asking_player_role}."
            )

            # Отправляем всем, кроме спрашивающего
            success_count = 0
            for player_id in game_state.get_all_players():
                if player_id != asking_player_id and player_id > 0:
                    success = await self.send_to_player(
                        context, player_id, message_text, reply_markup
                    )
                    if success:
                        success_count += 1

                if player_id < 0:
                    success_count += 1

            return success_count > 0
        except Exception as e:
            logger.error(f"Ошибка отправки вопроса: {e}")
            return False

    async def send_vote_results(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        question: str,
        yes_votes: int,
        no_votes: int,
        majority_yes: bool,
    ) -> Dict[int, bool]:
        """Рассылка результатов голосования"""
        result_text = (
            f"📊 Результаты голосования:\n\n"
            f"Вопрос: «{question}»\n"
            f"✅ Да: {yes_votes}\n"
            f"❌ Нет: {no_votes}\n"
        )

        if majority_yes:
            result_text += "\n✅ Большинство ответило ДА!\n"
            if game_state.get_current_player():
                current_player_username = await self.get_username(
                    context, game_state.get_current_player()
                )
                result_text += (
                    f"\n🎮 {current_player_username} может задать еще один вопрос."
                )
            else:
                result_text += f"\n🎮 Вы можете задать еще один вопрос."
        else:
            result_text += "\n❌ Большинство ответило НЕТ!\n"
            result_text += "Ход переходит следующему игроку."

            next_player = game_state.get_current_player()
            if next_player:
                next_player_username = await self.get_username(context, next_player)
                result_text += f"\n\nСледующий ход: {next_player_username}"

        return await self.broadcast_to_game(context, game_state, result_text)

    async def send_player_exit_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        exiting_user_id: int,
        exit_info: Dict[str, Any],
        game_result: Dict[str, Any] = None,
    ) -> Dict[int, bool]:
        """Уведомление о выходе игрока"""
        exiting_username = await self.get_username(context, exiting_user_id)

        notification_text = f"⚠️ {exiting_username} вышел из игры!\n\n"

        if game_result and game_result.get("end_game"):
            # Игра завершилась
            winner_id = game_result.get("winner_id")
            if winner_id:
                winner_username = await self.get_username(context, winner_id)
                winner_role = game_result.get("winner_role", "Неизвестно")

                notification_text += (
                    f"🏆 Поздравляем! {winner_username} победил(а)!\n"
                    f"🎭 Роль: {winner_role}\n"
                    f"🎮 Игра завершена!"
                )

                # Раскрываем все роли
                notification_text += "\n\n📋 Все роли:\n"
                for player_id in game_state.get_all_players():
                    role = game_state.get_player_role(player_id)
                    if role:
                        username = await self.get_username(context, player_id)
                        notification_text += f"{username}: {role}\n"
        else:
            # Игра продолжается
            notification_text += (
                f"👥 Осталось игроков: {game_state.get_remaining_players_count()}\n"
            )

            if exit_info.get("was_current_player"):
                next_player = game_result.get("next_player") if game_result else None
                if next_player:
                    next_player_username = await self.get_username(context, next_player)
                    notification_text += f"\n🎮 Следующий ход у: {next_player_username}"

        return await self.broadcast_to_game(
            context, game_state, notification_text, [exiting_user_id]
        )

    async def send_game_end_notification(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        game_state,
        winner_id: int,
        winner_role: str,
    ) -> Dict[int, bool]:
        """Уведомление о завершении игры"""
        winner_username = await self.get_username(context, winner_id)

        # Раскрываем все роли
        roles_text = "📋 Все роли:\n"
        for player_id in game_state.get_all_players():
            role = game_state.get_player_role(player_id)
            if role:
                username = await self.get_username(context, player_id)
                roles_text += f"{username}: {role}\n"

        end_message = (
            f"🎉 Поздравляем! {winner_username} угадал(а) своего персонажа!\n\n"
            f"{winner_username} был(а): {winner_role}\n\n"
            f"{roles_text}\n"
            f"Игра завершена!"
        )

        return await self.broadcast_to_game(context, game_state, end_message)

    async def send_turn_notification(
        self, context: ContextTypes.DEFAULT_TYPE, game_state, player_id: int
    ) -> bool:
        """Уведомление о том, что ход перешел к игроку"""
        if player_id < 0:
            return True

        try:
            username = await self.get_username(context, player_id)

            message_text = (
                f"🎮 Ваш ход, {username}!\n\n"
                "Задайте вопрос о вашем персонаже.\n"
                "Примеры вопросов:\n"
                "• «Мой персонаж человек?»\n"
                "• «Мой персонаж из фильма?»\n"
                "• «Мой персонаж умеет летать?»\n\n"
                "Для финальной догадки задайте вопрос в формате:\n"
                "«Я [предполагаемый персонаж]!» (обязателен восклицательный знак в конце!)"
            )

            return await self.send_to_player(context, player_id, message_text)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о ходе: {e}")
            return False

    # ===== Очистка кэша =====

    def clear_username_cache(self, user_id: int = None):
        """Очистка кэша username"""
        if user_id:
            self._username_cache.pop(user_id, None)
        else:
            self._username_cache.clear()
