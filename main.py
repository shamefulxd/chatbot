import logging
import random
import sqlite3
from config import BOT_TOKEN
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
API_TOKEN = BOT_TOKEN
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключение к SQLite
conn = sqlite3.connect('recipes.db', check_same_thread=False)
cursor = conn.cursor()


def init_db():
    """Инициализация базы данных."""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category_id INTEGER NOT NULL,
        ingredients TEXT NOT NULL,
        instructions TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')

    # Добавляем базовые категории
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        basic_categories = [
            ('Завтраки',), ('Обеды',), ('Ужины',),
            ('Десерты',), ('Выпечка',), ('Напитки',)
        ]
        cursor.executemany(
            "INSERT INTO categories (name) VALUES (?)",
            basic_categories
        )
        conn.commit()


init_db()


class RecipeStates(StatesGroup):
    """Состояния FSM для добавления рецепта."""
    select_category = State()
    enter_title = State()
    enter_ingredients = State()
    enter_instructions = State()


def main_menu_keyboard():
    """Клавиатура главного меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Все рецепты"),
             KeyboardButton(text="🗂 Категории")],
            [KeyboardButton(text="🎲 Случайный рецепт"),
             KeyboardButton(text="➕ Добавить рецепт")],
            [KeyboardButton(text="🔍 Поиск")]
        ],
        resize_keyboard=True
    )


def random_recipe_keyboard():
    """Клавиатура для случайного рецепта."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎲 Новый случайный рецепт")],
            [KeyboardButton(text="🏠 На главную")]
        ],
        resize_keyboard=True
    )


def home_keyboard():
    """Клавиатура с кнопкой возврата на главную."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 На главную")]],
        resize_keyboard=True
    )


def cancel_keyboard():
    """Клавиатура отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


def categories_keyboard():
    """Клавиатура с категориями."""
    cursor.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cursor.fetchall()

    buttons = []
    row = []
    for i, (id_, name) in enumerate(categories, 1):
        row.append(InlineKeyboardButton(text=name, callback_data=f"cat_{id_}"))
        if i % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def recipes_keyboard(category_id=None, page=0, per_page=5):
    """Клавиатура с рецептами."""
    if category_id:
        cursor.execute('''
            SELECT id, title FROM recipes 
            WHERE category_id = ?
            ORDER BY title
            LIMIT ? OFFSET ?
        ''', (category_id, per_page, page * per_page))
    else:
        cursor.execute('''
            SELECT id, title FROM recipes 
            ORDER BY title
            LIMIT ? OFFSET ?
        ''', (per_page, page * per_page))

    recipes = cursor.fetchall()

    buttons = []
    for id_, title in recipes:
        buttons.append([InlineKeyboardButton(text=title, callback_data=f"rec_{id_}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prev_{page}_{category_id or 0}"
            )
        )

    if len(recipes) == per_page:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"next_{page}_{category_id or 0}"
            )
        )

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(text="🏠 На главную", callback_data="main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_random_recipe(message: types.Message):
    """Отправляет случайный рецепт."""
    cursor.execute("SELECT COUNT(*) FROM recipes")
    count = cursor.fetchone()[0]
    random_id = random.randint(1, count)

    cursor.execute('''
        SELECT r.title, c.name, r.ingredients, r.instructions, u.full_name
        FROM recipes r
        JOIN categories c ON r.category_id = c.id
        JOIN users u ON r.user_id = u.user_id
        WHERE r.id = ?
    ''', (random_id,))

    recipe = cursor.fetchone()

    if recipe:
        title, category, ingredients, instructions, author = recipe
        response = (
            f"🎲 <b>Случайный рецепт:</b>\n\n"
            f"🍳 <b>{title}</b>\n"
            f"📌 Категория: {category}\n\n"
            f"🛒 <b>Ингредиенты:</b>\n{ingredients}\n\n"
            f"📝 <b>Инструкции:</b>\n{instructions}\n\n"
            f"👨‍🍳 Автор: {author}"
        )
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=random_recipe_keyboard()
        )
    else:
        await send_random_recipe(message)


