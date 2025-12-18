import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database_manager import DatabaseManager
from lobby.lobby_manager import LobbyManager
from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db_manager = DatabaseManager()
lobby_manager = LobbyManager(db_manager)


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
        [
            InlineKeyboardButton("Начать игру", callback_data="start_game"),
            InlineKeyboardButton("Информация", callback_data="lobby_info"),
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

    # Создаем лобби (публичное по умолчанию)
    result = lobby_manager.create_lobby(
        host_id=user_id,
        max_players=4,  # TODO: Добавить выбор количества игроков через кнопки
        is_private=False,  # TODO: Добавить выбор приватности
    )

    if result["success"]:
        lobby_info = lobby_manager.get_lobby_info(result["lobby_id"])

        message_text = (
            f"✅ Лобби успешно создано!\n\n"
            f"🆔 ID лобби: {lobby_info['lobby_id']}\n"
            f"🔑 Код приглашения: {lobby_info['invite_code']}\n"
            f"👥 Игроков: {lobby_info['current_players']}/{lobby_info['max_players']}\n"
            f"👑 Хост: Вы\n\n"
            f"Поделитесь кодом приглашения с друзьями!"
        )

        # Кнопка для копирования кода
        keyboard = [
            [
                InlineKeyboardButton(
                    "📋 Копировать код",
                    callback_data=f"copy_code_{lobby_info['invite_code']}",
                ),
            ],
            [
                InlineKeyboardButton("↩️ Назад в меню", callback_data="back_to_menu"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup)
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
        # TODO: изменить id на имена
        # Формируем список игроков
        players_list = "\n".join(
            [f"👤 Игрок {i+1}" for i in range(len(lobby_info["players"]))]
        )

        message_text = (
            f"✅ Вы успешно присоединились к лобби!\n\n"
            f"🆔 ID лобби: {lobby_info['lobby_id']}\n"
            f"👥 Игроков: {lobby_info['current_players']}/{lobby_info['max_players']}\n"
            f"👑 Хост: {'Вы' if lobby_info['host_id'] == user_id else 'Другой игрок'}\n\n"
            f"Список игроков:\n{players_list}"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "📊 Информация о лобби",
                    callback_data=f"info_{lobby_info['lobby_id']}",
                )
            ],
            [InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")],
        ]

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

    # Ищем лобби, в котором находится пользователь
    db_manager.cursor.execute(
        """
        SELECT l.lobby_id, l.status, l.current_players, l.max_players,
               l.invite_code, l.host_id
        FROM lobbies l
        JOIN lobby_players lp ON l.lobby_id = lp.lobby_id
        WHERE lp.user_id = ? AND l.status = 'waiting'
        """,
        (user_id,),
    )

    lobby_data = db_manager.cursor.fetchone()

    if not lobby_data:
        await query.edit_message_text(
            "Вы не находитесь ни в одном активном лобби.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )
        return

    # Получаем полную информацию о лобби
    lobby_info = lobby_manager.get_lobby_info(lobby_data[0])
    # TODO: изменить id на имена
    # Формируем сообщение
    players_list = "\n".join(
        [
            f"{'👑 ' if player['user_id'] == lobby_info['host_id'] else '👤 '}"
            f"Игрок {i+1}"
            for i, player in enumerate(lobby_info["players"])
        ]
    )

    message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info['lobby_id']}\n"
        f"🔑 Код: {lobby_info['invite_code']}\n"
        f"📊 Статус: {lobby_info['status']}\n"
        f"👥 Игроков: {lobby_info['current_players']}/{lobby_info['max_players']}\n\n"
        f"Список игроков:\n{players_list}"
    )

    keyboard = []

    # Если пользователь хост, добавляем кнопку начала игры
    if lobby_info["host_id"] == user_id:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🎮 Начать игру", callback_data=f"start_{lobby_info['lobby_id']}"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "📋 Копировать код",
                callback_data=f"copy_code_{lobby_info['invite_code']}",
            ),
            InlineKeyboardButton(
                "🚪 Выйти", callback_data=f"leave_{lobby_info['lobby_id']}"
            ),
        ]
    )

    keyboard.append([InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup)


async def leave_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из лобби"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    # Находим лобби пользователя TODO: вынести в lobby_manager
    db_manager.cursor.execute(
        """
        SELECT l.lobby_id FROM lobbies l
        JOIN lobby_players lp ON l.lobby_id = lp.lobby_id
        WHERE lp.user_id = ? AND l.status = 'waiting'
        """,
        (user_id,),
    )

    lobby_data = db_manager.cursor.fetchone()

    if not lobby_data:
        await query.edit_message_text(
            "Вы не находитесь ни в одном активном лобби.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
            ),
        )
        return

    lobby_id = lobby_data[0]

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

    if result["success"]:
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
    """Начало игры"""
    query = update.callback_query
    await query.answer()

    # Извлекаем lobby_id из callback_data
    # TODO: баг, сюда всегда прилетает start_game
    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    # Пытаемся начать игру
    result = lobby_manager.start_game(lobby_id, user_id)

    if result["success"]:
        # TODO: Здесь будет логика запуска игры
        # 1. Генерация игрового поля
        # 2. Раздача карт/ролей
        # 3. Уведомление всех игроков
        # 4. Переход к игровому процессу

        await query.edit_message_text(
            "🎮 Игра началась!\n\n"
            "Игровой процесс будет реализован в будущих обновлениях.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
    else:
        logger.error(f"Error: {result.get('error', None)} Message: {result['message']}")
        await query.edit_message_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )


