# main_v4.py — Исправленный вывод с размерами и материалом
import logging
import asyncio
import gspread
import nest_asyncio
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# Применяем патч для работы с asyncio
nest_asyncio.apply()

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Google Sheets авторизация ===
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


# Инициализация клиента Google Sheets
def init_gsheets():
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Ошибка инициализации Google Sheets: {e}")
        return None


client = init_gsheets()

# === ID таблиц ===
TABLE_IDS = {
    'SVOD': '1iJCFtvWEJeGmqtlMXVhtbJlT153Hk4BsZyh19JONWO8'  # Сводная таблица
}

# === Состояния диалога ===
FILTER_CHOICE, NAME_INPUT, PRODUCER_INPUT = range(3)


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я твой складской помощник 🤖",
        reply_markup=ReplyKeyboardMarkup(
            [["/ostatki", "/help"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )


# === Команда /help ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start - Начать работу с ботом\n"
        "/ostatki - Показать остатки на складе\n"
        "/help - Показать это сообщение\n"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')


# === Проверка подключения к Google Sheets ===
async def check_gsheets_connection():
    if not client:
        logger.error("Не удалось подключиться к Google Sheets")
        return False

    try:
        sheet = client.open_by_key(TABLE_IDS['SVOD'])
        sheet.worksheet('Общий склад')
        return True
    except Exception as e:
        logger.error(f"Ошибка доступа к таблице: {e}")
        return False


# === Команда /ostatki ===
async def ostatki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем подключение к Google Sheets
    if not await check_gsheets_connection():
        await update.message.reply_text("❌ Ошибка подключения к Google Sheets. Попробуйте позже.")
        return ConversationHandler.END

    keyboard = [
        [KeyboardButton("🔍 По наименованию")],
        [KeyboardButton("🏭 По производителю")],
        [KeyboardButton("📋 Показать всё")]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "Выбери способ фильтрации остатков:",
        reply_markup=reply_markup
    )
    return FILTER_CHOICE


# === Обработка выбора фильтра ===
async def handle_filter_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    context.user_data['filter_choice'] = choice

    if "наименованию" in choice:
        await update.message.reply_text("Введите наименование товара:")
        return NAME_INPUT

    elif "производителю" in choice:
        # Получаем уникальных производителей
        producers = await get_unique_producers()
        if not producers:
            await update.message.reply_text("❌ Данные о производителях не найдены")
            return ConversationHandler.END

        keyboard = [[KeyboardButton(p)] for p in producers]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await update.message.reply_text(
            "Выберите производителя:",
            reply_markup=reply_markup
        )
        return PRODUCER_INPUT

    else:  # Показать всё
        await show_all_products(update)
        return ConversationHandler.END


# === Получение уникальных производителей ===
async def get_unique_producers():
    try:
        sheet = client.open_by_key(TABLE_IDS['SVOD']).worksheet('Общий склад')
        data = sheet.get_all_values()

        if len(data) < 2:
            return []

        headers = [h.strip().lower() for h in data[0]]  # Нормализация заголовков

        # Поиск индекса столбца производителя
        prod_idx = -1
        possible_names = ['производство', 'производитель', 'тег', 'завод', 'производства']
        for idx, header in enumerate(headers):
            if any(name in header for name in possible_names):
                prod_idx = idx
                break

        if prod_idx == -1:
            logger.error("Столбец производителя не найден. Заголовки: %s", headers)
            return []

        # Собираем уникальных производителей (игнорируем пустые значения)
        producers = set()
        for row in data[1:]:
            if len(row) > prod_idx and row[prod_idx].strip():
                # Нормализация названий производств
                producer_name = row[prod_idx].strip()
                if "карелия" in producer_name.lower():
                    producer_name = "Карелия Гранит"
                elif "техногаббро" in producer_name.lower():
                    producer_name = "Техногаббро"
                elif "евромодул" in producer_name.lower():
                    producer_name = "Евромодуль"
                producers.add(producer_name)

        return sorted(producers)

    except Exception as e:
        logger.error(f"Ошибка при получении производителей: {e}")
        return []


# === Показать все товары с детализацией ===
async def show_all_products(update: Update):
    try:
        sheet = client.open_by_key(TABLE_IDS['SVOD']).worksheet('Общий склад')
        data = sheet.get_all_values()

        if len(data) < 2:
            await update.message.reply_text("❌ Данные не найдены")
            return

        headers = [h.strip().lower() for h in data[0]]

        # Поиск индексов столбцов
        name_idx = headers.index('наименование') if 'наименование' in headers else -1
        prod_idx = headers.index('тег производства') if 'тег производства' in headers else -1
        qty_idx = headers.index('количество') if 'количество' in headers else -1
        material_idx = headers.index('материал') if 'материал' in headers else -1
        length_idx = headers.index('длина (мм)') if 'длина (мм)' in headers else -1
        width_idx = headers.index('ширина (мм)') if 'ширина (мм)' in headers else -1
        height_idx = headers.index('высота (мм)') if 'высота (мм)' in headers else -1

        if name_idx == -1 or qty_idx == -1:
            await update.message.reply_text("❌ Не найдены необходимые столбцы в таблице")
            return

        # Формируем сообщение
        message = "📦 <b>Товары на складе:</b>\n\n"
        count = 0

        for row in data[1:]:
            if len(row) > max(name_idx, qty_idx) and row[qty_idx].strip():
                # Нормализация названия производства
                producer = row[prod_idx].strip() if prod_idx != -1 and len(row) > prod_idx else ""
                if "карелия" in producer.lower():
                    producer = "Карелия Гранит"
                elif "техногаббро" in producer.lower():
                    producer = "Техногаббро"
                elif "евромодул" in producer.lower():
                    producer = "Евромодуль"

                # Формируем информацию о товаре
                product_info = f"▪️ <b>{row[name_idx]}</b>"

                # Добавляем материал
                if material_idx != -1 and len(row) > material_idx and row[material_idx].strip():
                    product_info += f" [{row[material_idx]}]"

                # Добавляем размеры
                dimensions = []
                if length_idx != -1 and len(row) > length_idx and row[length_idx].strip():
                    dimensions.append(f"Д: {row[length_idx]}мм")
                if width_idx != -1 and len(row) > width_idx and row[width_idx].strip():
                    dimensions.append(f"Ш: {row[width_idx]}мм")
                if height_idx != -1 and len(row) > height_idx and row[height_idx].strip():
                    dimensions.append(f"В: {row[height_idx]}мм")

                if dimensions:
                    product_info += f" ({', '.join(dimensions)})"

                # Добавляем количество и производителя
                product_info += f" - {row[qty_idx]} шт"
                if producer:
                    product_info += f" ({producer})"

                # Разбиваем сообщение на части, если слишком длинное
                if len(message + product_info + "\n") > 4000:
                    await update.message.reply_text(message, parse_mode='HTML')
                    message = ""

                message += product_info + "\n"
                count += 1

        if count == 0:
            message = "❌ Товары не найдены"

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при показе всех товаров: {e}")
        await update.message.reply_text("❌ Ошибка при получении данных")


# === Обработка ввода наименования ===
async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_name = update.message.text
    await search_by_name(update, product_name)
    return ConversationHandler.END


# === Поиск по наименованию с детализацией ===
async def search_by_name(update: Update, product_name: str):
    try:
        sheet = client.open_by_key(TABLE_IDS['SVOD']).worksheet('Общий склад')
        data = sheet.get_all_values()

        if len(data) < 2:
            await update.message.reply_text("❌ Данные не найдены")
            return

        headers = [h.strip().lower() for h in data[0]]

        # Поиск индексов столбцов
        name_idx = headers.index('наименование') if 'наименование' in headers else -1
        qty_idx = headers.index('количество') if 'количество' in headers else -1
        material_idx = headers.index('материал') if 'материал' in headers else -1
        length_idx = headers.index('длина (мм)') if 'длина (мм)' in headers else -1
        width_idx = headers.index('ширина (мм)') if 'ширина (мм)' in headers else -1
        height_idx = headers.index('высота (мм)') if 'высота (мм)' in headers else -1
        prod_idx = headers.index('тег производства') if 'тег производства' in headers else -1

        if name_idx == -1 or qty_idx == -1:
            await update.message.reply_text("❌ Не найдены необходимые столбцы в таблице")
            return

        # Ищем совпадения
        found = False
        message = f"🔍 <b>Результаты по запросу '{product_name}':</b>\n\n"

        for row in data[1:]:
            if len(row) > max(name_idx, qty_idx) and product_name.lower() in row[name_idx].lower():
                found = True

                # Формируем информацию о товаре
                product_info = f"▪️ <b>{row[name_idx]}</b>"

                # Добавляем материал
                if material_idx != -1 and len(row) > material_idx and row[material_idx].strip():
                    product_info += f" [{row[material_idx]}]"

                # Добавляем размеры
                dimensions = []
                if length_idx != -1 and len(row) > length_idx and row[length_idx].strip():
                    dimensions.append(f"Д: {row[length_idx]}мм")
                if width_idx != -1 and len(row) > width_idx and row[width_idx].strip():
                    dimensions.append(f"Ш: {row[width_idx]}мм")
                if height_idx != -1 and len(row) > height_idx and row[height_idx].strip():
                    dimensions.append(f"В: {row[height_idx]}мм")

                if dimensions:
                    product_info += f" ({', '.join(dimensions)})"

                # Добавляем количество и производителя
                product_info += f" - {row[qty_idx]} шт"
                if prod_idx != -1 and len(row) > prod_idx and row[prod_idx].strip():
                    # Нормализация названия производства
                    producer = row[prod_idx].strip()
                    if "карелия" in producer.lower():
                        producer = "Карелия Гранит"
                    elif "техногаббро" in producer.lower():
                        producer = "Техногаббро"
                    elif "евромодул" in producer.lower():
                        producer = "Евромодуль"
                    product_info += f" ({producer})"

                # Разбиваем сообщение на части, если слишком длинное
                if len(message + product_info + "\n") > 4000:
                    await update.message.reply_text(message, parse_mode='HTML')
                    message = ""

                message += product_info + "\n"

        if not found:
            message = f"❌ Товары по запросу '{product_name}' не найдены"

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при поиске по наименованию: {e}")
        await update.message.reply_text("❌ Ошибка при поиске товара")


# === Обработка выбора производителя ===
async def handle_producer_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    producer = update.message.text
    await search_by_producer(update, producer)
    return ConversationHandler.END


# === Поиск по производителю с детализацией ===
async def search_by_producer(update: Update, producer: str):
    try:
        sheet = client.open_by_key(TABLE_IDS['SVOD']).worksheet('Общий склад')
        data = sheet.get_all_values()

        if len(data) < 2:
            await update.message.reply_text("❌ Данные не найдены")
            return

        headers = [h.strip().lower() for h in data[0]]

        # Поиск индекса столбца производителя
        prod_idx = -1
        possible_names = ['производство', 'производитель', 'тег', 'завод', 'производства']
        for idx, header in enumerate(headers):
            if any(name in header for name in possible_names):
                prod_idx = idx
                break

        if prod_idx == -1:
            await update.message.reply_text("❌ Столбец производителя не найден")
            return

        qty_idx = headers.index('количество') if 'количество' in headers else -1
        name_idx = headers.index('наименование') if 'наименование' in headers else -1
        material_idx = headers.index('материал') if 'материал' in headers else -1
        length_idx = headers.index('длина (мм)') if 'длина (мм)' in headers else -1
        width_idx = headers.index('ширина (мм)') if 'ширина (мм)' in headers else -1
        height_idx = headers.index('высота (мм)') if 'высота (мм)' in headers else -1

        if qty_idx == -1:
            await update.message.reply_text("❌ Столбец количества не найден")
            return

        # Ищем совпадения
        found = False
        message = f"🏭 <b>Товары производителя '{producer}':</b>\n\n"

        for row in data[1:]:
            if len(row) > max(prod_idx, qty_idx):
                # Нормализация названия производства
                row_producer = row[prod_idx].strip()
                if "карелия" in row_producer.lower():
                    row_producer = "Карелия Гранит"
                elif "техногаббро" in row_producer.lower():
                    row_producer = "Техногаббро"
                elif "евромодул" in row_producer.lower():
                    row_producer = "Евромодуль"

                if producer.lower() == row_producer.lower():
                    found = True

                    # Формируем информацию о товаре
                    name = row[name_idx] if name_idx != -1 and len(row) > name_idx else "Товар"
                    product_info = f"▪️ <b>{name}</b>"

                    # Добавляем материал
                    if material_idx != -1 and len(row) > material_idx and row[material_idx].strip():
                        product_info += f" [{row[material_idx]}]"

                    # Добавляем размеры
                    dimensions = []
                    if length_idx != -1 and len(row) > length_idx and row[length_idx].strip():
                        dimensions.append(f"Д: {row[length_idx]}мм")
                    if width_idx != -1 and len(row) > width_idx and row[width_idx].strip():
                        dimensions.append(f"Ш: {row[width_idx]}мм")
                    if height_idx != -1 and len(row) > height_idx and row[height_idx].strip():
                        dimensions.append(f"В: {row[height_idx]}мм")

                    if dimensions:
                        product_info += f" ({', '.join(dimensions)})"

                    # Добавляем количество
                    product_info += f" - {row[qty_idx]} шт"

                    # Разбиваем сообщение на части, если слишком длинное
                    if len(message + product_info + "\n") > 4000:
                        await update.message.reply_text(message, parse_mode='HTML')
                        message = ""

                    message += product_info + "\n"

        if not found:
            message = f"❌ Товары производителя '{producer}' не найдены"

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при поиске по производителю: {e}")
        await update.message.reply_text("❌ Ошибка при поиске по производителю")


# === Отмена диалога ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Операция отменена')
    return ConversationHandler.END


# === Запуск приложения ===
def main():
    if not client:
        logger.error("Не удалось инициализировать клиент Google Sheets. Проверьте credentials.json")
        return

    # Создаем приложение
    application = ApplicationBuilder().token('7792257008:AAGngevMPifXSz3KfXdsoXm5JPeeg0tTA1Q').build()

    # Обработчик команды /ostatki
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ostatki', ostatki_command)],
        states={
            FILTER_CHOICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filter_choice)
            ],
            NAME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_input)
            ],
            PRODUCER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_producer_input)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Регистрируем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))

    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling()


if __name__ == '__main__':
    main()