@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    """Обработчик команд /start и /help."""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name)
    )
    conn.commit()

    await message.answer(
        "👨‍🍳 Добро пожаловать в RecipeBot!\n"
        "Здесь вы можете хранить и делиться своими рецептами.\n\n"
        "Основные команды:\n"
        "- 🍽 Все рецепты - просмотр всех рецептов\n"
        "- 🗂 Категории - просмотр по категориям\n"
        "- 🎲 Случайный рецепт - получить случайный рецепт\n"
        "- ➕ Добавить рецепт - создать новый рецепт\n"
        "- 🔍 Поиск - найти рецепт по названию\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard()
    )


@dp.message(lambda message: message.text == "🏠 На главную")
async def go_to_main_menu(message: types.Message, state: FSMContext):
    """Возврат в главное меню."""
    await state.clear()
    await message.answer(
        "Вы вернулись в главное меню:",
        reply_markup=main_menu_keyboard()
    )


@dp.message(lambda message: message.text == "🗂 Категории")
async def show_categories(message: types.Message):
    """Показывает список категорий."""
    await message.answer(
        "Выберите категорию:",
        reply_markup=categories_keyboard()
    )


@dp.callback_query(lambda c: c.data.startswith("cat_"))
async def show_recipes_in_category(callback: types.CallbackQuery):
    """Показывает рецепты в выбранной категории."""
    category_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = cursor.fetchone()[0]

    await callback.message.answer(
        f"Рецепты в категории '{category_name}':",
        reply_markup=recipes_keyboard(category_id=category_id)
    )
    await callback.answer()


@dp.message(lambda message: message.text == "🍽 Все рецепты")
async def show_all_recipes(message: types.Message):
    """Показывает все рецепты."""
    await message.answer(
        "Все рецепты:",
        reply_markup=recipes_keyboard()
    )


@dp.message(lambda message: message.text == "🎲 Случайный рецепт")
async def random_recipe(message: types.Message):
    """Обработчик случайного рецепта."""
    cursor.execute("SELECT COUNT(*) FROM recipes")
    count = cursor.fetchone()[0]

    if count == 0:
        await message.answer(
            "В базе пока нет рецептов.",
            reply_markup=main_menu_keyboard()
        )
        return

    await send_random_recipe(message)


@dp.message(lambda message: message.text == "🎲 Новый случайный рецепт")
async def new_random_recipe(message: types.Message):
    """Обработчик для нового случайного рецепта."""
    await send_random_recipe(message)


@dp.callback_query(lambda c: c.data.startswith(("rec_", "prev_", "next_")))
async def handle_recipes_pagination(callback: types.CallbackQuery):
    """Обработчик пагинации рецептов."""
    if callback.data.startswith("rec_"):
        recipe_id = int(callback.data.split("_")[1])

        cursor.execute('''
            SELECT r.title, c.name, r.ingredients, r.instructions, u.full_name
            FROM recipes r
            JOIN categories c ON r.category_id = c.id
            JOIN users u ON r.user_id = u.user_id
            WHERE r.id = ?
        ''', (recipe_id,))
        recipe = cursor.fetchone()

        if recipe:
            title, category, ingredients, instructions, author = recipe
            response = (
                f"🍳 <b>{title}</b>\n"
                f"📌 Категория: {category}\n\n"
                f"🛒 <b>Ингредиенты:</b>\n{ingredients}\n\n"
                f"📝 <b>Инструкции:</b>\n{instructions}\n\n"
                f"👨‍🍳 Автор: {author}"
            )
            await callback.message.answer(
                response,
                parse_mode="HTML",
                reply_markup=home_keyboard()
            )
        else:
            await callback.message.answer("Рецепт не найден")
    else:
        action, page, category_id = callback.data.split("_")
        page = int(page)
        category_id = int(category_id) if category_id != "0" else None

        if action == "prev":
            page -= 1
        elif action == "next":
            page += 1

        if category_id:
            cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
            category_name = cursor.fetchone()[0]
            await callback.message.edit_text(
                f"Рецепты в категории '{category_name}':",
                reply_markup=recipes_keyboard(category_id=category_id, page=page)
            )
        else:
            await callback.message.edit_text(
                "Все рецепты:",
                reply_markup=recipes_keyboard(page=page)
            )

    await callback.answer()


@dp.message(lambda message: message.text == "➕ Добавить рецепт")
async def start_adding_recipe(message: types.Message, state: FSMContext):
    """Начинает процесс добавления рецепта."""
    await message.answer(
        "Давайте добавим новый рецепт!\n"
        "Выберите категорию из списка или введите новую:",
        reply_markup=categories_keyboard()
    )
    await state.set_state(RecipeStates.select_category)


