import logging
import os

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Bot
from telegram.error import TelegramError

from ServiceController import ServiceContainer
from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY, WAITING_FOR_THEME
from handlers.base_command import cancel_leave

logger = logging.getLogger(__name__)

# Инициализируем контейнер сервисов
services = ServiceContainer()

# Получаем сервисы из контейнера
lobby_manager = services.lobby_manager
game_logic = services.game_logic

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=os.getenv("BOT_TOKEN"))


async def get_username_from_id(user_id: int):
    if user_id < 0:
        return f"AI Bot {-user_id}"

    try:
        # Получаем информацию о чате по ID
        chat = await bot.get_chat(user_id)
        # Проверяем, есть ли у пользователя username
        return f"@{chat.username}"
    except TelegramError as e:
        return f"Ошибка при получении данных: {e}"


async def lobby_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления лобби"""
    keyboard = [
        [
            InlineKeyboardButton("Создать лобби", callback_data="create_lobby"),
            InlineKeyboardButton("Присоединиться", callback_data="join_lobby"),
        ],
        [
            InlineKeyboardButton("Моё лобби", callback_data="my_lobby"),
            InlineKeyboardButton("Выйти из лобби", callback_data="leave_lobby"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(
            "🏠 Управление лобби:", reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "🏠 Управление лобби:", reply_markup=reply_markup
        )

    return SELECTING_ACTION


async def create_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание нового лобби"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    current_lobby_id = lobby_manager.get_user_lobby(user_id)

    if current_lobby_id:
        # Получаем информацию о текущем лобби
        current_lobby_info = lobby_manager.get_lobby_info(current_lobby_id)

        if current_lobby_info:
            if current_lobby_info.status == 'playing':
                # Случай 1: Игра активна
                await query.edit_message_text(
                    f"❌ Вы находитесь в лобби с активной игрой!\n"
                    "Пожалуйста, дождитесь окончания игры или покиньте лобби.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "↩️ Назад в меню", callback_data="back_to_menu"
                                )
                            ]
                        ]
                    ),
                )
                return
            else:
                # Случай 2: Лобби есть, но игра не активна
                await query.edit_message_text(
                    f"❌ Вы уже находитесь в лобби {current_lobby_id}!\n"
                    "Пожалуйста, покиньте текущее лобби перед созданием нового.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "↩️ Назад в меню", callback_data="back_to_menu"
                                )
                            ]
                        ]
                    ),
                )
                return
        else:
            # Случай 3: Лобби ID есть, но информация не найдена (ошибка БД)
            await query.edit_message_text(
                "❌ Произошла ошибка при проверке вашего лобби.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "↩️ Назад в меню", callback_data="back_to_menu"
                            )
                        ]
                    ]
                ),
            )
            return

    # Если мы здесь, значит пользователь не в лобби - создаем новое

    # Создаем лобби (публичное по умолчанию)
    result = lobby_manager.create_lobby(
        host_id=user_id,
        max_players=15,
        is_private=False,  # TODO: Добавить выбор приватности
    )

    if result["success"]:
        await my_lobby_info(update, context)
    else:
        logger.error(f"Error: {result.get('error', None)} Message: {result['message']}")
        await query.edit_message_text(
            f"❌ Ошибка при создании лобби:\n{result['message']}\n\n"
            "Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )


async def join_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединение к лобби"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    # Проверяем, не находится ли пользователь уже в лобби
    current_lobby_id = lobby_manager.get_user_lobby(user_id)
    if current_lobby_id:
        # Теперь проверяем статус лобби отдельно
        # Сначала получаем полную информацию о лобби
        lobby_info = lobby_manager.get_lobby_info(current_lobby_id)

        if lobby_info:
            if lobby_info.status == 'playing':
                await query.edit_message_text(
                    f"❌ Вы находитесь в лобби с активной игрой!\n"
                    "Пожалуйста, дождитесь окончания игры или покиньте лобби.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "↩️ Назад в меню", callback_data="back_to_menu"
                                )
                            ]
                        ]
                    ),
                )
                return
            else:
                await query.edit_message_text(
                    f"❌ Вы уже находитесь в лобби (ID: {current_lobby_id})!\n"
                    "Пожалуйста, покиньте текущее лобби перед присоединением к другому.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "↩️ Назад в меню", callback_data="back_to_menu"
                                )
                            ]
                        ]
                    ),
                )
                return
        else:
            # Если информация о лобби не найдена, но ID есть - странная ситуация
            await query.edit_message_text(
                "❌ Произошла ошибка при проверке вашего лобби.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "↩️ Назад в меню", callback_data="back_to_menu"
                            )
                        ]
                    ]
                ),
            )
            return

    await query.edit_message_text(
        "Введите код приглашения лобби:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_menu")]]
        ),
    )

    return JOINING_LOBBY


async def process_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенного кода приглашения"""
    invite_code = update.message.text.strip().upper()
    user_id = update.effective_user.id

    # Сначала проверяем, активна ли игра в лобби
    lobby = lobby_manager.get_lobby_by_code(invite_code)
    if lobby and lobby.status == 'playing':
        await update.message.reply_text(
            "❌ В этом лобби уже идет игра!\n"
            "Присоединиться можно только к лобби в ожидании игроков.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )
        return JOINING_LOBBY

    # Пытаемся присоединиться к лобби
    result = lobby_manager.join_lobby(user_id, invite_code)

    if result["success"]:
        lobby_info = lobby_manager.get_lobby_info(result["lobby_id"])
        # Формируем список игроков
        players_list = "\n".join(
            [
                f"👤 {await get_username_from_id(lobby_info.players[i]['user_id'])}"
                for i in range(len(lobby_info.players))
            ]
        )

        message_text = (
            "Вы успешно присоединились к лобби!\n"
            f"🏠 Ваше лобби:\n\n"
            f"🆔 ID: {lobby_info.lobby_id}\n"
            f"🔑 Код: <code>{lobby_info.invite_code}</code>\n"
            f"📊 Статус: {lobby_info.status}\n"
            f"🤖 Боты: {'✅ Включены' if lobby_info.has_bots else '❌ Выключены'}\n"
            f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n\n"
            f"Список игроков:\n{players_list}"
        )

        keyboard = []
        keyboard.append([InlineKeyboardButton("🚪 Выйти", callback_data=f"leave_{lobby_info.lobby_id}")])
        keyboard.append(
            [InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]
        )
        keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="my_lobby")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        logger.error(f"Error: {result.get('error', None)} Message: {result['message']}")
        await update.message.reply_text(
            f"❌ {result['message']}\n\n" "Попробуйте ввести код еще раз:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_menu")]]
            ),
        )
        return JOINING_LOBBY

    return ConversationHandler.END


