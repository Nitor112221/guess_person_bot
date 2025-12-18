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

from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY
from database_manager import DatabaseManager
from handlers.base_command import cancel, start, help_command
from lobby.commands import button_callback, process_invite_code, lobby_menu

load_dotenv()
# Берем из переменных окружения (безопасно!)
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Запуск бота."""
    # Подключаемся к базе данных

    if not os.path.exists("data/"):
        os.mkdir("data/")

    DatabaseManager()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    # application.add_handler(CommandHandler("my_lobby", my_lobby_info))

    # ConversationHandler для управления лобби
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("lobby", lobby_menu)],
        states={
            SELECTING_ACTION: [CallbackQueryHandler(button_callback)],
            JOINING_LOBBY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_invite_code),
                CallbackQueryHandler(button_callback, pattern="^back_to_menu$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button_callback),
        ],
    )

    application.add_handler(conv_handler)

    # Обработчики callback кнопок вне ConversationHandler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
