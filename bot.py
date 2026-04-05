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

# Твой Telegram ID — статистика доступна только тебе
ADMIN_ID = 862407613

# ==========================
# BOT / DISPATCHER
# ==========================
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================
# USER PREFERENCES (memory)
# ==========================
USER_THEME: dict[int, str] = {}      # "day" | "night"
LAST_ANXIETY: dict[int, int] = {}    # последний уровень тревоги 0..10

# ==========================
# STATS (memory)
# ==========================
STATS = {
    "start": 0,
    "menu": 0,
    "settings": 0,
    "theme_toggle": 0,

    "anxiety_open": 0,
    "anxiety_set": 0,

    "step_breath": 0,
    "step_questions": 0,
    "step_ground": 0,
    "step_plan": 0,

    "sound_forest": 0,

    "about_creators": 0,
    "creator_svetlana": 0,
    "creator_mikhail": 0,
    "creator_sofya": 0,
}
ANXIETY_DISTRIBUTION = {i: 0 for i in range(11)}
USERS_SEEN: set[int] = set()

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


def praise(uid: int) -> str:
    return t(
        uid,
        "Ты молодец. Правда. Даже один шаг — уже движение к спокойствию.",
        "Ты молодец. Правда.\nДаже один шаг — это опора, которую ты себе создаёшь.",
    )


