import asyncio
import os
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramConflictError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
    FSInputFile,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ==========================
# CONFIG
# ==========================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

PORT = int(os.getenv("PORT", "10000"))
ADMIN_ID = 862407613

# Ссылка на мак-бот
CARDS_URL = "https://t.me/mak_practice_bot"

# Необязательная ссылка на сайт проекта
PROJECT_URL = os.getenv("PROJECT_URL", "").strip()


# ==========================
# BOT / DISPATCHER
# ==========================
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ==========================
# MEMORY
# ==========================
LAST_ANXIETY: dict[int, int] = {}
LAST_PRACTICE: dict[int, str] = {}
REMINDER_TASKS: dict[int, asyncio.Task] = {}
REMINDER_LABELS: dict[int, str] = {}

STATS = {
    "start": 0,
    "menu": 0,

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
    "site_open": 0,

    "cards_open": 0,

    "reminder_set": 0,
    "reminder_sent": 0,
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
    if os.path.exists(FOREST_MP3):
        return FOREST_MP3
    if os.path.exists(FOREST_MP3_MP3):
        return FOREST_MP3_MP3
    return None


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
# UX HELPERS
# ==========================
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
    parse_mode: str | None = "HTML",
    reply_markup=None,
    delay: float = 0.12,
) -> None:
    await typing(msg.chat.id, delay)
    await msg.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)


async def edit(
    cb: CallbackQuery,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup=None,
) -> None:
    await cb.answer()
    try:
        await cb.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        await say(cb.message, text, parse_mode=parse_mode, reply_markup=reply_markup, delay=0.05)


def praise() -> str:
    return "Ты молодец. Правда.\nДаже один шаг — это опора, которую ты себе создаёшь."


def set_last_practice(user_id: int, practice: str) -> None:
    LAST_PRACTICE[user_id] = practice


def reminder_text(practice: str) -> str:
    mapping = {
        "breath": "🌬 Напоминаю: можно сделать 3–5 спокойных циклов дыхания.\nИногда этого достаточно, чтобы стало легче.",
        "sound_forest": "🎧 Напоминаю: можно включить звук леса и просто немного побыть в тишине.",
        "ground": "🌳 Напоминаю: можно сделать короткое заземление и вернуться в сегодняшний день.",
        "plan_water": "💧 Напоминаю: можно выпить воды или умыться — это простой способ вернуть ощущение опоры.",
        "plan_air": "🌬 Напоминаю: можно сделать глубокий вдох свежего воздуха и длинный выдох.",
        "plan_message": "💬 Напоминаю: можно написать близкому человеку и не оставаться с тревогой в одиночку.",
        "plan_facts": "📝 Напоминаю: можно записать 3 факта и 1 следующий шаг — это помогает вернуть ясность.",
        "plan_timer": "⏲ Напоминаю: можно поставить таймер на 2 минуты и сделать одно простое действие.",
        "questions": "💭 Напоминаю: можно спокойно разобрать, что именно тревожит, и вернуть себе немного ясности.",
        "now_walk": "🚶 Напоминаю: можно немного пройтись и дать телу переключиться.",
        "now_water": "💧 Напоминаю: можно попить воды и чуть замедлиться.",
        "now_breath": "🌬 Напоминаю: можно немного подышать и вернуть телу ощущение безопасности.",
        "now_message": "💬 Напоминаю: можно написать близкому человеку и не оставаться одной или одному.",
    }
    return mapping.get(practice, "🌿 Напоминаю: можно сделать практику поддержки.")


def completion_text(extra: str) -> str:
    base = (
        f"{praise()}\n\n"
        "Это уже важный шаг.\n"
        "Хочешь продолжить, напомнить себе о практике или вернуться в начало?"
    )
    if extra:
        return f"{extra}\n\n{base}"
    return base


def seconds_until_target(hour: int, minute: int, *, tomorrow: bool = False) -> int:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if tomorrow:
        target = target + timedelta(days=1)
    elif target <= now:
        target = target + timedelta(days=1)

    return max(1, int((target - now).total_seconds()))