async def my_lobby_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о текущем лобби пользователя"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    # Находим лобби пользователя
    lobby_id = lobby_manager.get_user_lobby(user_id)

    if not lobby_id:
        await query.edit_message_text(
            "Вы не находитесь ни в одном активном лобби.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )
        return

    # Получаем полную информацию о лобби
    lobby_info = lobby_manager.get_lobby_info(lobby_id)
    # Формируем сообщение
    players_list = "\n".join(
        [
            f"{'👑 ' if player['user_id'] == lobby_info.host_id else '👤 ' if player['user_id'] > 0 else '🤖 '}"
            f"{await get_username_from_id(player['user_id'])}"
            for i, player in enumerate(lobby_info.players)
        ]
    )

    message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info.lobby_id}\n"
        f"🔑 Код: <code>{lobby_info.invite_code}</code>\n"
        f"📊 Статус: {lobby_info.status}\n"
        f"🤖 Боты: {'✅ Включены' if lobby_info.has_bots else '❌ Выключены'}\n"
        f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n\n"
        f"Список игроков:\n{players_list}"
    )
    if_edited_message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info.lobby_id}\n"
        f"🔑 Код: {lobby_info.invite_code}\n"
        f"📊 Статус: {lobby_info.status}\n"
        f"🤖 Боты: {'✅ Включены' if lobby_info.has_bots else '❌ Выключены'}\n"
        f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n\n"
        f"Список игроков:\n{players_list}"
    )

    keyboard = []

    # Если пользователь хост, добавляем кнопку начала игры
    if lobby_info.host_id == user_id:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🎮 Начать игру", callback_data=f"start_{lobby_info.lobby_id}"
                )
            ]
        )

    # Если пользователь хост и игра не запущена, добавляем кнопку управления ботами
    if lobby_info.host_id == user_id and lobby_info.status != 'playing':
        keyboard.append([
            InlineKeyboardButton(
                f"{'❌ Выключить ботов' if lobby_info.has_bots else '🤖 Включить ботов'}",
                callback_data=f"toggle_bots_{lobby_info.lobby_id}"
            )
        ])

    keyboard.append(
        [
            InlineKeyboardButton(
                "🚪 Выйти", callback_data=f"leave_{lobby_info.lobby_id}"
            ),
        ]
    )

    keyboard.append([InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")])
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="my_lobby")])

    current_message_text = query.message.text
    if current_message_text == if_edited_message_text:
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        message_text, reply_markup=reply_markup, parse_mode="HTML"
    )


