from telegram import Update, ReplyKeyboardRemove
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Dict
import random
from config import SELECTING_ACTION, CREATING_LOBBY, JOINING_LOBBY



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

