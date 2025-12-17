from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! Добро пожаловать в игрового бота!\n\n"
        "Доступные команды:\n"
        "/lobby - Управление лобби\n"
        "/my_lobby - Моё текущее лобби\n"
        "/help - Помощь"
    )
