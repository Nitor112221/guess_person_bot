import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import os
from typing import Optional
from handlers.base_command import start, echo
from dotenv import load_dotenv

load_dotenv()
# Берем из переменных окружения (безопасно!)
BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main() -> None:
    """Запуск бота."""
    # Создаем Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT, echo))
    # application.add_handler(CommandHandler("join", join))
    # application.add_handler(CommandHandler("startgame", start_game))

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()