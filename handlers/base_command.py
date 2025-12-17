from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from typing import Dict
import random


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start. Приветствие и начало регистрации."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    # if chat_id in active_games:
    #     await update.message.reply_text("Игра уже идет в этом чате!")
    #     return

    # Создаем новую игру
    # game = Game(chat_id, CHARACTERS_POOL)
    # active_games[chat_id] = game
    # game.add_player(user.id, user.first_name)

    await update.message.reply_text(
        f"Добро пожаловать в игру 'Угадай персонажа'!\n"
        f"Игрок {user.first_name} зарегистрирован.\n"
        f"Другие игроки пишут /join чтобы присоединиться.\n"
        f"Когда все готовы, напишите /startgame"
    )
    
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторяет сообщение пользователя"""
    # Получаем текст сообщения
    user_message = update.message.text
    
    # Отправляем тот же текст обратно
    await update.message.reply_text(user_message)
    

