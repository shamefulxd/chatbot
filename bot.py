import logging
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
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
BOT_TOKEN = BOT_TOKEN
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключение к SQLite
conn = sqlite3.connect('recipes.db', check_same_thread=False)
cursor = conn.cursor()


# Инициализация базы данных
def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        category_id INTEGER,
        ingredients TEXT,
        instructions TEXT,
        user_id INTEGER,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    conn.commit()


init_db()


# Состояния FSM для добавления рецепта
class AddRecipe(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_ingredients = State()
    waiting_for_instructions = State()


# Клавиатуры
def make_main_keyboard():
    buttons = [
        [KeyboardButton(text="Категории 🗂"), KeyboardButton(text="Все рецепты 📋")],
        [KeyboardButton(text="Добавить рецепт ➕")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def make_categories_keyboard():
    cursor.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cursor.fetchall()
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"category_{id}")]
        for id, name in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def make_recipes_keyboard(category_id=None):
    if category_id:
        cursor.execute('''
            SELECT r.id, r.title 
            FROM recipes r
            WHERE r.category_id = ?
            ORDER BY r.title
        ''', (category_id,))
    else:
        cursor.execute('''
            SELECT r.id, r.title 
            FROM recipes r
            ORDER BY r.title
        ''')

    recipes = cursor.fetchall()
    buttons = [
        [InlineKeyboardButton(text=title, callback_data=f"recipe_{id}")]
        for id, title in recipes
    ]

    if category_id:
        buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="back_to_categories")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Хендлеры
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name)
    )
    conn.commit()

    await message.answer(
        "👨‍🍳 Добро пожаловать в бот с рецептами!\n\n"
        "Выберите действие:",
        reply_markup=make_main_keyboard()
    )


# Добавление рецепта - начало
@dp.message(lambda message: message.text == "Добавить рецепт ➕")
async def add_recipe_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Давайте добавим новый рецепт!\n"
        "Сначала выберите категорию из списка или введите новую:",
        reply_markup=make_categories_keyboard()
    )
    await state.set_state(AddRecipe.waiting_for_category)


# Обработка выбора категории
@dp.callback_query(AddRecipe.waiting_for_category, lambda c: c.data.startswith('category_'))
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split('_')[1])
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = cursor.fetchone()[0]

    await state.update_data(category_id=category_id, category_name=category_name)
    await callback.message.answer(
        f"Выбрана категория: {category_name}\n"
        "Теперь введите название рецепта:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AddRecipe.waiting_for_title)
    await callback.answer()


# Обработка новой категории (если пользователь ввел текст вместо выбора)
@dp.message(AddRecipe.waiting_for_category)
async def process_new_category(message: types.Message, state: FSMContext):
    category_name = message.text.strip()

    # Добавляем новую категорию
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
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AddRecipe.waiting_for_title)


# Обработка названия рецепта
@dp.message(AddRecipe.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(
        "Отлично! Теперь введите ингредиенты (каждый с новой строки или через запятую):"
    )
    await state.set_state(AddRecipe.waiting_for_ingredients)


# Обработка ингредиентов
@dp.message(AddRecipe.waiting_for_ingredients)
async def process_ingredients(message: types.Message, state: FSMContext):
    await state.update_data(ingredients=message.text)
    await message.answer(
        "Хорошо! Теперь введите пошаговую инструкцию приготовления:"
    )
    await state.set_state(AddRecipe.waiting_for_instructions)


# Обработка инструкций и сохранение рецепта
@dp.message(AddRecipe.waiting_for_instructions)
async def process_instructions(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = message.from_user.id

    # Сохраняем рецепт
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
        f"✅ Рецепт '{user_data['title']}' успешно добавлен в категорию '{user_data['category_name']}'!",
        reply_markup=make_main_keyboard()
    )
    await state.clear()


# Просмотр категорий
@dp.message(lambda message: message.text == "Категории 🗂")
async def show_categories(message: types.Message):
    await message.answer(
        "Выберите категорию:",
        reply_markup=make_categories_keyboard()
    )


# Просмотр всех рецептов
@dp.message(lambda message: message.text == "Все рецепты 📋")
async def show_all_recipes(message: types.Message):
    await message.answer(
        "Все рецепты:",
        reply_markup=make_recipes_keyboard()
    )


# Просмотр рецептов по категории
@dp.callback_query(lambda c: c.data.startswith('category_'))
async def show_recipes_by_category(callback: types.CallbackQuery):
    category_id = int(callback.data.split('_')[1])
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = cursor.fetchone()[0]

    await callback.message.edit_text(
        f"Рецепты в категории '{category_name}':",
        reply_markup=make_recipes_keyboard(category_id)
    )
    await callback.answer()


# Возврат к категориям
@dp.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=make_categories_keyboard()
    )
    await callback.answer()


# Просмотр конкретного рецепта
@dp.callback_query(lambda c: c.data.startswith('recipe_'))
async def show_recipe(callback: types.CallbackQuery):
    recipe_id = int(callback.data.split('_')[1])

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
        await callback.message.answer(response, parse_mode="HTML")
    else:
        await callback.message.answer("Рецепт не найден")

    await callback.answer()


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
