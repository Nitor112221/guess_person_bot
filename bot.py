import logging
import os
from typing import Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

from ServiceController import ServiceContainer
from config import SELECTING_ACTION, JOINING_LOBBY, WAITING_FOR_THEME
from handlers.base_command import cancel, start, help_command, leave
from lobby.commands import button_callback, process_invite_code, lobby_menu, process_game_theme

load_dotenv()
# Берем из переменных окружения (безопасно!)
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO,
    filename="logs.log"
)
logging.getLogger('httpx').setLevel(logging.WARNING)  # убираем лишние логи
logger = logging.getLogger(__name__)


def main() -> None:
    """Запуск бота."""
    # Подключаемся к базе данных

    if not os.path.exists("data/"):
        os.mkdir("data/")

    # Инициализация
    services = ServiceContainer()
    game_logic = services.game_logic

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("leave", leave))
    application.add_handler(CommandHandler("lobby", lobby_menu))

    application.add_handler(CommandHandler("history", game_logic.get_question_history))

    # Callback для игрового цикла
    application.add_handler(
        CallbackQueryHandler(
            lambda update, context: game_logic.process_vote(
                update,
                context,
                int(update.callback_query.data.split('_')[2]),
                update.callback_query.data.split('_')[1],
            ),
            pattern="^vote_(yes|no)_",
        )
    )
    # ConversationHandler для управления лобби
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback)],
        states={
            SELECTING_ACTION: [CallbackQueryHandler(button_callback)],
            JOINING_LOBBY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_invite_code),
                CallbackQueryHandler(button_callback, pattern="^back_to_menu$"),
            ],
            WAITING_FOR_THEME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_game_theme),
                CallbackQueryHandler(button_callback, pattern="^cancel_start_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button_callback),
        ],
    )
    application.add_handler(conv_handler)

    # Обработчик вопросов во время игры
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, game_logic.ask_question)
    )

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
