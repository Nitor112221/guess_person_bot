from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import logging
from ServiceController import ServiceContainer

logger = logging.getLogger(__name__)


def get_services():
    """Ленивая загрузка сервисов"""
    if not hasattr(get_services, "_instance"):
        get_services._instance = ServiceContainer()
    return get_services._instance


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! Добро пожаловать в игрового бота!\n\n"
        "Доступные команды:\n"
        "/lobby - Управление лобби\n"
        "/leave - Выйти из лобби\n"  # Добавлено
        "/help - Помощь"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    help_text = (
        "📚 Справка по командам:\n\n"
        "🏠 Основные команды:\n"
        "/start - Начать работу с ботом\n"
        "/lobby - Управление лобби\n"
        "/leave - Выйти из лобби\n"  # Добавлено
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

    await update.message.reply_text(help_text)


async def leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /leave для выхода из лобби"""
    try:
        # Получаем сервисы
        services = get_services()
        lobby_manager = services.lobby_manager

        user_id = update.effective_user.id

        # Получаем текущее лобби пользователя
        lobby_id = lobby_manager.get_user_lobby(user_id)

        if not lobby_id:
            await update.message.reply_text("❌ Вы не находитесь ни в одном лобби.")
            return

        # Получаем информацию о лобби для подтверждения
        lobby_info = lobby_manager.get_lobby_info(lobby_id)

        # Создаем клавиатуру для подтверждения
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Да, выйти", callback_data=f"confirm_leave_{lobby_id}"
                ),
                InlineKeyboardButton("❌ Нет, остаться", callback_data="cancel_leave"),
            ]
        ]

        # Формируем сообщение с информацией о лобби
        message_text = (
            f"❓ Вы уверены, что хотите выйти из лобби?\n\n"
            f"🏠 Лобби ID: {lobby_id}\n"
            f"👥 Игроков: {lobby_info.current_players if lobby_info else '?'}\n"
            f"📊 Статус: {lobby_info.status if lobby_info else '?'}"
        )

        await update.message.reply_text(
            message_text, reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка в команде /leave: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при попытке выйти из лобби. "
            "Попробуйте еще раз или используйте меню /lobby."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")]]
        ),
    )
    return ConversationHandler.END


async def cancel_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена выхода из лобби"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("✅ Выход отменен. Вы остаетесь в лобби.")
