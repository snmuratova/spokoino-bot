import asyncio
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Простая "настройка темы" в памяти (на бесплатном Render может сбрасываться при перезапуске)
USER_THEME = {}  # user_id -> "day" | "night"


# ========= ВИЗУАЛ / UX =========

def theme(user_id: int) -> str:
    return USER_THEME.get(user_id, "night")  # по умолчанию ночной

def t(user_id: int, day_text: str, night_text: str) -> str:
    return night_text if theme(user_id) == "night" else day_text

def progress_bar(step: int, total: int = 4) -> str:
    filled = "▓" * step
    empty = "░" * (total - step)
    return f"{filled}{empty}"

async def typing(chat_id: int, seconds: float = 0.8):
    # Эффект «печатает…»
    try:
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(seconds)
    except Exception:
        pass

async def say(message_obj: Message, text: str, reply_markup=None, delay: float = 0.8, parse_mode="Markdown"):
    await typing(message_obj.chat.id, delay)
    await message_obj.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)

async def edit(cb: CallbackQuery, text: str, reply_markup=None, parse_mode="Markdown"):
    await cb.answer()
    try:
        await cb.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        # если Telegram не даёт редактировать, шлём новым сообщением
        await say(cb.message, text, reply_markup=reply_markup, delay=0.2, parse_mode=parse_mode)


# ========= КНОПКИ / МЕНЮ =========

