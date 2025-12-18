import logging
import os

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram import Bot
from telegram.error import TelegramError

from database_manager import DatabaseManager
from game.game_logic import GameManager
from lobby.lobby_manager import LobbyManager
from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db_manager = DatabaseManager()
lobby_manager = LobbyManager(db_manager)
game_manager = GameManager(db_manager)

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
    # TODO: запретить создавать лобби, если игрок уже состоит в лобби
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
            f"🔑 Код приглашения: <code>{lobby_info['invite_code']}</code>\n"
            f"👥 Игроков: {lobby_info['current_players']}/{lobby_info['max_players']}\n"
            f"👑 Хост: Вы\n\n"
            f"Поделитесь кодом приглашения с друзьями!"
        )

        # Кнопка для копирования кода
        keyboard = [
            #[
            #    InlineKeyboardButton(
            #        "📋 Копировать код",
            #        callback_data=f"copy_code_{lobby_info['invite_code']}",
            #    ),
            #],
            [
                InlineKeyboardButton("↩️ Назад в меню", callback_data="back_to_menu"),
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
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
            [f"👤 {await get_username_from_id(lobby_info["players"][i]["user_id"])}" for i in range(len(lobby_info["players"]))]
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
    # TODO: Для хоста не обновляется
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
            f"{await get_username_from_id(player["user_id"])}"
            for i, player in enumerate(lobby_info["players"])
        ]
    )

    message_text = (
        f"🏠 Ваше лобби:\n\n"
        f"🆔 ID: {lobby_info['lobby_id']}\n"
        f"🔑 Код: <code>{lobby_info["invite_code"]}</code>\n"
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
            #InlineKeyboardButton(
            #    "📋 Копировать код",
            #    callback_data=f"copy_code_{lobby_info['invite_code']}",
            #),
            InlineKeyboardButton(
                "🚪 Выйти", callback_data=f"leave_{lobby_info['lobby_id']}"
            ),
        ]
    )

    keyboard.append([InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")


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

async def start_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lobby_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    await start_game(update, context, lobby_id, user_id)


async def start_game_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    lobby_id = lobby_manager.get_lobby_by_used_id(user_id)
    if not lobby_id:
        logger.error(f"Error: None Message: Пользователь не состоит в лобби")
        await query.edit_message_text(
            f"❌ Вы не состоите в лобби",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
            ),
        )
        return None

    await start_game(update, context, lobby_id, user_id)
    return None


async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE, lobby_id: int, user_id: int):
    """Начало игры"""
    query = update.callback_query

    # Пытаемся начать игру
    result = lobby_manager.start_game(lobby_id, user_id)

    if result["success"]:
        # Запускаем игровую сессию
        game_result = game_manager.start_game_session(lobby_id)

        if game_result["success"]:
            # Рассылаем роли игрокам
            await game_manager.send_roles_to_players(context, lobby_id)

            # Устанавливаем состояние игры для первого игрока
            first_player = game_manager.get_current_player(lobby_id)

            # Отправляем сообщение первому игроку
            await context.bot.send_message(
                chat_id=first_player,
                text="🎮 Ваш ход! Задайте вопрос о вашем персонаже.\n"
                     "Примеры вопросов:\n"
                     "• «Мой персонаж человек?»\n"
                     "• «Мой персонаж из фильма?»\n"
                     "• «Мой персонаж умеет летать?»\n\n"
                     "Для финальной догадки задайте вопрос в формате:\n"
                     "«Я [предполагаемый персонаж]?»"
            )

            # Уведомляем всех, что игра началась
            for player_id in game_manager.active_games[lobby_id]['players']:
                if player_id != first_player:
                    await context.bot.send_message(
                        chat_id=player_id,
                        text="🎮 Игра началась!\n"
                             f"Первый ход у: {await game_manager.get_username_from_id(context, first_player)}\n"
                             "Ожидайте вопросов и голосуйте!"
                    )

            await query.edit_message_text(
                "🎮 Игра началась!\n"
                "Роли распределены. Первый игрок задает вопрос.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("↩️ В меню", callback_data="back_to_menu")]]
                ),
            )
        else:
            await query.edit_message_text(
                f"❌ Ошибка начала игры: {game_result['message']}",
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
    elif data == "start_game":
        await start_game_button(update, context)
        return None
    elif data.startswith('start_'):
        await start_game_callback(update, context)
        return None
    elif data.startswith("leave_"):
        await leave_lobby(update, context)
        return None
    elif data.startswith("confirm_leave_"):
        await confirm_leave(update, context)
        return None
    elif data.startswith("vote_"):
        # Обработка голосования в игре
        parts = data.split("_")
        if len(parts) == 3:
            vote_type = parts[1]  # yes или no
            lobby_id = int(parts[2])
            await game_manager.process_vote(update, context, lobby_id, vote_type)
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