async def reminder_worker(user_id: int, practice: str, seconds: int) -> None:
    try:
        await asyncio.sleep(seconds)
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"{reminder_text(practice)}\n\n"
                "Если хочется, можно начать с одного шага 👇"
            ),
            parse_mode="HTML",
            reply_markup=kb_after_step(),
        )
        STATS["reminder_sent"] += 1
    except asyncio.CancelledError:
        return
    finally:
        REMINDER_TASKS.pop(user_id, None)
        REMINDER_LABELS.pop(user_id, None)


def schedule_reminder(user_id: int, practice: str, when: str) -> str:
    old_task = REMINDER_TASKS.get(user_id)
    if old_task and not old_task.done():
        old_task.cancel()

    if when == "evening":
        seconds = seconds_until_target(20, 0, tomorrow=False)
        label = "сегодня вечером"
    else:
        seconds = seconds_until_target(10, 0, tomorrow=True)
        label = "завтра"

    task = asyncio.create_task(reminder_worker(user_id, practice, seconds))
    REMINDER_TASKS[user_id] = task
    REMINDER_LABELS[user_id] = label
    STATS["reminder_set"] += 1
    return label


# ==========================
# KEYBOARDS
# ==========================
def kb_start(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Оценить состояние", callback_data="start:anxiety")
    kb.button(text="💚 Получить поддержку", callback_data="start:support")
    kb.button(text="🌱 Метафорические карты", callback_data="cards:open")
    kb.button(text="👩‍💻 О приложении", callback_data="about:creators")
    if user_id == ADMIN_ID:
        kb.button(text="📈 Статистика", callback_data="stats:view")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def kb_cards_open():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌿 Образ дня", url=CARDS_URL)
    kb.button(text="💚 Вернуться к поддержке", callback_data="start:support")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def kb_support():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡ Быстрая помощь", callback_data="support:fast")
    kb.button(text="🌿 Спокойная поддержка", callback_data="support:slow")
    kb.button(text="🌱 МАК-терапия", callback_data="cards:open")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1)
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
    kb.button(text="⏰ Напомнить мне о практике", callback_data="remind:choose")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def kb_reminder_choice():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌙 Сегодня вечером", callback_data="remind:set:evening")
    kb.button(text="🌅 Завтра", callback_data="remind:set:tomorrow")
    kb.button(text="⬅️ Назад", callback_data="remind:back")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def kb_now_future():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏱ Это про сейчас", callback_data="aq:now")
    kb.button(text="🔮 Это про будущее", callback_data="aq:future")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_now_actions():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌬 Подышать", callback_data="now:breath")
    kb.button(text="🚶 Погулять", callback_data="now:walk")
    kb.button(text="💧 Попить воды", callback_data="now:water")
    kb.button(text="💬 Написать близкому", callback_data="now:message")
    kb.button(text="✍️ Свой вариант", callback_data="now:custom")
    kb.adjust(1, 1, 1, 1, 1)
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
        kb.button(text="🌬 Дыхание", callback_data="step:breath")
        kb.button(text="🎧 Звук леса", callback_data="sound:forest")
        kb.button(text="💧 Вода / умыться", callback_data="plan:water")
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