# TODO убрать, перенести в my_lobby_info
async def copy_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Копирование кода приглашения"""
    query = update.callback_query
    await query.answer()

    # Извлекаем код из callback_data
    invite_code = query.data.split("_")[-1]

    await query.edit_message_text(
        f"🔑 Код приглашения:\n`{invite_code}`\n\n"
        "Код скопирован! Поделитесь им с друзьями.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]]
        ),
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок"""
    query = update.callback_query
    data = query.data

    if data == "create_lobby":
        await create_lobby(update, context)
        return None
    elif data == "join_lobby":
        return await join_lobby(update, context)
    elif data == "my_lobby":
        await my_lobby_info(update, context)
        return None
    elif data == "leave_lobby":
        await leave_lobby(update, context)
        return None
    elif data.startswith("start_"):
        await start_game(update, context)
        return None
    elif data.startswith("leave_"):
        await leave_lobby(update, context)
        return None
    elif data.startswith("confirm_leave_"):
        await confirm_leave(update, context)
        return None
    elif data.startswith("copy_code_"):
        await copy_invite_code(update, context)
        return None
    elif data.startswith("info_"):
        # TODO: Показать детальную информацию о лобби
        await query.answer("Функция в разработке", show_alert=True)
        return None
    elif data == "back_to_menu":
        return await lobby_menu(update, context)
    elif data == "lobby_info":
        await my_lobby_info(update, context)
        return None
    else:
        await query.answer("Неизвестная команда")
        return None


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")]]
        ),
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    help_text = (
        "📚 Справка по командам:\n\n"
        "🏠 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/lobby - Управление лобби\n"
        "/my_lobby - Показать моё лобби\n"
        "/help - Эта справка\n\n"
        "🎮 Создание и присоединение:\n"
        "1. Используйте /lobby для открытия меню\n"
        "2. Создайте лобби или присоединитесь по коду\n"
        "3. Поделитесь кодом приглашения с друзьями\n\n"
        "⚠️ Примечания:\n"
        "- Для начала игры нужно минимум 2 игрока\n"
        "- Только хост может начать игру\n"
        "- Лобби автоматически удаляется, когда все выходят\n"
        "- Приватные лобби и пароли будут добавлены позже"
    )

    await update.message.reply_text(help_text)
