from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! Добро пожаловать в игрового бота!\n\n"
        "Доступные команды:\n"
        "/lobby - Управление лобби\n"
        "/help - Помощь"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    help_text = (
        "📚 Справка по командам:\n\n"
        "🏠 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/lobby - Управление лобби\n"
        "/history - История ваших вопросов (только во время игры)\n"
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
    # TODO: при добавлении приватности поменять help

    await update.message.reply_text(help_text)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")]]
        ),
    )
    return ConversationHandler.END