def kb_creators(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Светлана", callback_data="creator:svetlana")
    kb.button(text="Михаил", callback_data="creator:mikhail")
    kb.button(text="Софья", callback_data="creator:sofya")
    kb.button(text="🌿 Перейти в Мак онлайн", url=CARDS_URL)
    if PROJECT_URL:
        kb.button(text="🌐 Сайт проекта", callback_data="creator:site")
    if user_id == ADMIN_ID:
        kb.button(text="⬅️ В статистику", callback_data="stats:view")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def kb_stats():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить статистику", callback_data="stats:view")
    kb.button(text="👩‍💻 К создателям", callback_data="about:creators")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


# ==========================
# STATS
# ==========================
def stats_text() -> str:
    total = sum(ANXIETY_DISTRIBUTION.values())

    popular_steps = {
        "дыхание": STATS["step_breath"],
        "разобрать тревогу": STATS["step_questions"],
        "заземление": STATS["step_ground"],
        "план на 2 минуты": STATS["step_plan"],
        "звук леса": STATS["sound_forest"],
    }
    top_step = max(popular_steps, key=popular_steps.get)

    return (
        "<b>📈 Статистика бота</b>\n\n"
        f"👥 Пользователей: {len(USERS_SEEN)}\n"
        f"👋 Запусков /start: {STATS['start']}\n"
        f"📊 Открыли шкалу: {STATS['anxiety_open']}\n"
        f"✅ Выбрали уровень: {STATS['anxiety_set']}\n"
        f"📌 Всего оценок тревожности: {total}\n\n"
        f"🌬 Дыхание: {STATS['step_breath']}\n"
        f"💭 Разобрать тревогу: {STATS['step_questions']}\n"
        f"🌳 Заземление: {STATS['step_ground']}\n"
        f"📌 План: {STATS['step_plan']}\n"
        f"🎧 Звук леса: {STATS['sound_forest']}\n\n"
        f"🏆 Самый популярный шаг: {top_step}\n\n"
        f"🌿 Образ дня: {STATS['cards_open']}\n\n"
        f"🔗 О создателях:\n"
        f"Светлана: {STATS['creator_svetlana']}\n"
        f"Михаил: {STATS['creator_mikhail']}\n"
        f"Софья: {STATS['creator_sofya']}\n"
        f"Сайт: {STATS['site_open']}\n\n"
        f"⏰ Напоминания установлены: {STATS['reminder_set']}\n"
        f"📩 Напоминания отправлены: {STATS['reminder_sent']}"
    )


# ==========================
# START / MENU
# ==========================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    STATS["start"] += 1
    USERS_SEEN.add(message.from_user.id)

    await message.answer("Обновляю интерфейс…", reply_markup=ReplyKeyboardRemove())

    text = (
        "<b>🌿 Добро пожаловать</b>\n\n"
        "Это пространство поддержки в моменты тревоги, усталости и внутреннего напряжения.\n\n"
        "Здесь не нужно справляться со всем сразу.\n"
        "Можно начать с одного шага — и этого уже достаточно.\n\n"
        "🍃 Если захочется чего-то более образного и интуитивного — можно открыть метафорические карты.\n\n"
        "Выбери, что тебе сейчас ближе 👇"
    )

    await say(message, text, reply_markup=kb_start(message.from_user.id))


@dp.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    STATS["menu"] += 1
    USERS_SEEN.add(cb.from_user.id)

    text = (
        "<b>🌿 Добро пожаловать</b>\n\n"
        "Это пространство поддержки в моменты тревоги, усталости и внутреннего напряжения.\n\n"
        "Здесь не нужно справляться со всем сразу.\n"
        "Можно начать с одного шага — и этого уже достаточно.\n\n"
        "🍃 Если захочется чего-то более образного и интуитивного — можно открыть метафорические карты.\n\n"
        "Выбери, что тебе сейчас ближе 👇"
    )

    await edit(cb, text, reply_markup=kb_start(cb.from_user.id))


@dp.callback_query(F.data == "cards:open")
async def cb_cards_open(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["cards_open"] += 1
    await cb.answer()

    text = (
        "🌱 <b>Метафорические карты</b>\n\n"
        "Иногда к состоянию легче подойти не через вопрос, а через образ.\n\n"
        "Мак терапия помогают остановиться,\n"
        "почувствовать себя и заметить то, что сейчас важно.\n\n"
        "Выбери, как хочешь продолжить:"
    )

    await edit(cb, text, reply_markup=kb_cards_open())


@dp.callback_query(F.data == "more")
async def cb_more(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    text = "Продолжим 💛\n\nВыбери следующий шаг:"
    await edit(cb, text, reply_markup=kb_steps())


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
    kb.button(text="💧 Вода / умыться", callback_data="plan:water")
    kb.button(text="🌳 Заземление", callback_data="step:ground")
    kb.button(text="🏠 В начало", callback_data="menu")
    kb.adjust(1, 1, 1, 1, 1)
    await edit(cb, text, reply_markup=kb.as_markup())


@dp.callback_query(F.data == "support:slow")
async def cb_support_slow(cb: CallbackQuery, state: FSMContext):
    USERS_SEEN.add(cb.from_user.id)
    await state.clear()
    await state.set_state(AnxietyFlow.q1)

    text = (
        "🌿 <b>Спокойная поддержка</b>\n\n"
        "Давай пойдём шаг за шагом.\n\n"
        "1️⃣ <b>Что сейчас пугает или напрягает больше всего?</b>\n"
        "<i>В 1 фразе.</i>"
    )
    await edit(cb, text, reply_markup=None)


# ==========================
# ABOUT BOT / CREATORS
# ==========================
@dp.callback_query(F.data == "about:creators")
async def cb_about_creators(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["about_creators"] += 1
    text = (
        "<b>👩‍💻 О боте</b>\n\n"
        "Этот бот — результат работы команды.\n\n"
        "Он создан как пространство поддержки:\n"
        "чтобы человек мог замедлиться, снизить тревогу и сделать шаг к внутренней устойчивости.\n\n"
        "<b>🤗 Психологическая концепция и тексты</b>\n"
        "Светлана — психолог\n"
        "@teplaya_psihologiya\n\n"
        "<b>💻 Программная разработка</b>\n"
        "Михаил\n"
        "@mishaguber\n\n"
        "<b>🎨 Визуальный стиль и дизайн карт</b>\n"
        "Софья\n"
        "@O11111111O1\n\n"
        "Ниже можно открыть страницы команды или перейти в Мак онлайн."
    )
    await edit(cb, text, reply_markup=kb_creators(cb.from_user.id))


@dp.callback_query(F.data == "creator:svetlana")
async def cb_creator_svetlana(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_svetlana"] += 1
    await cb.answer()
    await cb.message.answer(
    "Светлана — психолог\n"
    "Страница: https://t.me/teplaya_psihologiya"
)

@dp.callback_query(F.data == "creator:mikhail")
async def cb_creator_mikhail(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_mikhail"] += 1
    await cb.answer()
    await cb.message.answer("Михаил — программная разработка\nСтраница: @mishaguber")


@dp.callback_query(F.data == "creator:sofya")
async def cb_creator_sofya(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["creator_sofya"] += 1
    await cb.answer()
    await cb.message.answer(
    "Софья — визуальный стиль и дизайн карт\n"
    "Портфолио: https://readymag.com/archive.ah23/4084372"
)


@dp.callback_query(F.data == "creator:site")
async def cb_creator_site(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    await cb.answer()
    if not PROJECT_URL:
        await cb.message.answer("Ссылка на сайт пока не добавлена.")
        return

    STATS["site_open"] += 1
    await cb.message.answer(f"🌐 Сайт проекта:\n{PROJECT_URL}")


# ==========================
# STATS VIEW
# ==========================
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(stats_text(), parse_mode="HTML", reply_markup=kb_stats())


@dp.callback_query(F.data == "stats:view")
async def cb_stats_view(cb: CallbackQuery):
    await cb.answer()
    if cb.from_user.id != ADMIN_ID:
        return
    await cb.message.answer(stats_text(), parse_mode="HTML", reply_markup=kb_stats())


# ==========================
# ANXIETY SCALE
# ==========================
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
            f"🧡 Ты отметила/отметил: <b>{level}/10</b>\n\n"
            "Похоже, сейчас очень непросто.\n"
            "Давай начнём с того, что быстрее всего помогает телу:\n"
            "дыхание, вода, звук природы и опора на реальность.\n\n"
            f"{praise()}"
        )
    elif level >= 4:
        text = (
            f"💛 Ты отметила/отметил: <b>{level}/10</b>\n\n"
            "Тревога заметная. Это уже достаточная причина поддержать себя.\n"
            "Сработает связка: дыхание → ясность → действие.\n\n"
            f"{praise()}"
        )
    else:
        text = (
            f"💚 Ты отметила/отметил: <b>{level}/10</b>\n\n"
            "Сейчас относительно спокойно.\n"
            "Можно мягко закрепить это состояние — чтобы тревоге было сложнее разогнаться.\n\n"
            f"{praise()}"
        )

    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb_recommend(level))


# ==========================
# REMINDERS
# ==========================
@dp.callback_query(F.data == "remind:choose")
async def cb_remind_choose(cb: CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id

    practice = LAST_PRACTICE.get(uid)
    if not practice:
        await cb.message.answer("Сначала выбери практику, о которой напомнить.")
        return

    practice_names = {
        "breath": "дыхании",
        "sound_forest": "звуке леса",
        "ground": "заземлении",
        "plan_water": "воде / умывании",
        "plan_air": "свежем воздухе",
        "plan_message": "сообщении близкому",
        "plan_facts": "практике «3 факта → 1 шаг»",
        "plan_timer": "таймере",
        "questions": "разборе тревоги",
        "now_walk": "прогулке",
        "now_water": "воде",
        "now_breath": "дыхании",
        "now_message": "сообщении близкому",
    }
    text = (
        f"⏰ Напомнить тебе о <b>{practice_names.get(practice, 'практике')}</b>?\n\n"
        "Выбери время:"
    )
    await edit(cb, text, reply_markup=kb_reminder_choice())


@dp.callback_query(F.data == "remind:back")
async def cb_remind_back(cb: CallbackQuery):
    await cb.answer()
    text = "Продолжим 💛\n\nВыбери следующий шаг:"
    await edit(cb, text, reply_markup=kb_steps())


@dp.callback_query(F.data.startswith("remind:set:"))
async def cb_remind_set(cb: CallbackQuery):
    await cb.answer()
    uid = cb.from_user.id
    practice = LAST_PRACTICE.get(uid)

    if not practice:
        await cb.message.answer("Сначала выбери практику, о которой напомнить.")
        return

    when = cb.data.split(":")[-1]
    label = schedule_reminder(uid, practice, when)

    text = (
        f"⏰ Напоминание установлено: <b>{label}</b>.\n\n"
        "Я напомню тебе об этой практике в выбранное время."
    )
    await edit(cb, text, reply_markup=kb_after_step())


# ==========================
# STEP 1: BREATH
# ==========================
@dp.callback_query(F.data == "step:breath")
async def cb_breath(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    STATS["step_breath"] += 1
    set_last_practice(uid, "breath")

    header = f"🌬 <b>Шаг 1 из 4</b>  <code>{progress_bar(1)}</code>"
    text = (
        f"{header}\n\n"
        "Когда тревога нарастает, телу нужен короткий, понятный сигнал безопасности.\n\n"
        "<b>Физиологический вздох:</b>\n"
        "• вдох носом\n"
        "• маленький довдох\n"
        "• длинный выдох ртом\n\n"
        "Повтори <b>3–5 раз</b>.\n\n"
        "Если хочется более ровно:\n"
        "<b>4–6</b>: вдох на 4, выдох на 6, 8 циклов.\n\n"
        f"{completion_text('')}"
    )
    await edit(cb, text, reply_markup=kb_after_step())


# ==========================
# STEP 2: QUESTIONS
# ==========================
@dp.callback_query(F.data == "step:questions")
async def cb_questions_start(cb: CallbackQuery, state: FSMContext):
    USERS_SEEN.add(cb.from_user.id)
    STATS["step_questions"] += 1
    set_last_practice(cb.from_user.id, "questions")

    await state.clear()
    await state.set_state(AnxietyFlow.q1)

    header = f"💭 <b>Шаг 2 из 4</b>  <code>{progress_bar(2)}</code>"
    text = (
        f"{header}\n\n"
        "Давай разберём тревогу по шагам.\n\n"
        "1️⃣ <b>Что сейчас пугает или напрягает больше всего?</b>\n"
        "<i>В 1 фразе.</i>"
    )
    await edit(cb, text, reply_markup=None)


@dp.message(AnxietyFlow.q1)
async def q1(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной короткой фразой — что сейчас пугает больше всего?")
        return

    await state.update_data(q1=txt)
    await state.set_state(AnxietyFlow.q2)
    await say(
        message,
        "2️⃣ Это больше про <b>сейчас</b> или про <b>будущее</b>?",
        reply_markup=kb_now_future(),
    )


@dp.callback_query(AnxietyFlow.q2, F.data == "aq:now")
async def q2_now(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(q2="про сейчас")
    await state.set_state(AnxietyFlow.q3)

    await say(
        cb.message,
        "3️⃣ Что может помочь тебе <b>прямо сейчас</b>?\n\n"
        "Можно выбрать готовый вариант 👇",
        reply_markup=kb_now_actions(),
    )


@dp.callback_query(AnxietyFlow.q2, F.data == "aq:future")
async def q2_future(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(q2="про будущее")
    await state.set_state(AnxietyFlow.q3)

    await say(
        cb.message,
        "Понимаю.\n"
        "Когда тревога уходит в будущее, мысли могут убегать далеко вперёд.\n"
        "Это правда выматывает.\n\n"
        "Давай на секунду вернёмся в сегодняшний день.\n\n"
        "3️⃣ Что из того, что тебя тревожит, происходит <b>уже сейчас</b>,\n"
        "а что пока существует только в мыслях или предположениях?\n\n"
        "Ответь 1–2 короткими фразами.",
    )


@dp.callback_query(AnxietyFlow.q3, F.data.startswith("now:"))
async def q3_now_actions(cb: CallbackQuery, state: FSMContext):
    await cb.answer()

    mapping = {
        "now:breath": ("подышать", "now_breath"),
        "now:walk": ("погулять", "now_walk"),
        "now:water": ("попить воды", "now_water"),
        "now:message": ("написать близкому", "now_message"),
    }

    if cb.data == "now:custom":
        await say(
            cb.message,
            "Напиши свой вариант.\nЧто может помочь тебе прямо сейчас?",
        )
        return

    chosen_text, practice_key = mapping.get(cb.data, ("", "questions"))
    await state.update_data(q3=chosen_text)
    set_last_practice(cb.from_user.id, practice_key)
    await state.set_state(AnxietyFlow.q5)

    await say(
        cb.message,
        "4️⃣ Представь, что <b>друг или близкий человек</b> написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "<i>1–2 предложения. По-доброму.</i>",
    )


@dp.message(AnxietyFlow.q3)
async def q3(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно коротко, 1–2 фразами.")
        return

    data = await state.get_data()
    q2_type = data.get("q2", "")

    if q2_type == "про будущее":
        await state.update_data(q3_future=txt)
        await state.set_state(AnxietyFlow.q4)
        await say(
            message,
            "4️⃣ Что может помочь тебе в ближайшее время?\n"
            "Напиши один простой шаг.",
        )
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q5)
    await say(
        message,
        "4️⃣ Представь, что <b>друг или близкий человек</b> написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "<i>1–2 предложения. По-доброму.</i>",
    )


@dp.message(AnxietyFlow.q4)
async def q4(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно написать один простой шаг.")
        return

    await state.update_data(q3=txt)
    await state.set_state(AnxietyFlow.q5)
    await say(
        message,
        "5️⃣ Представь, что <b>друг или близкий человек</b> написал тебе это же.\n"
        "Что бы ты ответил(а), чтобы поддержать?\n"
        "<i>1–2 предложения. По-доброму.</i>",
    )


@dp.message(AnxietyFlow.q5)
async def q5(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if len(txt) < 2:
        await say(message, "Можно одной фразой — как поддержал(а) бы близкого человека?")
        return

    data = await state.get_data()
    await state.clear()

    parts = [
        f"✨ <b>Итог шага 2</b>  <code>{progress_bar(2)}</code>\n",
        f"😰 <b>Что пугает:</b> {data.get('q1', '')}",
        f"🧭 <b>Это больше:</b> {data.get('q2', '')}",
    ]

    if data.get("q3_future"):
        parts.append(f"🌫 <b>Что уже происходит / что пока в мыслях:</b> {data.get('q3_future', '')}")

    parts.append(f"👣 <b>Шаг на ближайшее время:</b> {data.get('q3', '')}")
    parts.append(f"💛 <b>Поддержка себе:</b> {txt}")
    parts.append("")
    parts.append(praise())
    parts.append("")
    parts.append("Это уже важный шаг.\nХочешь продолжить, напомнить себе о практике или вернуться в начало?")

    summary = "\n".join(parts)
    await say(message, summary, reply_markup=kb_after_step())


# ==========================
# STEP 3: GROUNDING
# ==========================
@dp.callback_query(F.data == "step:ground")
async def cb_ground(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    STATS["step_ground"] += 1
    set_last_practice(uid, "ground")

    header = f"🌳 <b>Шаг 3 из 4</b>  <code>{progress_bar(3)}</code>"
    text = (
        f"{header}\n\n"
        "Сейчас мы возвращаем внимание в реальность, шаг за шагом.\n\n"
        "Сделай спокойный вдох…\n"
        "и медленный выдох…\n\n"
        "👀 <b>5 — что ты видишь</b>\n"
        "Оглянись и найди 5 вещей.\n\n"
        "🤍 <b>4 — что ты чувствуешь физически</b>\n"
        "Удобно ли тебе? Тепло или прохладно?\n\n"
        "🎶 <b>3 — что ты слышишь</b>\n"
        "Найди 3 звука вокруг.\n\n"
        "🌬 <b>2 — запахи</b>\n"
        "Есть ли запах рядом?\n\n"
        "🫐 <b>1 — вкус</b>\n"
        "Если вкуса нет — просто представь вкус ягод или фруктов.\n\n"
        f"{completion_text('')}"
    )
    await edit(cb, text, reply_markup=kb_after_step())


# ==========================
# STEP 4: PLAN
# ==========================
@dp.callback_query(F.data == "step:plan")
async def cb_plan(cb: CallbackQuery):
    USERS_SEEN.add(cb.from_user.id)
    STATS["step_plan"] += 1

    header = f"📌 <b>Шаг 4 из 4</b>  <code>{progress_bar(4)}</code>"
    text = (
        f"{header}\n\n"
        "Не нужно решать всё сразу.\n"
        "Выбери <b>один</b> шаг — этого достаточно.\n\n"
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
        set_last_practice(uid, "plan_water")
        msg = completion_text(
            "💧 Выпей воды или умойся.\n"
            "Это простое действие возвращает телу ощущение опоры."
        )
    elif key == "air":
        set_last_practice(uid, "plan_air")
        msg = completion_text(
            "🌬 Сделай глубокий вдох свежего воздуха…\n"
            "и длинный выдох.\n"
            "Повтори 3 раза."
        )
    elif key == "message":
        set_last_practice(uid, "plan_message")
        msg = completion_text(
            "💬 Не обязательно справляться с этим в одиночку.\n"
            "Можно написать близкому:\n"
            "«Мне сейчас тревожно, можно 2 минуты поговорить?»"
        )
    elif key == "facts":
        set_last_practice(uid, "plan_facts")
        msg = completion_text(
            "📝 Давай вернём опору.\n\n"
            "<b>1) 3 факта (что точно известно):</b>\n"
            "Без «а вдруг» — только то, что реально подтверждено.\n\n"
            "<b>2) 1 следующий шаг:</b>\n"
            "Что ты можешь сделать в ближайшие 10 минут.\n\n"
            "Одного шага достаточно."
        )
    else:
        set_last_practice(uid, "plan_timer")
        msg = completion_text(
            "⏲ Поставь таймер на 2 минуты.\n"
            "И сделай самое простое действие из того, что выбрала/выбрал."
        )

    await say(cb.message, msg, reply_markup=kb_after_step())


# ==========================
# SOUND
# ==========================
@dp.callback_query(F.data == "sound:forest")
async def cb_sound_forest(cb: CallbackQuery):
    uid = cb.from_user.id
    USERS_SEEN.add(uid)
    STATS["sound_forest"] += 1
    set_last_practice(uid, "sound_forest")
    await cb.answer()

    path = get_forest_audio_path()
    if not path:
        await cb.message.answer(
            "Не нашла файл звука 😕\n"
            "Проверь, что в репозитории есть:\n"
            "assets/audio/forest.mp3"
        )
        return

    await cb.message.answer(
        completion_text(
            "🎧 Включаю лесной шум.\n"
            "Если хочется — сделай 3 цикла: вдох 4… выдох 6."
        ),
        parse_mode="HTML",
        reply_markup=kb_after_step(),
    )
    await cb.message.answer_audio(
        audio=FSInputFile(path),
        caption="🌲 Лесной шум",
    )


# ==========================
# CALLBACK FALLBACK
# ==========================
@dp.callback_query()
async def cb_unknown(cb: CallbackQuery):
    await cb.answer("Эта кнопка пока не подключена 🙏", show_alert=False)


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
# POLLING
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
        except Exception as e:
            print("POLLING ERROR:", e)
            await asyncio.sleep(3)


async def main():
    await start_web_server()
    await run_polling_forever()


if __name__ == "__main__":
    asyncio.run(main())