@dp.message(lambda message: message.text == "❌ Отмена")
async def cancel_adding(message: types.Message, state: FSMContext):
    """Отменяет добавление рецепта."""
    await state.clear()
    await message.answer(
        "Добавление рецепта отменено.",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query(RecipeStates.select_category, lambda c: c.data.startswith("cat_"))
async def select_existing_category(callback: types.CallbackQuery, state: FSMContext):
    """Выбор существующей категории."""
    category_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = cursor.fetchone()[0]

    await state.update_data(category_id=category_id, category_name=category_name)
    await callback.message.answer(
        f"Выбрана категория: {category_name}\n"
        "Теперь введите название рецепта:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(RecipeStates.enter_title)
    await callback.answer()


@dp.message(RecipeStates.select_category)
async def enter_new_category(message: types.Message, state: FSMContext):
    """Создание новой категории."""
    if message.text == "❌ Отмена":
        await cancel_adding(message, state)
        return

    category_name = message.text.strip()

    cursor.execute(
        "INSERT OR IGNORE INTO categories (name) VALUES (?)",
        (category_name,)
    )
    conn.commit()

    cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
    category_id = cursor.fetchone()[0]

    await state.update_data(category_id=category_id, category_name=category_name)
    await message.answer(
        f"Создана новая категория: {category_name}\n"
        "Теперь введите название рецепта:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(RecipeStates.enter_title)


@dp.message(RecipeStates.enter_title)
async def enter_recipe_title(message: types.Message, state: FSMContext):
    """Ввод названия рецепта."""
    if message.text == "❌ Отмена":
        await cancel_adding(message, state)
        return

    await state.update_data(title=message.text)
    await message.answer(
        "Отлично! Теперь введите ингредиенты (каждый с новой строки):",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(RecipeStates.enter_ingredients)


@dp.message(RecipeStates.enter_ingredients)
async def enter_recipe_ingredients(message: types.Message, state: FSMContext):
    """Ввод ингредиентов."""
    if message.text == "❌ Отмена":
        await cancel_adding(message, state)
        return

    await state.update_data(ingredients=message.text)
    await message.answer(
        "Хорошо! Теперь введите пошаговую инструкцию приготовления:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(RecipeStates.enter_instructions)


@dp.message(RecipeStates.enter_instructions)
async def enter_recipe_instructions(message: types.Message, state: FSMContext):
    """Ввод инструкций и сохранение рецепта."""
    if message.text == "❌ Отмена":
        await cancel_adding(message, state)
        return

    user_data = await state.get_data()
    user_id = message.from_user.id

    cursor.execute(
        '''INSERT INTO recipes 
        (title, category_id, ingredients, instructions, user_id)
        VALUES (?, ?, ?, ?, ?)''',
        (
            user_data['title'],
            user_data['category_id'],
            user_data['ingredients'],
            message.text,
            user_id
        )
    )
    conn.commit()

    await message.answer(
        f"✅ Рецепт '{user_data['title']}' успешно добавлен "
        f"в категорию '{user_data['category_name']}'!",
        reply_markup=main_menu_keyboard()
    )
    await state.clear()


@dp.message(lambda message: message.text == "🔍 Поиск")
async def start_search(message: types.Message):
    """Начинает процесс поиска."""
    await message.answer(
        "Введите название рецепта или часть названия для поиска:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )


@dp.message(lambda message: message.text and message.text != "❌ Отмена")
async def search_recipes(message: types.Message):
    """Выполняет поиск рецептов."""
    search_query = f"%{message.text}%"
    cursor.execute('''
        SELECT r.id, r.title, c.name 
        FROM recipes r
        JOIN categories c ON r.category_id = c.id
        WHERE r.title LIKE ?
        ORDER BY r.title
        LIMIT 20
    ''', (search_query,))

    recipes = cursor.fetchall()

    if recipes:
        buttons = [
            [InlineKeyboardButton(text=f"{title} ({category})", callback_data=f"rec_{id_}")]
            for id_, title, category in recipes
        ]

        await message.answer(
            f"Результаты поиска по запросу '{message.text}':",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    else:
        await message.answer(
            "Рецепты по вашему запросу не найдены.",
            reply_markup=main_menu_keyboard()
        )


async def main():
    """Запуск бота."""
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
