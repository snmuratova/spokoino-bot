import asyncio
import os
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramConflictError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ==========================
# CONFIG
# ==========================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

PORT = int(os.getenv("PORT", "10000"))

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# На бесплатном Render может сбрасываться при перезапуске
USER_THEME: dict[int, str] = {}  # "day" | "night"


# ==========================
# PATHS (AUDIO)
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FOREST_MP3 = os.path.join(BASE_DIR, "assets", "audio", "forest.mp3")
FOREST_MP3_MP3 = os.path.join(BASE_DIR, "assets", "audio", "forest.mp3.mp3")


def get_forest_audio_path() -> str | None:
    """Поддерживаем оба варианта имени файла: forest.mp3 и forest.mp3.mp3"""
    if os.path.exists(FOREST_MP3):
        return FOREST_MP3
    if os.path.exists(FOREST_MP3_MP3):
        return FOREST_MP3_MP3
    return None


# ==========================
# UX HELPERS
# ==========================
def theme(user_id: int) -> str:
    return USER_THEME.get(user_id, "night")


def t(user_id: int, day: str, night: str) -> str:
    return night if theme(user_id) == "night" else day


def progress_bar(step: int, total: int = 4) -> str:
    filled = "▓" * step
    empty = "░" * (total - step)
    return f"{filled}{empty}"


async def typing(chat_id: int, seconds: float = 0.12) -> None:
    try:
        await bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(seconds)
    except Exception:
        pass


async def say(
    msg: Message,
    text: str,
    *,
    parse_mode: str | None = "Markdown",
    reply_markup=None,
    delay: float = 0.12,
) -> None:
    await typing(msg.chat.id, delay)
    await msg.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)


async def edit(
    cb: CallbackQuery,
    text: str,
    *,
    parse_mode: str | None = "Markdown",
    reply_markup=None,
) -> None:
    await cb.answer()
    try:
        await cb.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        await say(cb.message, text, parse_mode=parse_mode, reply_markup=reply_markup, delay=0.05)


# ==========================
# KEYBOARDS
# ==========================
def kb_main():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Оценить тревожность", callback_data="anxiety:scale")
    kb.button(text="🌬 Шаг 1 — Дыхание", callback_data="step:breath")
    kb.button(text="🧠 Шаг 2 — Разобрать тревогу", callback_data="step:questions")
    kb.button(text="🪨 Шаг 3 — Заземление", callback_data="step:ground")
    kb.button(text="📌 Шаг 4 — План на 2 минуты", callback_data="step:plan")
    kb.button(text="🎧 Звук леса", callback_data="sound:forest")
    kb.button(text="⚙️ Настройки", callback_data="settings")
    kb.adjust(1, 1, 1, 1, 1, 1)
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
    toggle_text = "🌙 Ночной стиль: ВКЛ" if cur == "night" else "☀️ Дневной стиль: ВКЛ"
    kb.button(text=toggle_text, callback_data="theme:toggle")
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_now_future():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Это про сейчас", callback_data="aq:now")
    kb.button(text="🔮 Это про будущее", callback_data="aq:future")
    kb.adjust(1, 1)
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

    
def kb_anxiety_scale():
    kb = InlineKeyboardBuilder()
    for i in range(0, 11):
        kb.button(text=str(i), callback_data=f"anxiety:{i}")
    kb.adjust(6, 5)  # 0–5 в строке, 6–10 ниже
    kb.button(text="🏠 Меню", callback_data="menu")
    kb.adjust(6, 5, 1)
    return kb.as_markup()


# ==========================
# FSM: QUESTIONS FLOW
# ==========================
class AnxietyFlow(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()


# ==========================
# START / MENU
# ==========================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    title = t(uid, "💙 *Навигатор спокойствия*", "🌙 *Навигатор спокойствия*")
    intro = t(
        uid,
        "Если тревожно — это нормально.\nДавай снизим напряжение шаг за шагом.",
        "Если тревожно — ты не одна и не один.\nДавай бережно снизим напряжение шаг за шагом.",
    )

    await say(message, f"{title}\n\n{intro}\n\nВыбери шаг:", reply_markup=kb_main(), delay=0.2)


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
        "Можно переключить стиль сообщений:\n"
        "• Ночной — мягче и спокойнее\n"
        "• Дневной — короче и бодрее"
    )
    await edit(cb, text, reply_markup=kb_settings(uid))


@dp.callback_query(F.data == "theme:toggle")
async def cb_theme_toggle(cb: CallbackQuery):
    uid = cb.from_user.id
    USER_THEME[uid] = "day" if theme(uid) == "night" else "night"
    cur = t(uid, "☀️ Включён дневной стиль.", "🌙 Включён ночной стиль.")
    await edit(cb, f"{cur}\n\nВыбери шаг:", reply_markup=kb_main())


# ==========================
# SOUND: FOREST
# ==========================
@dp.callback_query(F.data == "sound:forest")
async def cb_sound_forest(cb: CallbackQuery):
    await cb.answer()

    path = get_forest_audio_path()
    if not path:
        await cb.message.answer(
            "Не нашла файл звука 😕\n"
            "Проверь, что в репозитории есть:\n"
            "`assets/audio/forest.mp3` (или `forest.mp3.mp3`).",
            parse_mode="Markdown",
        )
        return

    await cb.message.answer(
        "🎧 Включаю лесной шум.\n"
        "Можно сделать 3 цикла: вдох 4 — выдох 6."
    )
    await cb.message.answer_audio(
        audio=FSInputFile(path),
        caption="🌲 Лесной шум",
    )