# ==========================
# KEYBOARDS
# ==========================
def kb_start(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Оценить состояние", callback_data="start:anxiety")
    kb.button(text="💚 Получить поддержку", callback_data="start:support")
    kb.button(text="👩‍💻 О создателях", callback_data="about:creators")

    if user_id == ADMIN_ID:
        kb.button(text="📈 Статистика", callback_data="stats")

    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def kb_support():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡ Быстрая помощь", callback_data="support:fast")
    kb.button(text="🌿 Спокойная поддержка", callback_data="support:slow")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def kb_steps():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Дыхание", callback_data="step:breath")
    kb.button(text="💭 Разобрать тревогу", callback_data="step:questions")
    kb.button(text="🌳 Заземление", callback_data="step:ground")
    kb.button(text="📌 План на 2 минуты", callback_data="step:plan")
    kb.button(text="🎧 Звук леса", callback_data="sound:forest")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def kb_after_step():
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ Следующий шаг", callback_data="more")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_settings(user_id: int):
    kb = InlineKeyboardBuilder()
    cur = theme(user_id)
    toggle_text = "🌙 Ночной стиль: ВКЛ" if cur == "night" else "☀️ Дневной стиль: ВКЛ"
    kb.button(text=toggle_text, callback_data="theme:toggle")
    kb.button(text="🏠 В начало", callback_data="menu")
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
    kb.button(text="💧 Вода / умыться", callback_data="plan:water")
    kb.button(text="🌬 Вдох свежего воздуха", callback_data="plan:air")
    kb.button(text="💬 Написать близкому", callback_data="plan:message")
    kb.button(text="📝 3 факта → 1 шаг", callback_data="plan:facts")
    kb.button(text="⏲ Таймер 2 минуты", callback_data="plan:timer")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def kb_anxiety_scale():
    kb = InlineKeyboardBuilder()
    for i in range(0, 11):
        kb.button(text=str(i), callback_data=f"anxiety:{i}")
    kb.adjust(6, 5)
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(6, 5, 1)
    return kb.as_markup()


def kb_recommend(level: int):
    kb = InlineKeyboardBuilder()

    if level >= 7:
        kb.button(text="🌬 Сделать дыхание сейчас", callback_data="step:breath")
        kb.button(text="🎧 Включить звук леса", callback_data="sound:forest")
        kb.button(text="🥤 Выпить воды", callback_data="plan:water")
        kb.button(text="🌳 Заземление", callback_data="step:ground")
        kb.adjust(1, 1, 1, 1)

    elif level >= 4:
        kb.button(text="🌬 Дыхание", callback_data="step:breath")
        kb.button(text="💭 Разобрать тревогу", callback_data="step:questions")
        kb.button(text="🌳 Заземление", callback_data="step:ground")
        kb.button(text="📌 План на 2 минуты", callback_data="step:plan")
        kb.adjust(1, 1, 1, 1)

    else:
        kb.button(text="🌳 Заземление", callback_data="step:ground")
        kb.button(text="🎧 Звук леса", callback_data="sound:forest")
        kb.button(text="📌 План на 2 минуты", callback_data="step:plan")
        kb.adjust(1, 1, 1)

    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def kb_creators():
    kb = InlineKeyboardBuilder()
    kb.button(text="Светлана", callback_data="creator:svetlana")
    kb.button(text="Михаил", callback_data="creator:mikhail")
    kb.button(text="Софья", callback_data="creator:sofya")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


# ==========================
# FSM: QUESTIONS FLOW
# ==========================
class AnxietyFlow(StatesGroup):
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
    q5 = State()


# ==========================
# START / MENU
# ==========================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    STATS["start"] += 1
    USERS_SEEN.add(message.from_user.id)

    text = (
        "🌿 *Добро пожаловать*\n\n"
        "Это бесплатное пространство поддержки в моменты тревоги, усталости и внутреннего напряжения.\n\n"
        "Здесь не нужно справляться со всем сразу.\n"
        "Можно начать с одного шага — и этого уже достаточно.\n\n"
        "Я рядом.\n\n"
        "Выбери, что тебе сейчас ближе 👇"
    )

    await say(message, text, reply_markup=kb_start(message.from_user.id), delay=0.12)


@dp.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    STATS["menu"] += 1
    USERS_SEEN.add(cb.from_user.id)

    text = (
        "🌿 *Пространство спокойствия*\n\n"
        "Можно вернуться к себе в любой момент.\n\n"
        "Выбери, что сейчас важно 👇"
    )

    await edit(cb, text, reply_markup=kb_start(cb.from_user.id))


@dp.callback_query(F.data == "more")
async def cb_more(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    msg = t(uid, "Продолжим. Выбери следующий шаг:", "Продолжим 💛\nВыбери следующий шаг:")
    await edit(cb, msg, reply_markup=kb_main(uid))


@dp.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    STATS["settings"] += 1
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
    USERS_SEEN.add(uid)
    STATS["theme_toggle"] += 1
    USER_THEME[uid] = "day" if theme(uid) == "night" else "night"
    cur = t(uid, "☀️ Включён дневной стиль.", "🌙 Включён ночной стиль.")
    await edit(cb, f"{cur}\n\nВыбери, что тебе сейчас ближе 👇", reply_markup=kb_start(uid))


@dp.callback_query(F.data == "start:anxiety")
async def cb_start_anxiety(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["anxiety_open"] += 1
    text = (
        "📊 Почувствуй, как ты сейчас.\n\n"
        "Оцени своё состояние от 0 до 10:\n\n"
        "0 — спокойно\n"
        "5 — заметное напряжение\n"
        "10 — очень сильная тревога\n\n"
        "Можно не думать долго — выбери число, которое ощущается ближе всего."
    )
    await edit(cb, text, reply_markup=kb_anxiety_scale())


@dp.callback_query(F.data == "start:support")
async def cb_start_support(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    text = (
        "💚 Я рядом.\n\n"
        "Давай выберем формат поддержки:\n\n"
        "⚡ Быстрая помощь — если сейчас очень тревожно\n"
        "🌿 Спокойная поддержка — если хочется пройти путь шаг за шагом"
    )
    await edit(cb, text, reply_markup=kb_support())


@dp.callback_query(F.data == "support:fast")
async def cb_support_fast(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    text = (
        "Сейчас не нужно разбираться.\n"
        "Давай просто поможем телу.\n\n"
        "Выбери, с чего начать:"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Дыхание", callback_data="step:breath")
    kb.button(text="🎧 Звук леса", callback_data="sound:forest")
    kb.button(text="💧 Вода", callback_data="plan:water")
    kb.button(text="🌳 Заземление", callback_data="step:ground")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1)

    await edit(cb, text, reply_markup=kb.as_markup())


@dp.callback_query(F.data == "support:slow")
async def cb_support_slow(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    text = (
        "🌿 Спокойная поддержка\n\n"
        "Давай пойдём шаг за шагом.\n\n"
        "Сначала оценим состояние,\n"
        "потом разберём тревогу и найдём опору.\n\n"
        "Ты не одна/не один в этом."
    )
    await edit(cb, text, reply_markup=kb_anxiety_scale())


@dp.callback_query(F.data == "about:creators")
async def cb_about_creators(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["about_creators"] += 1
    text = (
        "👩‍💻 *О создателях бота*\n\n"
        "Этот бот — результат творческой и бережной работы команды.\n\n"
        "Он создан как пространство поддержки:\n"
        "чтобы человек мог замедлиться, снизить тревогу и сделать шаг к внутренней устойчивости.\n\n"
        "🤗 *Психологическая концепция и тексты*\n"
        "Светлана — психолог\n"
        "@muratovablog\n\n"
        "💻 *Программная разработка*\n"
        "Михаил\n"
        "@mishaguber\n\n"
        "🎨 *Визуальный стиль и дизайн карт*\n"
        "Софья\n"
        "@O11111111O1\n\n"
        "Выбери, чью страницу открыть:"
    )
    await edit(cb, text, reply_markup=kb_creators())


@dp.callback_query(F.data == "creator:svetlana")
async def cb_creator_svetlana(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_svetlana"] += 1
    await cb.answer()
    await cb.message.answer(
        "Светлана — психолог\n"
        "Страница: @muratovablog"
    )


@dp.callback_query(F.data == "creator:mikhail")
async def cb_creator_mikhail(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_mikhail"] += 1
    await cb.answer()
    await cb.message.answer(
        "Михаил — программная разработка\n"
        "Страница: @mishaguber"
    )


@dp.callback_query(F.data == "creator:sofya")
async def cb_creator_sofya(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_sofya"] += 1
    await cb.answer()
    await cb.message.answer(
        "Софья — визуальный стиль и дизайн карт\n"
        "Страница: @O11111111O1"
    )


# ==========================
# ADMIN STATS (only you)
# ==========================
def stats_text() -> str:
    total = sum(ANXIETY_DISTRIBUTION.values())

    popular_steps = {
        "дыхание": STATS["step_breath"],
        "разобрать тревогу": STATS["step_questions"],
        "заземление": STATS["step_ground"],
        "план": STATS["step_plan"],
        "звук леса": STATS["sound_forest"],
    }
    top_step = max(popular_steps, key=popular_steps.get)

    return (
        "📈 *Статистика бота* (только для автора)\n\n"
        f"👥 Пользователей: {len(USERS_SEEN)}\n"
        f"👋 Запусков /start: {STATS['start']}\n"
        f"📊 Открыли шкалу: {STATS['anxiety_open']}\n"
        f"✅ Выбрали уровень: {STATS['anxiety_set']}\n"
        f"📌 Всего оценок тревожности: {total}\n\n"
        f"🌬 Дыхание: {STATS['step_breath']}\n"
        f"💭 Разобрать тревогу: {STATS['step_questions']}\n"
        f"🪨 Заземление: {STATS['step_ground']}\n"
        f"📌 План: {STATS['step_plan']}\n"
        f"🎧 Звук леса: {STATS['sound_forest']}\n\n"
        f"🏆 Самый популярный шаг: {top_step}\n\n"
        f"🔗 Нажатия на страницы создателей:\n"
        f"Светлана: {STATS['creator_svetlana']}\n"
        f"Михаил: {STATS['creator_mikhail']}\n"
        f"Софья: {STATS['creator_sofya']}\n"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(stats_text(), parse_mode="Markdown")


@dp.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    await cb.answer()
    if cb.from_user.id != ADMIN_ID:
        return
    await cb.message.answer(stats_text(), parse_mode="Markdown")


# ==========================
# ANXIETY SCALE (0–10) -> recommendation
# ==========================
@dp.callback_query(F.data == "anxiety:scale")
async def cb_anxiety_scale(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["anxiety_open"] += 1
    text = (
        "📊 *Шкала тревожности*\n\n"
        "Оцени своё состояние от 0 до 10:\n"
        "0 — спокойно\n"
        "5 — заметное напряжение\n"
        "10 — очень сильная тревога\n\n"
        "Выбери число:"
    )
    await edit(cb, text, reply_markup=kb_anxiety_scale())


@dp.callback_query(F.data.startswith("anxiety:"))
async def cb_anxiety_set(cb: CallbackQuery):
    await cb.answer()

    if cb.data == "anxiety:scale":
        return

    try:
        level = int(cb.data.split(":", 1)[1])
    except ValueError:
        return

    if not (0 <= level <= 10):
        return

    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    LAST_ANXIETY[uid] = level
    STATS["anxiety_set"] += 1
    ANXIETY_DISTRIBUTION[level] += 1

    if level >= 7:
        text = (
            f"🧡 Ты отметила/отметил: *{level}/10*\n\n"
            "Похоже, сейчас очень непросто.\n"
            "Давай начнём с того, что быстрее всего помогает телу:\n"
            "дыхание, вода, звук природы и опора на реальность.\n\n"
            f"{praise(uid)}"
        )
    elif level >= 4:
        text = (
            f"💛 Ты отметила/отметил: *{level}/10*\n\n"
            "Тревога заметная. Это уже достаточная причина поддержать себя.\n"
            "Сработает связка: дыхание → ясность → действие.\n\n"
            f"{praise(uid)}"
        )
    else:
        text = (
            f"💚 Ты отметила/отметил: *{level}/10*\n\n"
            "Сейчас относительно спокойно.\n"
            "Можно мягко закрепить это состояние — чтобы тревоге было сложнее разогнаться.\n\n"
            f"{praise(uid)}"
        )

    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb_recommend(level))


# ==========================
# SOUND: FOREST
# ==========================
@dp.callback_query(F.data == "sound:forest")
async def cb_sound_forest(cb: CallbackQuery):
    STATS["sound_forest"] += 1
    USERS_SEEN.add(cb.from_user.id)
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

    uid = cb.from_user.id
    await cb.message.answer(
        "🎧 Включаю лесной шум.\n"
        "Если хочется — сделай 3 цикла: вдох 4… выдох 6.\n\n"
        f"{praise(uid)}"
    )
    await cb.message.answer_audio(
        audio=FSInputFile(path),
        caption="🌲 Лесной шум",
    )
    await cb.message.answer(
        "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?",
        reply_markup=kb_nav(),
    )


# ==========================
# STEP 1: BREATH
# ==========================
@dp.callback_query(F.data == "step:breath")
async def cb_breath(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    STATS["step_breath"] += 1

    header = f"🌬 *Шаг 1 из 4*  `{progress_bar(1)}`"
    text = (
        f"{header}\n\n"
        "Когда тревога поднимается, телу нужен короткий, понятный сигнал безопасности.\n\n"
        "*Физиологический вздох (самый быстрый):*\n"
        "• вдох носом\n"
        "• маленький довдох (как «добавить воздуха»)\n"
        "• длинный выдох ртом\n\n"
        "Повтори **3–5 раз**.\n\n"
        "Если хочется более ровно:\n"
        "*4–6*: вдох на 4… выдох на 6… **8 циклов**.\n\n"
        f"{praise(uid)}\n\n"
        "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
    )
    await edit(cb, text, reply_markup=kb_nav())


# ==========================
# STEP 2: QUESTIONS (FSM)
# ==========================
@dp.callback_query(F.data == "step:questions")
async def cb_questions_start(cb: CallbackQuery, state: FSMContext):
    STATS["step_questions"] += 1
    uid = cb.from_user.id
    USERS_SEEN.add(uid)

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
    await say(
        message,
        "2️⃣ Это больше про *сейчас* или про *будущее*?",
        reply_markup=kb_now_future(),
        delay=0.12,
    )


@dp.callback_query(AnxietyFlow.q2, F.data.in_({"aq:now", "aq:future"}))
async def q2(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    if cb.data == "aq:now":
        await state.update_data(q2="про сейчас")
        await state.set_state(AnxietyFlow.q3)
        await say(
            cb.message,
            "3️⃣ Что ты можешь сделать в ближайшие 10 минут,\n"
            "чтобы стало хотя бы на *5% легче*?\n"
            "Пусть это будет один простой шаг.",
            delay=0.12,
        )

    else:
        await state.update_data(q2="про будущее")
        await state.set_state(AnxietyFlow.q3)
        await say(
            cb.message,
            "Понимаю.\n"
            "Когда тревога уходит в будущее, мысли могут убегать очень далеко вперёд.\n"
            "Это правда выматывает.\n\n"
            "Давай на секунду вернёмся в сегодняшний день.\n\n"
            "3️⃣ Что из того, что тебя тревожит, происходит *уже сейчас*,\n"
            "а что пока существует только в мыслях или предположениях?\n\n"
            "Ответь 1–2 короткими фразами.",
            delay=0.12,
        )


@dp.message(AnxietyFlow.q3)
async def q3(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно коротко, 1–2 фразами.", delay=0.05)
        return

    data = await state.get_data()
    q2_type = data.get("q2", "")

    if q2_type == "про будущее":
        await state.update_data(q3_future=txt)
        await state.set_state(AnxietyFlow.q4)
        await say(
            message,
            "4️⃣ Что ты можешь сделать в ближайшие 10 минут,\n"
            "чтобы стало хотя бы на *5% легче*?\n"
            "Пусть это будет один простой шаг.",
            delay=0.12,
        )
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q5)
    await say(
        message,
        "4️⃣ Представь, что *друг или близкий человек* написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "_1–2 предложения. По-доброму._",
        delay=0.12,
    )


@dp.message(AnxietyFlow.q4)
async def q4(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно написать один простой шаг.", delay=0.05)
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q5)
    await say(
        message,
        "5️⃣ Представь, что *друг или близкий человек* написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "_1–2 предложения. По-доброму._",
        delay=0.12,
    )


@dp.message(AnxietyFlow.q5)
async def q5(message: Message, state: FSMContext):
    uid = message.from_user.id
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной фразой — как поддержал(а) бы близкого человека?", delay=0.05)
        return

    data = await state.get_data()
    await state.clear()

    parts = [
        f"✨ *Итог шага 2*  `{progress_bar(2)}`\n",
        f"😰 *Что пугает:* {data.get('q1', '')}",
        f"🧭 *Это больше:* {data.get('q2', '')}",
    ]

    if data.get("q3_future"):
        parts.append(f"🌫 *Что уже происходит / что пока в мыслях:* {data.get('q3_future', '')}")

    parts.append(f"👣 *Шаг на ближайшее время:* {data.get('q3', '')}")
    parts.append(f"💛 *Поддержка себе:* {txt}")
    parts.append("")
    parts.append(praise(uid))
    parts.append("")
    parts.append("Это уже важный шаг.\nХочешь продолжить или остановимся здесь?")

    summary = "\n".join(parts)
    await say(message, summary, reply_markup=kb_nav(), delay=0.12)


# ==========================
# STEP 3: GROUNDING (SLOW)
# ==========================
@dp.callback_query(F.data == "step:ground")
async def cb_ground(cb: CallbackQuery):
    STATS["step_ground"] += 1
    uid = cb.from_user.id
    USERS_SEEN.add(uid)

    header = f"🌳 *Шаг 3 из 4*  `{progress_bar(3)}`"
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
        "🫐 **1 — вкус**\n"
        "Если вкуса нет — представь вкус свежих ягод или фруктов.\n"
        "Сладкий? Кисловатый? Прохладный?\n\n"
        "И ещё раз: вдох… и длинный выдох…\n\n"
        f"{praise(uid)}\n\n"
        "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
    )
    await edit(cb, text, reply_markup=kb_nav())


# ==========================
# STEP 4: PLAN (2 MIN)
# ==========================
@dp.callback_query(F.data == "step:plan")
async def cb_plan(cb: CallbackQuery):
    STATS["step_plan"] += 1
    USERS_SEEN.add(cb.from_user.id)

    header = f"📌 *Шаг 4 из 4*  `{progress_bar(4)}`"
    text = (
        f"{header}\n\n"
        "Не нужно решать всё сразу.\n"
        "Выбери **один** шаг — этого достаточно.\n\n"
        "Нажми на вариант ниже:"
    )
    await edit(cb, text, reply_markup=kb_plan())


@dp.callback_query(F.data.startswith("plan:"))
async def cb_plan_choice(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    await cb.answer()

    key = cb.data.split(":", 1)[1]
    if key == "water":
        msg = (
            "💧 Выпей воды или умойся.\n"
            "Это простое действие возвращает телу ощущение опоры.\n\n"
            f"{praise(uid)}\n\n"
            "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
        )
    elif key == "air":
        msg = (
            "🌬 Сделай глубокий вдох свежего воздуха…\n"
            "и длинный выдох.\n"
            "Повтори 3 раза.\n\n"
            f"{praise(uid)}\n\n"
            "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
        )
    elif key == "message":
        msg = (
            "💬 Не обязательно справляться с этим в одиночку.\n"
            "Можно написать близкому:\n"
            "«Мне сейчас тревожно, можно 2 минуты поговорить?»\n\n"
            f"{praise(uid)}\n\n"
            "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
        )
    elif key == "facts":
        msg = (
            "📝 Давай вернём опору.\n\n"
            "**1) 3 факта (что точно известно):**\n"
            "Без «а вдруг» — только то, что реально подтверждено.\n\n"
            "**2) 1 следующий шаг:**\n"
            "Что ты можешь сделать в ближайшие 10 минут.\n\n"
            "Одного шага достаточно.\n\n"
            f"{praise(uid)}\n\n"
            "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
        )
    else:  # timer
        msg = (
            "⏲ Поставь таймер на 2 минуты.\n"
            "И сделай самое простое действие из того, что выбрала/выбрал.\n\n"
            f"{praise(uid)}\n\n"
            "Это уже важный шаг.\nХочешь продолжить или остановимся здесь?"
        )

    await say(cb.message, msg, delay=0.12, reply_markup=kb_nav())


# ==========================
# FALLBACK: stop endless "Loading..."
# ==========================
@dp.callback_query()
async def cb_unknown(cb: CallbackQuery):
    await cb.answer("Эта кнопка пока не подключена 🙏 Нажми /start", show_alert=False)


# ==========================
# WEB SERVER
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