async def leave_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из лобби"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    lobby_id = lobby_manager.get_user_lobby(user_id)

    if not lobby_id:
        await query.edit_message_text(
            "Вы не находитесь ни в одном активном лобби.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )
        return

    # Подтверждение выхода
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Да, выйти", callback_data=f"confirm_leave_{lobby_id}"
            ),
            InlineKeyboardButton("❌ Нет, остаться", callback_data="back_to_menu"),
        ]
    ]

    await query.edit_message_text(
        "Вы уверены, что хотите выйти из лобби?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def confirm_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение выхода из лобби"""
    query = update.callback_query
    await query.answer()

    # Извлекаем lobby_id из callback_data
    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Выходим из лобби
    result = lobby_manager.leave_lobby(user_id, lobby_id)
    logger.info(f"Leave_lobby_return result: {result}")
    if result["success"]:
        # Завершаем обработку выхода
        if not result.get("game_processing_result", None):
            await query.edit_message_text(
                "✅ Вы вышли из лобби.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
                ),
            )
            return

        if result.get("game_processing_result", {}).get("needs_processing"):
            await lobby_manager.complete_player_exit(context, result)

        # Проверяем, не завершилась ли игра
        if result.get("remaining_players", 0) <= 1:
            await query.edit_message_text(
                "✅ Вы вышли из лобби. Игра завершена.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
                ),
            )
        else:
            await query.edit_message_text(
                "✅ Вы вышли из лобби.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
                ),
            )
    else:
        logger.error(f"Error: {result.get('error', None)} Message: {result['message']}")
        await query.edit_message_text(
            f"❌ Ошибка: {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало игры - первый шаг: подготовка"""
    query = update.callback_query
    await query.answer()

    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Проверяем статус лобби
    lobby_info = lobby_manager.get_lobby_info(lobby_id)
    if lobby_info and lobby_info.status == 'playing':
        await query.edit_message_text(
            "❌ Игра уже идет в этом лобби!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    if lobby_info and lobby_info.status == 'game_starting':
        await query.edit_message_text(
            "⏳ Игра уже готовится к запуску!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return WAITING_FOR_THEME

    # Подготавливаем игру (меняем статус на game_starting)
    result = lobby_manager.start_game_prepare(lobby_id, user_id)

    if not result["success"]:
        logger.error(
            f"Error starting game: {result.get('error', None)} Message: {result['message']}"
        )
        await query.edit_message_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Отправляем сообщение с просьбой задать тему
    message_text = (
        "🎮 Подготовка к игре...\n\n"
        "🎨 Хотите задать тему для персонажей?\n\n"
        "Примеры тем:\n"
        "• Герои Марвел\n"
        "• Исторические личности\n"
        "• Персонажи аниме\n"
        "• Супергерои комиксов\n"
        "• Известные ученые\n"
        "• Литературные персонажи\n"
        "• Персонажи видеоигр\n\n"
        "📝 Напишите тему для ролей ИЛИ отправьте 'скип' для случайной генерации."
    )

    # Сохраняем lobby_id в контексте
    context.user_data['starting_game_lobby'] = lobby_id

    # Отправляем сообщение хосту
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_start_{lobby_id}")]]
        ),
    )

    return WAITING_FOR_THEME


async def process_game_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка темы для игры от хоста"""
    user_id = update.effective_user.id
    lobby_id = context.user_data.get('starting_game_lobby')

    if not lobby_id:
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте начать игру заново.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Проверяем, что пользователь все еще хост
    lobby_info = lobby_manager.get_lobby_info(lobby_id)
    if not lobby_info or lobby_info.host_id != user_id:
        await update.message.reply_text(
            "❌ Только хост может настраивать игру!",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    theme = update.message.text.strip()

    # Подтверждаем начало игры с темой
    result = lobby_manager.confirm_start_game(lobby_id)

    if not result["success"]:
        await update.message.reply_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Очищаем временные данные
    if 'starting_game_lobby' in context.user_data:
        del context.user_data['starting_game_lobby']

    # Получаем тему (если была указана и не скип)
    final_theme = None
    if theme and theme.lower() not in ['скип', 'skip']:
        final_theme = theme

    # Запускаем игровую сессию через GameLogic
    game_result = game_logic.start_game_session(lobby_id, final_theme)

    if not game_result["success"]:
        await update.message.reply_text(
            f"❌ Ошибка начала игры: {game_result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Получаем состояние игры
    game_state = game_logic.storage.get_game(lobby_id)
    if not game_state:
        await update.message.reply_text(
            "❌ Не удалось получить состояние игры",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Уведомляем хоста об успешном запуске
    if final_theme:
        await update.message.reply_text(
            f"✅ Игра начата с темой: {final_theme}!\n\n"
            f"Сгенерировано {len(game_state.get_all_players())} персонажей.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
    else:
        await update.message.reply_text(
            f"✅ Игра начата!\n\n"
            f"Сгенерировано {len(game_state.get_all_players())} случайных персонажей.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )

    # Рассылаем правила игрокам через GameNotifier
    for player_id in game_state.get_all_players():
        if player_id < 0:
            continue
        # Получаем роли всех игроков, кроме текущего
        other_players_roles = {}
        for other_id in game_state.get_all_players():
            if other_id != player_id:
                role = game_state.get_player_role(other_id)
                if role:
                    other_players_roles[other_id] = role

        # Отправляем правила через GameNotifier
        await game_logic.notifier.send_game_rules(
            context, game_state, player_id, other_players_roles
        )

    # Получаем первого игрока
    first_player = game_state.get_current_player()
    if not first_player:
        await update.message.reply_text(
            "❌ Не удалось определить первого игрока",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return ConversationHandler.END

    # Отправляем уведомление первому игроку через GameNotifier
    await game_logic.notifier.send_turn_notification(context, game_state, first_player)

    # Уведомляем остальных игроков
    first_player_username = await game_logic.notifier.get_username(
        context, first_player
    )

    for player_id in game_state.get_all_players():
        if player_id != first_player and player_id > 0:
            await game_logic.notifier.send_to_player(
                context,
                player_id,
                f"🎮 Игра началась!\n"
                f"Первый ход у: {first_player_username}\n"
                "Ожидайте вопросов и будьте готовы голосовать!",
            )

    return ConversationHandler.END


async def cancel_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена начала игры"""
    query = update.callback_query
    await query.answer()

    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Возвращаем статус лобби обратно на waiting
    try:
        lobby_manager.db.cursor.execute(
            """
            UPDATE lobbies
            SET status = 'waiting'
            WHERE lobby_id = ?
            """,
            (lobby_id,),
        )
        lobby_manager.db._connection.commit()

        # Очищаем временные данные
        if 'starting_game_lobby' in context.user_data:
            del context.user_data['starting_game_lobby']

        await query.edit_message_text(
            "❌ Начало игры отменено.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
    except Exception as e:
        await query.edit_message_text(
            f"❌ Ошибка при отмене: {str(e)}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )

    return ConversationHandler.END


async def toggle_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение/выключение ботов в лобби"""
    query = update.callback_query
    await query.answer()

    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Пытаемся переключить состояние ботов
    result = lobby_manager.toggle_bots(lobby_id, user_id)

    if result["success"]:
        if result["has_bots"]:
            lobby_manager.add_bot_to_lobby(lobby_id)
        else:
            lobby_manager.remove_bot_to_lobby(lobby_id)

        # Обновляем информацию о лобби
        await my_lobby_info(update, context)
    else:
        await query.edit_message_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="my_lobby")]]
            ),
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок"""
    query = update.callback_query
    data = query.data
    logger.info(data)

    if data == "create_lobby":
        await create_lobby(update, context)
    elif data == "join_lobby":
        return await join_lobby(update, context)
    elif data == "my_lobby":
        await my_lobby_info(update, context)
    elif data == "leave_lobby":
        await leave_lobby(update, context)
    if data.startswith('cancel_start_'):
        return await cancel_game_start(update, context)
    elif data.startswith("toggle_bots_"):
        await toggle_bots(update, context)
    elif data.startswith('start_'):
        return await start_game(update, context)
    elif data.startswith("leave_"):
        await leave_lobby(update, context)
    elif data.startswith("confirm_leave_"):
        await confirm_leave(update, context)
    elif data.startswith("vote_"):
        # Обработка голосования в игре
        parts = data.split("_")
        if len(parts) == 3:
            vote_type = parts[1]  # yes или no
            lobby_id = int(parts[2])
            await game_logic.process_vote(update, context, lobby_id, vote_type)
    elif data == "back_to_menu":
        return await lobby_menu(update, context)
    elif data == "cancel_leave":
        await cancel_leave(update, context)
    elif data == "lobby_info":
        await my_lobby_info(update, context)
    else:
        await query.answer("Неизвестная команда")

    return ConversationHandler.END