import logging
import os

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Bot
from telegram.error import TelegramError

from ServiceController import ServiceContainer
from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
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
    # Проверяем, не находится ли пользователь уже в лобби
    current_lobby_id = lobby_manager.get_user_lobby(user_id)
    if current_lobby_id:
        await query.edit_message_text(
            f"❌ Вы уже находитесь в лобби {current_lobby_id}!\n"
            "Пожалуйста, покиньте текущее лобби перед созданием нового.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад в меню", callback_data="back_to_menu")]]
            ),
        )
        return

    # Создаем лобби (публичное по умолчанию)
    result = lobby_manager.create_lobby(
        host_id=user_id,
        max_players=15,
        is_private=False,  # TODO: Добавить выбор приватности
    )

    if result["success"]:
        lobby_info = lobby_manager.get_lobby_info(result["lobby_id"])

        message_text = (
            f"✅ Лобби успешно создано!\n\n"
            f"🆔 ID лобби: {lobby_info.lobby_id}\n"
            f"🔑 Код приглашения: <code>{lobby_info.invite_code}</code>\n"
            f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n"
            f"👑 Хост: Вы\n\n"
            f"Поделитесь кодом приглашения с друзьями!"
        )

        keyboard = [
            [
                InlineKeyboardButton("🎮 Начать игру", callback_data=f"start_{lobby_info.lobby_id}")
            ],
            [
                InlineKeyboardButton("🚪 Выйти", callback_data=f"leave_{lobby_info.lobby_id}")
            ],
            [
                InlineKeyboardButton("↩️ Назад в меню", callback_data="back_to_menu"),
            ],
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="my_lobby"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            message_text, reply_markup=reply_markup, parse_mode="HTML"
        )
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
        await query.edit_message_text(
            f"❌ Вы уже находитесь в лобби {current_lobby_id}!\n"
            "Пожалуйста, покиньте текущее лобби перед присоединением к другому.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад в меню", callback_data="back_to_menu")]]
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
            f"✅ Вы успешно присоединились к лобби!\n\n"
            f"🆔 ID лобби: {lobby_info.lobby_id}\n"
            f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n"
            f"👑 Хост: {await get_username_from_id(lobby_info.host_id)}\n\n"
            f"Список игроков:\n{players_list}"
        )

        keyboard = []
        if lobby_info.host_id == user_id:
            keyboard.append([InlineKeyboardButton("🎮 Начать игру", callback_data=f"start_{lobby_info.lobby_id}")])
        keyboard.append([InlineKeyboardButton("🚪 Выйти", callback_data=f"leave_{lobby_info.lobby_id}")])
        keyboard.append([InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")])
        keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="my_lobby")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message_text, reply_markup=reply_markup)
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
    # Находим лобби пользователя - ВЫНЕСЕНО В LobbyManager
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
            f"{'👑 ' if player['user_id'] == lobby_info.host_id else '👤 '}"
            f"{await get_username_from_id(player['user_id'])}"
            for i, player in enumerate(lobby_info.players)
        ]
    )

    message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info.lobby_id}\n"
        f"🔑 Код: <code>{lobby_info.invite_code}</code>\n"
        f"📊 Статус: {lobby_info.status}\n"
        f"👥 Игроков: {lobby_info.current_players}/{lobby_info.max_players}\n\n"
        f"Список игроков:\n{players_list}"
    )
    if_edited_message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info.lobby_id}\n"
        f"🔑 Код: {lobby_info.invite_code}\n"
        f"📊 Статус: {lobby_info.status}\n"
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
    # TODO: надо удалять пользователя из игры,если игра активна
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
    """Начало игры с использованием новой архитектуры"""
    query = update.callback_query
    await query.answer()

    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Пытаемся начать игру через LobbyManager
    result = lobby_manager.start_game(lobby_id, user_id)

    if not result["success"]:
        logger.error(f"Error starting game: {result.get('error', None)} Message: {result['message']}")
        await query.edit_message_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return

    # Запускаем игровую сессию через GameLogic
    game_result = game_logic.start_game_session(lobby_id)

    if not game_result["success"]:
        await query.edit_message_text(
            f"❌ Ошибка начала игры: {game_result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return

    # Получаем состояние игры
    game_state = game_logic.storage.get_game(lobby_id)
    if not game_state:
        await query.edit_message_text(
            "❌ Не удалось получить состояние игры",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return

    # Рассылаем правила игрокам через GameNotifier
    for player_id in game_state.get_all_players():
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
        await query.edit_message_text(
            "❌ Не удалось определить первого игрока",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return

    # Отправляем уведомление первому игроку через GameNotifier
    await game_logic.notifier.send_turn_notification(
        context, game_state, first_player
    )

    # Уведомляем остальных игроков
    first_player_username = await game_logic.notifier.get_username(context, first_player)

    for player_id in game_state.get_all_players():
        if player_id != first_player:
            await game_logic.notifier.send_to_player(
                context,
                player_id,
                f"🎮 Первый ход у: {first_player_username}\n"
                "Ожидайте вопросов и будьте готовы голосовать!"
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
    elif data.startswith('start_'):
        await start_game(update, context)
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
    elif data.startswith("info_"):
        # TODO: Показать детальную информацию о лобби
        await query.answer("Функция в разработке", show_alert=True)
    elif data == "back_to_menu":
        return await lobby_menu(update, context)
    elif data == "lobby_info":
        await my_lobby_info(update, context)
    else:
        await query.answer("Неизвестная команда")

    return ConversationHandler.END