def kb_main():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Шаг 1 — Дыхание", callback_data="step:breath")
    kb.button(text="🧠 Шаг 2 — Разобрать тревогу", callback_data="step:questions")
    kb.button(text="🪨 Шаг 3 — Заземление", callback_data="step:ground")
    kb.button(text="📌 Шаг 4 — План на 2 минуты", callback_data="step:plan")
    kb.button(text="⚙️ Настройки", callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def kb_nav():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Ещё шаг", callback_data="more")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()

def kb_settings(user_id: int):
    kb = InlineKeyboardBuilder()
    cur = theme(user_id)
    toggle_text = "🌙 Ночной режим: ВКЛ" if cur == "night" else "☀️ Дневной режим: ВКЛ"
    kb.button(text=toggle_text, callback_data="theme:toggle")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()

def kb_now_future():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Это про сейчас", callback_data="aq:now")
    kb.button(text="🔮 Это про будущее", callback_data="aq:future")
    kb.adjust(1)
    return kb.as_markup()

def kb_plan():
    kb = InlineKeyboardBuilder()
    kb.button(text="🥤 Вода / умыться", callback_data="plan:water")
    kb.button(text="🌬 Вдох свежего воздуха", callback_data="plan:air")
    kb.button(text="💬 Написать близкому", callback_data="plan:message")
    kb.button(text="📝 3 факта → 1 шаг", callback_data="plan:facts")
    kb.button(text="⏲ Таймер 2 минуты", callback_data="plan:timer")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


# ========= FSM (вопросы) =========

class AnxietyFlow(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()


# ========= START / MENU =========

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    title = t(uid, "💙 *Навигатор спокойствия*", "🌙 *Навигатор спокойствия*")
    intro = t(
        uid,
        "Если тревожно — это нормально.\nДавай снизим напряжение шаг за шагом.",
        "Если тревожно — ты не одна.\nДавай бережно снизим напряжение шаг за шагом."
    )

    await say(
        message,
        f"{title}\n\n{intro}\n\nВыбери шаг:",
        reply_markup=kb_main(),
        delay=0.6
    )

@dp.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    title = t(uid, "💙 *Навигатор спокойствия*", "🌙 *Навигатор спокойствия*")
    await edit(cb, f"{title}\n\nВыбери шаг:", reply_markup=kb_main())

@dp.callback_query(F.data == "more")
async def cb_more(cb: CallbackQuery):
    uid = cb.from_user.id
    msg = t(uid, "Продолжим. Выбери следующий шаг:", "Продолжим 💛\nВыбери следующий шаг:")
    await edit(cb, msg, reply_markup=kb_main())

@dp.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    text = (
        "⚙️ *Настройки*\n\n"
        "Можно переключить стиль.\n"
        "Ночной — спокойнее и мягче.\n"
        "Дневной — чуть бодрее и короче."
    )
    await edit(cb, text, reply_markup=kb_settings(uid))

@dp.callback_query(F.data == "theme:toggle")
async def cb_theme_toggle(cb: CallbackQuery):
    uid = cb.from_user.id
    USER_THEME[uid] = "day" if theme(uid) == "night" else "night"
    cur = t(uid, "☀️ Включён дневной стиль.", "🌙 Включён ночной стиль.")
    await edit(cb, f"{cur}\n\nВыбери шаг:", reply_markup=kb_main())


# ========= ШАГ 1: ДЫХАНИЕ =========

@dp.callback_query(F.data == "step:breath")
async def cb_breath(cb: CallbackQuery):
    uid = cb.from_user.id
    header = f"🌬 *Шаг 1 из 4*  `{progress_bar(1)}`"
    text = (
        f"{header}\n\n"
        "Когда тревога нарастает, телу важно замедлиться.\n\n"
        "*Физиологический вздох:*\n"
        "• вдох носом\n"
        "• маленький довдох\n"
        "• длинный выдох ртом\n\n"
        "Повтори **3–5 раз**.\n\n"
        "Если хочется ровнее:\n"
        "*4–6*: вдох на 4… выдох на 6… **8 циклов**.\n\n"
        + t(uid, "Ты справляешься 💛", "Я рядом 💛")
    )
    await edit(cb, text, reply_markup=kb_nav())


# ========= ШАГ 2: ВОПРОСЫ (FSM) =========

@dp.callback_query(F.data == "step:questions")
async def cb_questions_start(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.clear()
    await state.set_state(AnxietyFlow.q1)

    header = f"🧠 *Шаг 2 из 4*  `{progress_bar(2)}`"
    text = (
        f"{header}\n\n"
        + t(uid, "Давай аккуратно разберём тревогу.", "Я понимаю тебя.\nДавай аккуратно разберём тревогу.")
        + "\n\n"
        "1️⃣ *Что сейчас напрягает больше всего?*\n"
        "_В 1 фразе._"
    )
    await edit(cb, text, reply_markup=None)

@dp.message(AnxietyFlow.q1)
async def q1(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной короткой фразой: что пугает больше всего?", delay=0.4)
        return

    await state.update_data(q1=txt)
    await state.set_state(AnxietyFlow.q2)
    await say(message, "2️⃣ Это больше про *сейчас* или про *будущее*?", reply_markup=kb_now_future(), delay=0.6)

@dp.callback_query(AnxietyFlow.q2, F.data.in_({"aq:now", "aq:future"}))
async def q2(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    val = "про сейчас" if cb.data == "aq:now" else "про будущее"
    await state.update_data(q2=val)
    await state.set_state(AnxietyFlow.q3)
    await say(
        cb.message,
        "3️⃣ Что ты можешь сделать в ближайшие 10 минут,\n"
        "чтобы стало хотя бы на *5% легче*?\n"
        "Пусть это будет маленький шаг.",
        delay=0.6
    )

@dp.message(AnxietyFlow.q3)
async def q3(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно совсем маленький шаг. Что реально сделать за 10 минут?", delay=0.4)
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q4)
    await say(
        message,
        "4️⃣ Представь, что *друг или близкий человек* написал тебе это же.\n"
        "Что бы ты ответил или ответила?\n"
        "_1–2 предложения. По-доброму._",
        delay=0.7
    )

@dp.message(AnxietyFlow.q4)
async def q4(message: Message, state: FSMContext):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной фразой — как поддержал или поддержала бы близкого человека?", delay=0.4)
        return

    data = await state.get_data()
    await state.clear()

    header = f"✨ *Итог шага 2*  `{progress_bar(2)}`"
    summary = (
        f"{header}\n\n"
        f"😰 *Что пугает:* {data.get('q1','')}\n"
        f"🧭 *Это больше:* {data.get('q2','')}\n"
        f"👣 *Маленький шаг:* {data.get('q3','')}\n"
        f"💛 *Поддержка себе:* {txt}\n\n"
        + t(uid, "Ты сделала или сделал важное. Продолжим?", "Ты уже помогла/помог себе. Давай закрепим?")
    )
    await say(message, summary, reply_markup=kb_nav(), delay=0.9)


# ========= ШАГ 3: ЗАЗЕМЛЕНИЕ (медленное) =========

@dp.callback_query(F.data == "step:ground")
async def cb_ground(cb: CallbackQuery):
    uid = cb.from_user.id
    header = f"🪨 *Шаг 3 из 4*  `{progress_bar(3)}`"
    text = (
        f"{header}\n\n"
        "Немного замедлимся.\n"
        + t(uid, "Сделай спокойный вдох… и выдох…", "Сделай спокойный вдох…\nи медленный выдох…")
        + "\n\n"
        "👀 **5 — что ты видишь**\n"
        "Оглянись и найди 5 вещей.\n\n"
        "🤍 **4 — что ты чувствуешь физически**\n"
        "Удобно ли сидишь/стоишь?\n"
        "Тепло или прохладно?\n"
        "Из какой ткани твоя одежда: мягкая, гладкая, плотная?\n\n"
        "👂 **3 — что ты слышишь**\n"
        "Найди 3 звука вокруг.\n\n"
        "🌬 **2 — запахи**\n"
        "Есть ли запах? Если нет — просто отметь: «нет запаха».\n\n"
        "👅 **1 — вкус**\n"
        "Если вкуса нет — представь вкус свежих ягод или фруктов.\n"
        "Сладкий? Кисловатый?\n\n"
        "Сделай ещё один вдох… и длинный выдох.\n\n"
        + t(uid, "Ты здесь. Ты в этом моменте 💛", "Ты здесь. Волна тревоги постепенно спадает 💛")
    )
    await edit(cb, text, reply_markup=kb_nav())


# ========= ШАГ 4: ПЛАН НА 2 МИНУТЫ =========

@dp.callback_query(F.data == "step:plan")
async def cb_plan(cb: CallbackQuery):
    header = f"📌 *Шаг 4 из 4*  `{progress_bar(4)}`"
    text = (
        f"{header}\n\n"
        "Не нужно решать всё сразу.\n"
        "Выбери **один** маленький шаг — этого достаточно.\n\n"
        "Нажми на вариант ниже:"
    )
    await edit(cb, text, reply_markup=kb_plan())

@dp.callback_query(F.data.startswith("plan:"))
async def cb_plan_choice(cb: CallbackQuery):
    await cb.answer()
    key = cb.data.split(":", 1)[1]

    if key == "water":
        msg = "🥤 Выпей воды или умойся.\nЭто простое действие помогает телу почувствовать опору."
    elif key == "air":
        msg = "🌬 Сделай глубокий вдох свежего воздуха…\nи длинный выдох.\nПовтори 3 раза."
    elif key == "message":
        msg = "💬 Не обязательно справляться с этим в одиночку.\nНапиши: «мне сейчас тревожно, можно 2 минуты поговорить?»"
    elif key == "facts":
        msg = (
            "📝 Давай вернём опору.\n\n"
            "1) Запиши **3 факта**, которые точно известны (без «а вдруг»).\n"
            "2) Выбери **1 самый маленький шаг** на ближайшие 10 минут.\n\n"
            "Не больше одного шага. Этого достаточно 💛"
        )
    else:  # timer
        msg = "⏲ Поставь таймер на 2 минуты.\nИ сделай самое простое действие из того, что выбрала."

    await say(cb.message, msg, delay=0.5, reply_markup=kb_nav())


# ========= WEB SERVER (Render порт) =========

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

    print(f"Web server started on port {port}", flush=True)

async def main():
    # Важно: сначала поднимаем порт, чтобы Render не таймаутился
    await start_web_server()
    print("Starting bot polling...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
