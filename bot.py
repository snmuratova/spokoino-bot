import asyncio
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ================= UI =================

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Шаг 1 — Дыхание", callback_data="breath")
    kb.button(text="🧠 Шаг 2 — Разобрать тревогу", callback_data="questions")
    kb.button(text="🪨 Шаг 3 — Заземление", callback_data="ground")
    kb.button(text="📌 Шаг 4 — План на 2 минуты", callback_data="plan")
    kb.adjust(1)
    return kb.as_markup()


def nav_buttons():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Ещё шаг", callback_data="more")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


def now_future_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Сейчас", callback_data="aq_now")
    kb.button(text="🔮 Будущее", callback_data="aq_future")
    kb.adjust(2)
    return kb.as_markup()


# ================= FSM =================

class AnxietyFlow(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()


# ================= START =================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💙 *Навигатор спокойствия*\n\n"
        "Если тревожно — ты не одна.\n"
        "Давай снизим напряжение шаг за шагом.\n\n"
        "Выбери шаг:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "menu")
async def back_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.edit_text(
        "💙 *Навигатор спокойствия*\n\nВыбери шаг:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "more")
async def more(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "Продолжим 💛\n\nВыбери следующий шаг:",
        reply_markup=main_menu()
    )


# ================= ШАГ 1 =================

@dp.callback_query(F.data == "breath")
async def breath(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "🌬 *Шаг 1 из 4 — Дыхание*\n\n"
        "Когда тревога усиливается, телу важно замедлиться.\n\n"
        "*Физиологический вздох:*\n"
        "Вдох → маленький довдох → длинный выдох\n\n"
        "Повтори 3–5 раз.\n\n"
        "Или вдох на 4… выдох на 6… (8 циклов)\n\n"
        "Ты уже помогаешь себе 💛",
        parse_mode="Markdown",
        reply_markup=nav_buttons()
    )


# ================= ШАГ 2 =================

@dp.callback_query(F.data == "questions")
async def questions_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AnxietyFlow.q1)
    await cb.message.edit_text(
        "🧠 *Шаг 2 из 4 — Разобрать тревогу*\n\n"
        "Я понимаю тебя.\n\n"
        "1️⃣ Что сейчас пугает больше всего?\n"
        "(в 1 фразе)",
        parse_mode="Markdown"
    )


@dp.message(AnxietyFlow.q1)
async def q1(message: Message, state: FSMContext):
    await state.update_data(q1=message.text)
    await state.set_state(AnxietyFlow.q2)
    await message.answer(
        "2️⃣ Это больше про сейчас или про будущее?",
        reply_markup=now_future_kb()
    )


@dp.callback_query(AnxietyFlow.q2, F.data.in_(["aq_now", "aq_future"]))
async def q2(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    value = "про сейчас" if cb.data == "aq_now" else "про будущее"
    await state.update_data(q2=value)
    await state.set_state(AnxietyFlow.q3)
    await cb.message.answer(
        "3️⃣ Что можно сделать в ближайшие 10 минут,\n"
        "чтобы стало хотя бы на 5% легче?"
    )


@dp.message(AnxietyFlow.q3)
async def q3(message: Message, state: FSMContext):
    await state.update_data(q3=message.text)
    await state.set_state(AnxietyFlow.q4)
    await message.answer(
        "4️⃣ Представь, что друг или близкий человек\n"
        "написал тебе это же.\n"
        "Что бы ты ответила?"
    )


@dp.message(AnxietyFlow.q4)
async def q4(message: Message, state: FSMContext):
    data = await state.get_data()

    summary = (
        "✨ *Ты уже проделала важную работу*\n\n"
        f"• Пугает: {data.get('q1')}\n"
        f"• Это: {data.get('q2')}\n"
        f"• Маленький шаг: {data.get('q3')}\n"
        f"• Поддержка: {message.text}\n\n"
        "Ты справляешься 💛"
    )

    await message.answer(summary, parse_mode="Markdown", reply_markup=nav_buttons())
    await state.clear()


# ================= ШАГ 3 =================

@dp.callback_query(F.data == "ground")
async def ground(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "🪨 *Шаг 3 из 4 — Заземление*\n\n"
        "Сделай медленный вдох… и выдох…\n\n"
        "👀 5 вещей, которые ты видишь\n"
        "🤍 4 ощущения (тепло/холодно, удобно ли)\n"
        "👂 3 звука вокруг\n"
        "🌬 2 запаха\n"
        "👅 1 вкус\n"
        "Если вкуса нет — представь свежие ягоды или фрукты.\n\n"
        "Ты здесь. Ты в безопасности 💛",
        parse_mode="Markdown",
        reply_markup=nav_buttons()
    )


# ================= ШАГ 4 =================

@dp.callback_query(F.data == "plan")
async def plan(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "📌 *Шаг 4 из 4 — План на 2 минуты*\n\n"
        "Выбери один маленький шаг:\n\n"
        "🥤 Выпить воды\n"
        "🌬 Глубокий вдох свежего воздуха\n"
        "💬 Написать близкому человеку\n"
        "📝 3 факта → 1 маленький шаг\n"
        "⏲ Таймер 2 минуты\n\n"
        "Только один шаг. Этого достаточно 💛",
        parse_mode="Markdown",
        reply_markup=nav_buttons()
    )


# ================= WEB SERVER =================

async def handle_root(request):
    return web.Response(text="OK")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()


async def main():
    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