# ==========================
# STEP 1: BREATH
# ==========================
@dp.callback_query(F.data == "step:breath")
async def cb_breath(cb: CallbackQuery):
    uid = cb.from_user.id
    header = f"🌬 *Шаг 1 из 4*  `{progress_bar(1)}`"
    text = (
        f"{header}\n\n"
        "Когда тревога поднимается, телу помогает короткий «сигнал безопасности».\n\n"
        "*Физиологический вздох (самый быстрый):*\n"
        "• вдох носом\n"
        "• маленький довдох (как «добавить воздуха»)\n"
        "• длинный выдох ртом\n\n"
        "Повтори **3–5 раз**.\n\n"
        "Если хочется более ровно:\n"
        "*4–6*: вдох на 4… выдох на 6… **8 циклов**.\n\n"
        + t(uid, "Ты справляешься 💛", "Я рядом 💛")
    )
    await edit(cb, text, reply_markup=kb_nav())


# ==========================
# STEP 2: QUESTIONS (FSM)
# ==========================
@dp.callback_query(F.data == "step:questions")
async def cb_questions_start(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    await state.clear()
    await state.set_state(AnxietyFlow.q1)

    header = f"🧠 *Шаг 2 из 4*  `{progress_bar(2)}`"
    text = (
        f"{header}\n\n"
        + t(uid, "Давай разберём тревогу по шагам.", "Я понимаю тебя.\nДавай разберём тревогу по шагам.")
        + "\n\n"
        "1️⃣ *Что сейчас пугает или напрягает больше всего?*\n"
        "_В 1 фразе._"
    )
    await edit(cb, text, reply_markup=None)


@dp.message(AnxietyFlow.q1)
async def q1(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной короткой фразой — что сейчас пугает больше всего?", delay=0.05)
        return

    await state.update_data(q1=txt)
    await state.set_state(AnxietyFlow.q2)
    await say(message, "2️⃣ Это больше про *сейчас* или про *будущее*?", reply_markup=kb_now_future(), delay=0.12)


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
        delay=0.12,
    )


@dp.message(AnxietyFlow.q3)
async def q3(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно совсем маленький шаг. Что реально сделать за 10 минут?", delay=0.05)
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q4)
    await say(
        message,
        "4️⃣ Представь, что *друг или близкий человек* написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "_1–2 предложения. По-доброму._",
        delay=0.12,
    )


@dp.message(AnxietyFlow.q4)
async def q4(message: Message, state: FSMContext):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной фразой — как поддержал(а) бы близкого человека?", delay=0.05)
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
        + t(uid, "Ты уже сделала/сделал важное. Продолжим?", "Ты уже помог(ла) себе. Давай закрепим?")
    )
    await say(message, summary, reply_markup=kb_nav(), delay=0.12)


# ==========================
# STEP 3: GROUNDING (SLOW)
# ==========================
@dp.callback_query(F.data == "step:ground")
async def cb_ground(cb: CallbackQuery):
    uid = cb.from_user.id
    header = f"🪨 *Шаг 3 из 4*  `{progress_bar(3)}`"
    text = (
        f"{header}\n\n"
        "Сейчас мы возвращаем внимание в реальность, шаг за шагом.\n\n"
        "Сделай спокойный вдох…\n"
        "и медленный выдох…\n\n"
        "👀 **5 — что ты видишь**\n"
        "Оглянись и найди 5 вещей. Можно назвать их про себя.\n\n"
        "🤍 **4 — что ты чувствуешь физически**\n"
        "Удобно ли ты сидишь или стоишь?\n"
        "Тепло тебе или прохладно?\n"
        "Из какого материала твоя одежда — мягкая, гладкая, плотная?\n\n"
        "👂 **3 — что ты слышишь**\n"
        "Найди 3 звука вокруг. Даже самые тихие.\n\n"
        "🌬 **2 — запахи**\n"
        "Есть ли запах? Если нет — просто отметь: «сейчас нет запаха».\n\n"
        "👅 **1 — вкус**\n"
        "Если вкуса нет — представь вкус свежих ягод или фруктов.\n"
        "Сладкий? Кисловатый? Прохладный?\n\n"
        "И ещё раз: вдох… и длинный выдох…\n\n"
        + t(uid, "Ты здесь. Ты в этом моменте 💛", "Ты здесь. Волна тревоги постепенно спадает 💛")
    )
    await edit(cb, text, reply_markup=kb_nav())


# ==========================
# STEP 4: PLAN (2 MIN)
# ==========================
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
    uid = cb.from_user.id
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
            "**1) 3 факта (что точно известно):**\n"
            "Без «а вдруг» — только то, что реально подтверждено.\n\n"
            "**2) 1 следующий шаг (самый маленький):**\n"
            "Что ты можешь сделать в ближайшие 10 минут.\n\n"
            + t(uid, "Этого достаточно 💛", "Одного шага достаточно 💛")
        )
    else:  # timer
        msg = "⏲ Поставь таймер на 2 минуты.\nИ сделай самое простое действие из того, что выбрала."

    await say(cb.message, msg, delay=0.12, reply_markup=kb_nav())


# ==========================
# WEB SERVER (for Render port)
# ==========================
async def handle_root(request):
    return web.Response(text="OK")


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()


# ==========================
# POLLING (safe loop)
# ==========================
async def run_polling_forever() -> None:
    """
    Если BOT_TOKEN запущен где-то ещё, Telegram даст Conflict.
    Мы не падаем — ждём и пробуем снова.
    """
    backoff = 2
    while True:
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            backoff = 2
        except TelegramConflictError:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception:
            await asyncio.sleep(3)


async def main():
    await start_web_server()
    await run_polling_forever()


if __name__ == "__main__":
    asyncio.run(main())
