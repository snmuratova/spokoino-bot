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


# ========= Меню =========
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🌬 Дыхание")
    kb.button(text="🧠 Разобрать тревогу")
    kb.button(text="🪨 Заземление (медленно)")
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


# ========= Вопросы =========
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
        "Привет 💛\n\n"
        "Если тревожно — ты не одна.\n"
        "Давай снизим напряжение шаг за шагом.\n\n"
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
    await cb.message.answer(
        "Хорошо. Выберем следующий маленький шаг 💛",
        reply_markup=choose_next_step_kb()
    )


# ========= ДЫХАНИЕ =========
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
        "Когда тревога высокая, телу важно помочь замедлиться.\n\n"
        "*Физиологический вздох:*\n"
        "1) Вдох носом\n"
        "2) Маленький довдох\n"
        "3) Длинный выдох ртом\n\n"
        "Повтори 3–5 раз.\n\n"
        "Или вариант 4–6:\n"
        "Вдох на 4… выдох на 6…\n"
        "Сделай 8 циклов.\n\n"
        "Ты уже делаешь важное 💛",
        parse_mode="Markdown",
        reply_markup=after_step_kb()
    )


# ========= ЗАЗЕМЛЕНИЕ (медитация) =========
@dp.message(F.text == "🪨 Заземление (медленно)")
async def ground_from_menu(message: Message):
    await send_ground_slow(message)


@dp.callback_query(F.data == "step_ground")
async def ground_from_inline(cb: CallbackQuery):
    await cb.answer()
    await send_ground_slow(cb.message)


async def send_ground_slow(target: Message):
    await target.answer(
        "🪨 **Заземление**\n\n"
        "Немного замедлимся.\n"
        "Я понимаю тебя.\n"
        "Тревога может ощущаться очень сильной.\n\n"
        "Сделай спокойный вдох…\n"
        "и медленный выдох…\n\n"
        "👀 5 — Посмотри вокруг.\n"
        "Назови 5 вещей, которые ты видишь.\n\n"
        "🤍 4 — Обрати внимание на ощущения.\n"
        "Удобно ли ты сидишь или стоишь?\n"
        "Тепло тебе или прохладно?\n"
        "Почувствуй ткань одежды.\n\n"
        "👂 3 — Прислушайся.\n"
        "Какие 3 звука есть вокруг?\n\n"
        "🌬 2 — Есть ли запахи?\n"
        "Если нет — просто отметь это.\n\n"
        "👅 1 — Обрати внимание на вкус.\n"
        "Если вкуса нет — представь вкус свежих ягод или фруктов.\n"
        "Какой он? Сладкий? Кисловатый?\n\n"
        "Сделай ещё один медленный вдох…\n"
        "и длинный выдох.\n\n"
        "Ты здесь.\n"
        "Ты в этом моменте.\n"
        "И волна тревоги постепенно спадает.\n\n"
        "Я рядом 💛",
        parse_mode="Markdown",
        reply_markup=after_step_kb()
    )


# ========= ПЛАН 2 МИН =========
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
    kb.button(text="🌬 Глубокий вдох свежего воздуха", callback_data="p_air")
    kb.button(text="💬 Написать 1 сообщение", callback_data="p_message")
    kb.button(text="📝 3 факта → 1 шаг", callback_data="p_facts")
    kb.button(text="⏲ Таймер 2 мин", callback_data="p_timer")
    kb.adjust(1)
    return kb.as_markup()


async def send_plan(target: Message):
    await target.answer(
        "📌 **План на 2 минуты**\n\n"
        "Не нужно решать всё сразу.\n"
        "Выбери один маленький шаг:",
        parse_mode="Markdown",
        reply_markup=kb_plan_choices()
    )


@dp.callback_query(F.data.startswith("p_"))
async def plan_choice(cb: CallbackQuery):
    await cb.answer()

    mapping = {
        "p_water": "Выпей воды или умойся. Это помогает телу почувствовать опору.",
        "p_air": "Сделай глубокий вдох свежего воздуха. Медленно. И длинный выдох.",
        "p_message": "Напиши: «мне сейчас тревожно, можно 2 минуты поговорить?»",
        "p_facts": (
            "Напиши 3 факта, которые точно известны.\n"
            "Потом выбери 1 самый маленький шаг на ближайшие 10 минут.\n"
            "Только один."
        ),
        "p_timer": "Поставь таймер на 2 минуты и сделай самое простое действие.",
    }

    await cb.message.answer(mapping.get(cb.data, "Ок."))

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Готово", callback_data="done_ok")
    kb.button(text="🔁 Ещё шаг", callback_data="more_step")
    kb.adjust(2)
    await cb.message.answer("Готово? 💛", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "done_ok")
async def done_ok(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(
        "Даже маленький шаг — уже забота о себе 💛",
        reply_markup=after_step_kb()
    )


# ========= Веб-сервер =========
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
