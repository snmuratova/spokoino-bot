import asyncio
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ========= Меню (кнопки снизу) =========
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🌬 Дыхание")
    kb.button(text="🧠 Разобрать тревогу")
    kb.button(text="🪨 Заземление")
    kb.button(text="📌 План на 2 минуты")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def after_step_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Ещё один шаг", callback_data="more_step")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def choose_next_step_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Дыхание", callback_data="step_breath")
    kb.button(text="🧠 Вопросы", callback_data="step_questions")
    kb.button(text="🪨 Заземление", callback_data="step_ground")
    kb.button(text="📌 План 2 мин", callback_data="step_plan")
    kb.adjust(2, 2)
    return kb.as_markup()


# ========= Шаг 2: Вопросы (FSM) =========
class AnxietyQuestions(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()


def kb_now_future():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Про сейчас", callback_data="aq_now")
    kb.button(text="🔮 Про будущее", callback_data="aq_future")
    kb.adjust(2)
    return kb.as_markup()


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет 💙\n"
        "Если тревожно — давай снизим уровень тревоги за несколько шагов.\n\n"
        "Выбери, с чего начнём:",
        reply_markup=main_menu_kb()
    )
    await message.answer("Можно идти по шагам 👇", reply_markup=choose_next_step_kb())


@dp.callback_query(F.data == "menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer("Меню 👇", reply_markup=main_menu_kb())
    await cb.message.answer("Выбери шаг:", reply_markup=choose_next_step_kb())


@dp.callback_query(F.data == "more_step")
async def more_step(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("Ок. Что сделаем дальше?", reply_markup=choose_next_step_kb())


# ========= ШАГ 1: Дыхание =========
@dp.message(F.text == "🌬 Дыхание")
async def breath_from_menu(message: Message):
    await send_breath(message)

@dp.callback_query(F.data == "step_breath")
async def breath_from_inline(cb: CallbackQuery):
    await cb.answer()
    await send_breath(cb.message)

async def send_breath(target: Message):
    await target.answer(
        "🌬 **Шаг 1: Дыхание**\n\n"
        "Самый быстрый вариант — *«физиологический вздох»*:\n"
        "1) Вдох носом\n"
        "2) Ещё маленький довдох (как «добавить воздуха»)\n"
        "3) Длинный выдох ртом\n"
        "Повтори 3–5 раз.\n\n"
        "Запасной вариант — *4–6*:\n"
        "Вдох на 4, выдох на 6. Сделай 8 циклов.\n",
        parse_mode="Markdown",
        reply_markup=after_step_kb()
    )


# ========= ШАГ 3: Заземление =========
@dp.message(F.text == "🪨 Заземление")
async def ground_from_menu(message: Message):
    await send_ground(message)

@dp.callback_query(F.data == "step_ground")
async def ground_from_inline(cb: CallbackQuery):
    await cb.answer()
    await send_ground(cb.message)

async def send_ground(target: Message):
    await target.answer(
        "🪨 **Шаг 3: Заземление 5–4–3–2–1**\n\n"
        "Назови:\n"
        "5 — что видишь\n"
        "4 — что чувствуешь телом\n"
        "3 — что слышишь\n"
        "2 — какие запахи\n"
        "1 — какой вкус\n\n"
        "Это помогает, когда мысли разгоняются.\n",
        parse_mode="Markdown",
        reply_markup=after_step_kb()
    )


# ========= ШАГ 4: План на 2 минуты =========
@dp.message(F.text == "📌 План на 2 минуты")
async def plan_from_menu(message: Message):
    await send_plan(message)

@dp.callback_query(F.data == "step_plan")
async def plan_from_inline(cb: CallbackQuery):
    await cb.answer()
    await send_plan(cb.message)

def kb_plan_choices():
    kb = InlineKeyboardBuilder()
    kb.button(text="🥤 Вода / умыться", callback_data="p_water")
    kb.button(text="🪟 Окно + 10 выдохов", callback_data="p_window")
    kb.button(text="💬 Написать 1 сообщение", callback_data="p_message")
    kb.button(text="📝 3 факта → 1 шаг", callback_data="p_facts")
    kb.button(text="⏲ Таймер 2 мин и делаю", callback_data="p_timer")
    kb.adjust(1)
    return kb.as_markup()

async def send_plan(target: Message):
    await target.answer(
        "📌 **Шаг 4: План на 2 минуты**\n\n"
        "Выбери одно маленькое действие — прямо сейчас:",
        parse_mode="Markdown",
        reply_markup=kb_plan_choices()
    )

@dp.callback_query(F.data.startswith("p_"))
async def plan_choice(cb: CallbackQuery):
    await cb.answer()
    mapping = {
        "p_water": "Супер. Выпей воды или умойся. Это быстро снижает напряжение тела.",
        "p_window": "Ок. Открой окно и сделай 10 медленных выдохов (выдох чуть длиннее вдоха).",
        "p_message": "Напиши 1 сообщение: «мне сейчас тревожно, можно 2 минуты поговорить?»",
        "p_facts": "Запиши: 3 факта (что точно известно) → 1 следующий шаг (самый маленький).",
        "p_timer": "Поставь таймер на 2 минуты и сделай самое простое действие из списка.",
    }
    await cb.message.answer(mapping.get(cb.data, "Ок."))

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Готово", callback_data="done_ok")
    kb.button(text="🔁 Ещё один шаг", callback_data="more_step")
    kb.adjust(2)
    await cb.message.answer("Готово? ✅", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "done_ok")
async def done_ok(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("Класс. Даже маленький шаг — уже победа 💛", reply_markup=after_step_kb())


# ========= ШАГ 2: Вопросы (то, что ты выбрала) =========
@dp.message(F.text == "🧠 Разобрать тревогу")
async def questions_from_menu(message: Message, state: FSMContext):
    await start_questions(message, state)

@dp.callback_query(F.data == "step_questions")
async def questions_from_inline(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await start_questions(cb.message, state)

async def start_questions(target: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AnxietyQuestions.q1)
    await target.answer(
        "🧠 **Шаг 2: Вопросы, чтобы разобраться с тревогой**\n\n"
        "1️⃣ Что сейчас пугает больше всего? (в 1 фразе)",
        parse_mode="Markdown"
    )

@dp.message(AnxietyQuestions.q1)
async def q1(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Можно одной короткой фразой: что пугает больше всего?")
        return
    await state.update_data(q1=text)
    await state.set_state(AnxietyQuestions.q2)
    await message.answer(
        "2️⃣ Это больше про *сейчас* или про *будущее*?",
        parse_mode="Markdown",
        reply_markup=kb_now_future()
    )

@dp.callback_query(AnxietyQuestions.q2, F.data.in_({"aq_now", "aq_future"}))
async def q2(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    val = "про сейчас" if cb.data == "aq_now" else "про будущее"
    await state.update_data(q2=val)
    await state.set_state(AnxietyQuestions.q3)
    await cb.message.answer(
        "4️⃣ Что ты можешь сделать в ближайшие 10 минут, чтобы стало хотя бы на 5% легче?\n"
        "Можно совсем маленький шаг."
    )

@dp.message(AnxietyQuestions.q3)
async def q3(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Ок. А что реально сделать за 10 минут, даже на 5% легче?")
        return
    await state.update_data(q3=text)
    await state.set_state(AnxietyQuestions.q4)
    await message.answer(
        "5️⃣ Представь, что подруга написала тебе это же. Что бы ты сказала ей?\n"
        "1–2 предложения, по-доброму."
    )

@dp.message(AnxietyQuestions.q4)
async def q4(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Можно одной фразой — как поддержала бы подругу?")
        return

    await state.update_data(q4=text)
    data = await state.get_data()

    summary = (
        "✅ **Готово. Короткое резюме:**\n\n"
        f"😰 *Что пугает:* {data.get('q1','')}\n"
        f"🧭 *Это больше:* {data.get('q2','')}\n"
        f"👣 *Шаг на 10 минут:* {data.get('q3','')}\n"
        f"💛 *Поддержка себе:* {data.get('q4','')}\n\n"
        "Хочешь закрепить состояние ещё одним шагом?"
    )

    await message.answer(summary, parse_mode="Markdown", reply_markup=after_step_kb())
    await message.answer("Выбери следующий шаг:", reply_markup=choose_next_step_kb())
    await state.clear()


# ========= Мини-вебсервер для Render (порт) =========
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
