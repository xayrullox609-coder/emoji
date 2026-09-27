"""
green.py — Birlashtirilgan bot: "Name Emojis" (newbot_fixed) + "Logo/Text Emojis"
(tgs_make_bot') bitta botda.

[start bosilganda 2 ta bo'lim ko'rsatiladi:
  🔤 Name Emojis      — so'zdan tayyor shablon ustiga yozilgan animatsiyali emoji
  🖼 Logo/Text Emojis — 103 ta tayyor shablondan birini tanlab, ustiga
                        o'zingizning matningizni joylash

FAYL TUZILISHI:
    green.py        <- shu fayl (Telegram handlerlari)
    logo_engine.py         <- SVG/Lottie generatsiya "dvigateli" (tgs_make_bot'dan)
    logo_emoji_ids.py      <- Logo/Text shablonlari uchun preview custom_emoji_id lar
    template_engine.py     <- Name emoji render dvigateli (o'zgarishsiz)
    font_render.py         <- Name emoji shrift render (o'zgarishsiz)
    templates_config.py    <- Name emoji shablonlari sozlamalari (o'zgarishsiz)
    templates/*.json       <- Name emoji shablonlari
    templates_tgs/*.json   <- Logo/Text emoji shablonlari (yangilangan JSON'lar)
    fonts/*.ttf             <- Har ikkala bo'lim uchun shriftlar
"""

import asyncio
import json
import logging
import os
import random
import re
import string
import zipfile

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    Message,
    MessageEntity,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
)

import logo_engine
from logo_emoji_ids import LOGO_TEMPLATE_EMOJI_IDS
from template_engine import render_template, save_as_tgs
from templates_config import EMOJI_IDS, TEMPLATE_ORDER, TEMPLATES

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
MAX_LEN = 12
PLACEHOLDER = "\U0001F538"


def _random_nick(length: int = 12) -> str:
    """Telegram-style random lowercase nick, e.g. 'wiwheowuwhsj'."""
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _section_label(kind: str) -> str:
    return {
        "logo": "Logo/Text emoji",
        "green": "Green Emojis",
        "name": "Name emoji"
    }.get(kind, "Name emoji")


ADMIN_ID = 0
LOG_CHAT_ID = 0

ALLOWED_FILE = os.path.join(
    os.path.dirname(__file__),
    "allowed_users.json"
)

USERS_FILE = os.path.join(
    os.path.dirname(__file__),
    "users.json"
)

EMOJI_PACK_FILE = os.path.join(
    os.path.dirname(__file__),
    "emoji_pack.json"
)

PRICE_FILES = {
    "name": os.path.join(
        os.path.dirname(__file__),
        "price_name.json"
    ),
    "logo": os.path.join(
        os.path.dirname(__file__),
        "price_logo.json"
    ),
    "code": os.path.join(
        os.path.dirname(__file__),
        "price_code.json"
    ),
    "green": os.path.join(
        os.path.dirname(__file__),
        "price_green.json"
    ),
}


# ---------- "🟢 Green Emojis" bo'limi ----------
GREEN_EMOJI_DIR = os.path.join(
    os.path.dirname(__file__),
    "green_emojis"
)

GREEN_EMOJI_TEMPLATE_PATHS = [
    os.path.join(GREEN_EMOJI_DIR, f"{i:03d}.json")
    for i in range(1, 30)
]

GREEN_EMOJI_PREVIEW_IDS = [
    "5449413509702001244",
    "5447566038109560980",
    "5447363161034367576",
    "5447583398367370838",
    "5447175999244507666",
    "5447380731745575376",
    "5447113975621794813",
    "5447180062283571572",
    "5449389045568284712",
    "5449439532908851080",
    "5447582251611105317",
    "5449782206874559979",
    "5447120095950185848",
    "5449592751572167022",
    "5447233822389217314",
    "5447570921487379718",
    "5447188351570454981",
    "5449492760438547397",
    "5447224918922010955",
    "5447352084313712339",
    "5449864369598933552",
    "5447264823463162476",
    "5447266133428185558",
    "5447304534730776164",
    "5449821239537345805",
    "5447356611209242428",
    "5447416573247660061",
    "5447418540342682118",
    "5449719758050075099",
]

CREDITS_FILE = os.path.join(
    os.path.dirname(__file__),
    "credits.json"
)

STATS_FILE = os.path.join(
    os.path.dirname(__file__),
    "stats.json"
)

REFUND_REQUESTS_FILE = os.path.join(
    os.path.dirname(__file__),
    "refund_requests.json"
)

REFERRALS_FILE = os.path.join(
    os.path.dirname(__file__),
    "referrals.json"
)

SETTINGS_FILE = os.path.join(
    os.path.dirname(__file__),
    "settings.json"
)

DEFAULT_PRICE_STARS = 15
DEFAULT_CODE_PRICE_STARS = 5000

DEFAULT_SUPPORT_CONTACT = "@your_support_username"

LOGO_PAGE_SIZE = 10
TOTAL_LOGO_TEMPLATES = 103

logging.basicConfig(level=logging.INFO)

router = Router()


# ============================================================================
# Umumiy: pack saqlash, ruxsatlar, foydalanuvchilar, narx, kreditlar,
# referal, majburiy kanallar
# ============================================================================

def load_packs() -> dict:
    if not os.path.exists(EMOJI_PACK_FILE):
        return {}

    try:
        with open(EMOJI_PACK_FILE, encoding="utf-8") as f:
            return json.load(f)

    except (json.JSONDecodeError, OSError):
        return {}


def save_packs(packs: dict):
    with open(EMOJI_PACK_FILE, "w", encoding="utf-8") as f:
        json.dump(packs, f)


def _safe_nick(nick: str) -> str:
    cleaned = re.sub(
        r"[^a-zA-Z0-9_]",
        "",
        nick
    )

    return cleaned or "pack"


async def add_stickers_to_pack(
    bot: Bot,
    sticker_paths: list[str],
    nick: str,
    pack_kind: str,
    progress_message: Message | None = None,
    owner_id: int | None = None,
    title: str | None = None,
):
    """
    Create or reuse a sticker set for this nick+kind and add all the
    given stickers to it.
    """

    from aiogram.types import InputSticker

    sticker_type = (
        "custom_emoji"
        if pack_kind == "emoji"
        else "regular"
    )

    owner_id = owner_id or ADMIN_ID

    packs = load_packs()

    storage_key = f"{pack_kind}:{nick}:{owner_id}"

    name = packs.get(storage_key)

    total = len(sticker_paths)

    last_text = None

    async def update(text: str):
        nonlocal last_text

        if progress_message is None or text == last_text:
            return

        last_text = text

        try:
            await progress_message.edit_text(text)

        except Exception:
            pass

    try:
        me = await bot.get_me()

        if not name:
            name = (
                f"{_safe_nick(nick)}_{owner_id}_by_{me.username}"
            )

        for i, sticker_path in enumerate(sticker_paths):

            item = InputSticker(
                sticker=FSInputFile(sticker_path),
                format="animated",
                emoji_list=["🙂"]
            )

            while True:

                try:

                    if i == 0 and storage_key not in packs:

                        try:
                            await bot.create_new_sticker_set(
                                user_id=owner_id,
                                name=name,
                                title=title or nick,
                                stickers=[item],
                                sticker_type=sticker_type,
                            )

                        except TelegramBadRequest as e:

                            if "already occupied" not in str(e).lower():
                                raise

                            await bot.add_sticker_to_set(
                                user_id=owner_id,
                                name=name,
                                sticker=item
                            )

                        packs[storage_key] = name

                        save_packs(packs)

                    else:

                        await bot.add_sticker_to_set(
                            user_id=owner_id,
                            name=name,
                            sticker=item
                        )

                    break

                except TelegramRetryAfter as e:

                    await update(
                        f"⏳ Telegram cheklovi sababli "
                        f"{e.retry_after}s kutyapmiz "
                        f"({i}/{total} qo'shildi), "
                        f"keyin davom etamiz..."
                    )

                    await asyncio.sleep(
                        e.retry_after + 1
                    )

                    continue

            await update(
                f"⏳ Tayyorlanmoqda: "
                f"{i + 1}/{total} qo'shildi"
            )

        return name

    except Exception as e:

        logging.warning(
            f"pack update failed: {e}"
        )

        return None


def load_allowed() -> set[int]:

    if not os.path.exists(ALLOWED_FILE):
        return set()

    try:

        with open(
            ALLOWED_FILE,
            encoding="utf-8"
        ) as f:

            return set(json.load(f))

    except (json.JSONDecodeError, OSError):

        return set()


def save_allowed(ids: set[int]):

    with open(
        ALLOWED_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            sorted(ids),
            f
        )


def is_free_user(user_id: int) -> bool:

    return (
        user_id == ADMIN_ID
        or user_id in load_allowed()
    )


def load_users() -> set[int]:

    if not os.path.exists(USERS_FILE):
        return set()

    try:

        with open(
            USERS_FILE,
            encoding="utf-8"
        ) as f:

            return set(json.load(f))

    except (json.JSONDecodeError, OSError):

        return set()


def save_users(ids: set[int]):

    with open(
        USERS_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            sorted(ids),
            f
        )


def record_user(user_id: int):
    """
    Remember that this user has started the bot,
    so broadcasts can reach them.
    """

    users = load_users()

    if user_id not in users:

        users.add(user_id)

        save_users(users)


def load_price(kind: str = "name") -> int:

    path = PRICE_FILES.get(
        kind,
        PRICE_FILES["name"]
    )

    default = (
        DEFAULT_CODE_PRICE_STARS
        if kind == "code"
        else DEFAULT_PRICE_STARS
    )

    if not os.path.exists(path):
        return default

    try:

        with open(
            path,
            encoding="utf-8"
        ) as f:

            return int(
                json.load(f).get(
                    "stars",
                    default
                )
            )

    except (
        json.JSONDecodeError,
        OSError,
        ValueError,
        TypeError
    ):

        return default


def save_price(kind: str, stars: int):

    path = PRICE_FILES.get(
        kind,
        PRICE_FILES["name"]
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {"stars": stars},
            f
        )


# ---------- Bot manba kodini sotish uchun toza .zip paket ----------

_CODE_PACKAGE_DIR = os.path.join(
    os.path.dirname(__file__),
    "output"
)

_CODE_PACKAGE_PATH = os.path.join(
    _CODE_PACKAGE_DIR,
    "bot_source_code.zip"
)
# Ishga tushirish paytidagi bu botning o'ziga tegishli maxfiy/runtime
# ma'lumotlari — xaridorga sotilgan nusxada bular BO'LMASLIGI kerak.
_CODE_PACKAGE_EXCLUDE_DIRS = {"__pycache__", "output", "data"}
_CODE_PACKAGE_EXCLUDE_FILES = {
    "users.json", "credits.json", "allowed_users.json", "emoji_pack.json",
    "referrals.json", "settings.json", "stats.json", "refund_requests.json",
    "price_name.json", "price_logo.json", "price_code.json", "price_green.json",
    "sonnet.lock", "bot.log",
}


def _sanitize_bot_py(content: str) -> str:
    """Sotuvchining haqiqiy BOT_TOKEN/ADMIN_ID/LOG_CHAT_ID qiymatlarini
    green.py nusxasidan olib tashlab, xaridor o'zi to'ldiradigan bo'sh
    joy (placeholder) bilan almashtiradi."""
    content = re.sub(
        r'BOT_TOKEN = os\.environ\.get\("BOT_TOKEN", "[^"]*"\)',
        'BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")',
        content,
    )
    content = re.sub(
        r"ADMIN_ID = \d+",
        "ADMIN_ID = 0  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing",
        content,
    )
    content = re.sub(
        r"LOG_CHAT_ID = -?\d+",
        "LOG_CHAT_ID = 0  # <-- shu yerga o'z log kanalingizning id'sini yozing  # <-- shu yerga o'z log kanalingizning id'sini yozing  # <-- shu yerga o'z log kanalingizning id'sini yozing  # <-- shu yerga o'z log kanalingizning id'sini yozing",
        content,
    )
    return content


def build_code_package() -> str:
    """Botning o'z manba kodidan tozalangan (token/admin/kanal/yordam
    kontakti olib tashlangan) .zip paket yasaydi. Har bir xariddan keyin
    QAYTA yasaladi (fayllar o'zgargan bo'lishi mumkin), lekin bevosita
    umumiy _CODE_PACKAGE_PATH'ga yozmaydi: avval alohida vaqtinchalik
    faylga yozadi, so'ng atomik ravishda almashtiradi. Bu ikkita xarid
    bir vaqtda bo'lganda (yoki eski, hali ochilmagan invoys keyinroq
    to'langanda) bittasi hali yozilayotgan/yarim tugallangan zip fayl
    o'qib yuborilib, xaridorga buzilgan/bo'sh fayl ketishining oldini
    oladi."""
    os.makedirs(_CODE_PACKAGE_DIR, exist_ok=True)
    src_root = os.path.dirname(__file__)

    tmp_path = f"{_CODE_PACKAGE_PATH}.{os.getpid()}.{random.randint(0, 999999)}.tmp"
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(src_root):
            dirnames[:] = [d for d in dirnames if d not in _CODE_PACKAGE_EXCLUDE_DIRS]
            for fname in filenames:
                if fname in _CODE_PACKAGE_EXCLUDE_FILES:
                    continue
                full_path = os.path.join(dirpath, fname)
                arcname = os.path.join("green", os.path.relpath(full_path, src_root))
                if fname in ("green.py", "telegram.py"):
                    with open(full_path, encoding="utf-8") as f:
                        content = f.read()
                    zf.writestr(arcname, _sanitize_bot_py(content))
                else:
                    zf.write(full_path, arcname)

    # Atomic on the same filesystem - readers either see the old complete
    # file or the new complete file, never a half-written one.
    os.replace(tmp_path, _CODE_PACKAGE_PATH)
    return _CODE_PACKAGE_PATH


def load_credits() -> dict:
    if not os.path.exists(CREDITS_FILE):
        return {}
    try:
        with open(CREDITS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_credits(credits: dict):
    with open(CREDITS_FILE, "w", encoding="utf-8") as f:
        json.dump(credits, f)


def get_credits(user_id: int) -> int:
    return load_credits().get(str(user_id), 0)


def add_credit(user_id: int, n: int = 1):
    credits = load_credits()
    key = str(user_id)
    credits[key] = credits.get(key, 0) + n
    save_credits(credits)


def use_credit(user_id: int) -> bool:
    credits = load_credits()
    key = str(user_id)
    if credits.get(key, 0) <= 0:
        return False
    credits[key] -= 1
    save_credits(credits)
    return True


def load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_stats(stats: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f)


def record_pack_created(user_id: int, username: str | None):
    """Track how many packs (emoji/sticker sets) each user has generated,
    for the admin 'who made the most' leaderboard."""
    stats = load_stats()
    key = str(user_id)
    entry = stats.get(key, {"packs": 0, "stars": 0, "username": None})
    entry["packs"] = entry.get("packs", 0) + 1
    if username:
        entry["username"] = username
    stats[key] = entry
    save_stats(stats)


def record_stars_spent(user_id: int, username: str | None, amount: int):
    """Track how many Stars each user has paid the bot in total, for the
    admin 'who spent the most' leaderboard."""
    if amount <= 0:
        return
    stats = load_stats()
    key = str(user_id)
    entry = stats.get(key, {"packs": 0, "stars": 0, "username": None})
    entry["stars"] = entry.get("stars", 0) + amount
    if username:
        entry["username"] = username
    stats[key] = entry
    save_stats(stats)


def load_refund_requests() -> dict:
    if not os.path.exists(REFUND_REQUESTS_FILE):
        return {}
    try:
        with open(REFUND_REQUESTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_refund_requests(requests: dict):
    with open(REFUND_REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(requests, f)


def create_refund_request(user_id: int, charge_id: str, amount: int) -> str:
    """Stash a pending stale-price refund so the admin can trigger it with
    one tap from the log channel, without the charge_id (which can be
    long) needing to round-trip through callback_data."""
    requests = load_refund_requests()
    ref_id = f"{user_id}_{len(requests)}_{random.randint(0, 999999)}"
    requests[ref_id] = {
        "user_id": user_id, "charge_id": charge_id, "amount": amount, "done": False,
    }
    save_refund_requests(requests)
    return ref_id


def load_referrals() -> dict:
    if not os.path.exists(REFERRALS_FILE):
        return {}
    try:
        with open(REFERRALS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_referrals(referrals: dict):
    with open(REFERRALS_FILE, "w", encoding="utf-8") as f:
        json.dump(referrals, f)


def record_referral(referred_id: int, referrer_id: int):
    """Remember who invited whom, so we can reward the referrer once the
    referred user finishes their first pack. Only the first referrer for
    a given user counts, and self-referrals are ignored."""
    if referred_id == referrer_id:
        return
    referrals = load_referrals()
    key = str(referred_id)
    if key in referrals:
        return
    referrals[key] = {"referrer": referrer_id, "rewarded": False}
    save_referrals(referrals)


async def reward_referral_if_pending(bot: Bot, referred_id: int):
    referrals = load_referrals()
    key = str(referred_id)
    entry = referrals.get(key)
    if not entry or entry.get("rewarded"):
        return
    referrer_id = entry["referrer"]
    entry["rewarded"] = True
    save_referrals(referrals)
    add_credit(referrer_id, 1)
    try:
        await bot.send_message(
            referrer_id,
            "🎉 Siz taklif qilgan do'stingiz birinchi emojisini yasadi!\n"
            "Sizga 1 ta bepul kredit berildi. Keyingi emojingizni yasaganda ishlatishingiz mumkin.",
        )
    except Exception as e:
        logging.warning(f"referral notify failed: {e}")


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f)


def get_channels() -> list[str]:
    channels = load_settings().get("channels")
    if channels:
        return channels
    legacy = load_settings().get("channel")
    return [legacy] if legacy else []


def set_channels(channels: list[str]):
    settings = load_settings()
    settings["channels"] = channels
    settings.pop("channel", None)
    save_settings(settings)


def get_support_contact() -> str:
    """Support/help contact shown in user-facing messages. Stored in
    settings.json (per-deployment, not shipped in the sold code package)
    so each buyer of the bot code sets their own without ever seeing
    the seller's."""
    return load_settings().get("support_contact") or DEFAULT_SUPPORT_CONTACT


def set_support_contact(contact: str):
    settings = load_settings()
    settings["support_contact"] = contact
    save_settings(settings)


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    channels = get_channels()
    if not channels:
        return True
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning(f"channel check failed for {channel}: {e}")
            continue
    return True


def subscribe_keyboard(channels: list[str]):
    rows = []
    for i, channel in enumerate(channels, start=1):
        uname = channel.lstrip("@")
        label = f"➕ Obuna bo'lish #{i}" if len(channels) > 1 else "📢 Kanalga o'tish"
        rows.append([InlineKeyboardButton(text=label, url=f"https://t.me/{uname}", style="primary")])
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="checksub", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _normalize_hex(text: str):
    m = re.match(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$", (text or "").strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
    601	        h = "".join(c * 2 for c in h)
    602	    return "#" + h.upper()


    605	def _utf16_len(s: str) -> int:
    606	    return len(s.encode("utf-16-le")) // 2


    # ============================================================================
    # FSM holatlar
    # ============================================================================

    class Flow(StatesGroup):
        word = State()
        pack_title = State()
        pack_nick = State()


    class LogoFlow(StatesGroup):
        waiting_outer = State()
        waiting_outer_hex = State()
        waiting_inner = State()
        waiting_inner_hex = State()
        waiting_logo_color = State()
        waiting_logo_color_hex = State()
        waiting_svg = State()


    class GiftFlow(StatesGroup):
        waiting_amount = State()


    class GreenFlow(StatesGroup):
        waiting_text = State()
        waiting_text_color = State()
        waiting_text_color_hex = State()


    class AdminFlow(StatesGroup):
        add_id = State()
        remove_id = State()
        set_price = State()
        set_channel = State()
        set_support = State()
        broadcast = State()


    # ============================================================================
    # Bosh menyu (/start) — 2 bo'lim: Name Emojis / Logo Text Emojis
    # ============================================================================

    def main_section_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔤 Name Emojis", callback_data="section:name", style="primary"),
            InlineKeyboardButton(text="🖼 Logo/Text Emojis", callback_data="section:logo", style="primary"),
        ], [
            InlineKeyboardButton(text="🟢 Green Emojis", callback_data="section:green", style="primary"),
        ], [
            InlineKeyboardButton(text="🎁 Yulduz hadya qilish", callback_data="section:gift", style="primary"),
        ], [
            InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
        ]])


    BUY_CODE_BUTTON_TEXT = "💻 Bot kodini olish"


    def persistent_keyboard():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BUY_CODE_BUTTON_TEXT)]],
            resize_keyboard=True,
        )


    async def _send_section_menu(message: Message):
        await message.answer("Nima yasaymiz? 👇", reply_markup=main_section_keyboard())


    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        record_user(message.from_user.id)

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1][len("ref_"):])
                record_referral(message.from_user.id, referrer_id)
            except ValueError:
                pass

        channels = get_channels()
        if channels and not await is_subscribed(message.bot, message.from_user.id):
            await message.answer(
                "Botdan foydalanish uchun avval kanal(lar)ga a'zo bo'ling, so'ng \"Tekshirish\" tugmasini bosing:",
                reply_markup=subscribe_keyboard(channels),
            )
            return

        await message.answer("👋 Xush kelibsiz!", reply_markup=persistent_keyboard())
        await _send_section_menu(message)


    @router.callback_query(F.data == "checksub")
    async def check_subscription(callback: CallbackQuery):
        channels = get_channels()
        if channels and not await is_subscribed(callback.bot, callback.from_user.id):
            await callback.answer("Hali barcha kanallarga a'zo bo'lmadingiz.", show_alert=True)
            return
        await callback.answer("✅ Tasdiqlandi!")
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _send_section_menu(callback.message)


    @router.callback_query(F.data == "backmain")
    async def back_to_main(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer()
        await _send_section_menu(callback.message)


    @router.callback_query(F.data == "help")
    async def help_handler(callback: CallbackQuery):
        me = await callback.bot.get_me()
        ref_link = f"https://t.me/{me.username}?start=ref_{callback.from_user.id}"
        credits = get_credits(callback.from_user.id)
        await callback.message.answer(
            f"🆘 Savol yoki muammo bo'lsa {get_support_contact()} ga yozing.\n\n"
            "🎁 Do'stingizni taklif qiling! U birinchi emoji/stikerini yasab bo'lgach, "
            "sizga 1 ta bepul kredit beriladi (keyingi emojingiz uchun to'lovsiz foydalanasiz).\n\n"
            f"Sizning taklif havolangiz:\n{ref_link}\n\n"
            f"💳 Hozir sizda {credits} ta bepul kredit bor."
        )
        await callback.answer()


    # ============================================================================
    # BO'LIM 0: YULDUZ HADYA QILISH (Telegram Stars orqali oddiy hadya)
    # ============================================================================

    GIFT_MIN_AMOUNT = 1
    GIFT_MAX_AMOUNT = 100000


    @router.callback_query(F.data == "section:gift")
    async def section_gift(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.set_state(GiftFlow.waiting_amount)
        await callback.answer()
        await callback.message.answer(
            "🎁 Nechta ⭐ Stars hadya qilmoqchisiz? Sonini yozing (masalan: 100):"
        )


    @router.message(GiftFlow.waiting_amount, F.text)
    async def gift_got_amount(message: Message, state: FSMContext):
        raw = (message.text or "").strip()
        if not raw.isdigit():
            await message.answer("Iltimos, faqat son yuboring (masalan: 100).")
            return
        amount = int(raw)
        if not (GIFT_MIN_AMOUNT <= amount <= GIFT_MAX_AMOUNT):
            await message.answer(
                f"Son {GIFT_MIN_AMOUNT} dan {GIFT_MAX_AMOUNT} tagacha bo'lishi kerak. Qaytadan yozing:"
            )
            return

        await state.update_data(gift_amount=amount)
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title="⭐ Yulduz hadya",
            description=f"{amount} ⭐ Stars hadya qilish",
            payload=f"gift:{message.from_user.id}:{amount}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Stars hadya", amount=amount)],
        )


    @router.message(GiftFlow.waiting_amount)
    async def gift_got_wrong_type(message: Message):
        await message.answer("Iltimos, faqat son yuboring (masalan: 100).")


    # ============================================================================
    # BOT KODINI SOTIB OLISH (pastki, doimiy tugma orqali)
    # ============================================================================

    async def _deliver_code_package(bot: Bot, chat_id: int) -> tuple[bool, Exception | None]:
        """bot_source_code.zip'ni yasab, bergan chat_id'ga yuboradi (kerak bo'lsa
        1 marta qayta urinib). Pullik va bepul (admin) yo'llarning ikkalasi ham
        shu funksiyani ishlatadi, shunda kod yuborish mantiqi bitta joyda qoladi."""
        last_error = None
        for attempt in range(2):
            try:
                zip_path = build_code_package()
                if not zipfile.is_zipfile(zip_path):
                    raise RuntimeError("zip fayl buzilgan chiqdi, qayta yasalmoqda")
                await bot.send_document(
                    chat_id, FSInputFile(zip_path, filename="bot_source_code.zip"),
                    caption="💻 Mana botning to'liq manba kodi. O'z BOT_TOKEN, ADMIN_ID va LOG_CHAT_ID qiymatlaringizni green.py ichida to'ldiring.",
                )
                return True, None
            except Exception as e:
                last_error = e
                logging.exception(f"code package send failed (attempt {attempt + 1})")
        return False, last_error


    @router.message(F.text == BUY_CODE_BUTTON_TEXT)
    async def buy_code_pressed(message: Message, state: FSMContext):
        if message.from_user.id == ADMIN_ID:
            await message.answer("✅ Siz botning egasisiz — kod bepul tayyorlanmoqda...")
            sent, last_error = await _deliver_code_package(message.bot, message.chat.id)
            if not sent:
                await message.answer(f"❌ Kodni yuborishda xatolik: {last_error}")
            return

        price = load_price("code")
        await message.bot.send_invoice(
            chat_id=message.chat.id,
            title="💻 Bot manba kodi",
            description=f"Botning to'liq manba kodi (barcha fayllar bilan), {price} ⭐",
            payload=f"code:{message.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Bot kodi", amount=price)],
        )


    # ============================================================================
    # BO'LIM 1: NAME EMOJIS
    # ============================================================================

    def build_preview():
        text = ""
        entities = []
        for key in TEMPLATE_ORDER:
            label = TEMPLATES[key]["label"]
            emoji_id = EMOJI_IDS.get(key)
            start = _utf16_len(text)
            text += PLACEHOLDER
            if emoji_id:
                entities.append(MessageEntity(
                    type="custom_emoji",
                    offset=start,
                    length=_utf16_len(PLACEHOLDER),
                    custom_emoji_id=emoji_id,
                ))
            text += f" {label}\n"
        return text, entities


    def choice_keyboard():
        buttons = [
            InlineKeyboardButton(
                text=TEMPLATES[k]["label"],
                callback_data=f"tpl:{k}"
            )
            for k in TEMPLATE_ORDER
        ]

        per_row = 4
        rows = [
            buttons[i:i + per_row]
            for i in range(0, len(buttons), per_row)
        ]

        rows.append([
            InlineKeyboardButton(
                text="Hammasi",
                callback_data="tpl:all",
                style="success"
            )
        ])

        rows.append([
            InlineKeyboardButton(
                text="⬅️ Bosh menyu",
                callback_data="backmain"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=rows)


    async def _send_name_menu(message: Message):
        text, entities = build_preview()

        await message.answer(
            text,
            entities=entities
        )

        await message.answer(
            "Qaysi birini yasaymiz?",
            reply_markup=choice_keyboard()
        )


    @router.callback_query(F.data == "section:name")
    async def section_name(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.update_data(kind="name")
        await callback.answer()
        await _send_name_menu(callback.message)


    def build_green_preview():
        """29 ta tayyor Green Emoji uchun preview: har birini haqiqiy
        custom_emoji_id orqali (rasm ko'rinishida) ko'rsatadi."""
        total = len(GREEN_EMOJI_PREVIEW_IDS)

        text = (
            f"🟢 Green Emojis — {total} ta tayyor animatsiyali "
            f"emojidan iborat to'plam:\n\n"
        )

        entities = []

        for i, emoji_id in enumerate(
            GREEN_EMOJI_PREVIEW_IDS,
            start=1
        ):
            offset = _utf16_len(text)

            text += PLACEHOLDER

            entities.append(
                MessageEntity(
                    type="custom_emoji",
                    offset=offset,
                    length=_utf16_len(PLACEHOLDER),
                    custom_emoji_id=emoji_id,
                )
            )

            text += "\n" if i % 10 == 0 else " "

        text += (
            "\n\nDavom etsangiz keyingi qadamda MATN va uning "
            "RANGINI so'raymiz, so'ng shu matn barcha 29 taga "
            "qo'shib chiqariladi."
        )

        return text, entities


    def green_start_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Shu to'plam bilan davom etish",
                callback_data="greenstart",
                style="primary"
            ),
        ], [
def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


# ============================================================================
# FSM holatlar
# ============================================================================

class Flow(StatesGroup):
    word = State()
    pack_title = State()
    pack_nick = State()


class LogoFlow(StatesGroup):
    waiting_outer = State()
    waiting_outer_hex = State()
    waiting_inner = State()
    waiting_inner_hex = State()
    waiting_logo_color = State()
    waiting_logo_color_hex = State()
    waiting_svg = State()


class GiftFlow(StatesGroup):
    waiting_amount = State()


class GreenFlow(StatesGroup):
    waiting_text = State()
    waiting_text_color = State()
    waiting_text_color_hex = State()


class AdminFlow(StatesGroup):
    add_id = State()
    remove_id = State()
    set_price = State()
    set_channel = State()
    set_support = State()
    broadcast = State()


# ============================================================================
# Bosh menyu (/start) — 2 bo'lim: Name Emojis / Logo Text Emojis
# ============================================================================

def main_section_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔤 Name Emojis", callback_data="section:name", style="primary"),
        InlineKeyboardButton(text="🖼 Logo/Text Emojis", callback_data="section:logo", style="primary"),
    ], [
        InlineKeyboardButton(text="🟢 Green Emojis", callback_data="section:green", style="primary"),
    ], [
        InlineKeyboardButton(text="🎁 Yulduz hadya qilish", callback_data="section:gift", style="primary"),
    ], [
        InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help"),
    ]])


BUY_CODE_BUTTON_TEXT = "💻 Bot kodini olish"


def persistent_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BUY_CODE_BUTTON_TEXT)]],
        resize_keyboard=True,
    )


async def _send_section_menu(message: Message):
    await message.answer("Nima yasaymiz? 👇", reply_markup=main_section_keyboard())


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    record_user(message.from_user.id)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][len("ref_"):])
            record_referral(message.from_user.id, referrer_id)
        except ValueError:
            pass

    channels = get_channels()
    if channels and not await is_subscribed(message.bot, message.from_user.id):
        await message.answer(
            "Botdan foydalanish uchun avval kanal(lar)ga a'zo bo'ling, so'ng \"Tekshirish\" tugmasini bosing:",
            reply_markup=subscribe_keyboard(channels),
        )
        return

    await message.answer("👋 Xush kelibsiz!", reply_markup=persistent_keyboard())
    await _send_section_menu(message)


@router.callback_query(F.data == "checksub")
async def check_subscription(callback: CallbackQuery):
    channels = get_channels()
    if channels and not await is_subscribed(callback.bot, callback.from_user.id):
        await callback.answer("Hali barcha kanallarga a'zo bo'lmadingiz.", show_alert=True)
        return
    await callback.answer("✅ Tasdiqlandi!")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _send_section_menu(callback.message)


@router.callback_query(F.data == "backmain")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await _send_section_menu(callback.message)


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    me = await callback.bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{callback.from_user.id}"
    credits = get_credits(callback.from_user.id)
    await callback.message.answer(
        f"🆘 Savol yoki muammo bo'lsa {get_support_contact()} ga yozing.\n\n"
        "🎁 Do'stingizni taklif qiling! U birinchi emoji/stikerini yasab bo'lgach, "
        "sizga 1 ta bepul kredit beriladi (keyingi emojingiz uchun to'lovsiz foydalanasiz).\n\n"
        f"Sizning taklif havolangiz:\n{ref_link}\n\n"
        f"💳 Hozir sizda {credits} ta bepul kredit bor."
    )
    await callback.answer()


# ============================================================================
# BO'LIM 0: YULDUZ HADYA QILISH (Telegram Stars orqali oddiy hadya)
# ============================================================================

GIFT_MIN_AMOUNT = 1
GIFT_MAX_AMOUNT = 100000


@router.callback_query(F.data == "section:gift")
async def section_gift(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(GiftFlow.waiting_amount)
    await callback.answer()
    await callback.message.answer(
        "🎁 Nechta ⭐ Stars hadya qilmoqchisiz? Sonini yozing (masalan: 100):"
    )


@router.message(GiftFlow.waiting_amount, F.text)
async def gift_got_amount(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Iltimos, faqat son yuboring (masalan: 100).")
        return
    amount = int(raw)
    if not (GIFT_MIN_AMOUNT <= amount <= GIFT_MAX_AMOUNT):
        await message.answer(
            f"Son {GIFT_MIN_AMOUNT} dan {GIFT_MAX_AMOUNT} tagacha bo'lishi kerak. Qaytadan yozing:"
        )
        return

    await state.update_data(gift_amount=amount)
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="⭐ Yulduz hadya",
        description=f"{amount} ⭐ Stars hadya qilish",
        payload=f"gift:{message.from_user.id}:{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Stars hadya", amount=amount)],
    )


@router.message(GiftFlow.waiting_amount)
async def gift_got_wrong_type(message: Message):
    await message.answer("Iltimos, faqat son yuboring (masalan: 100).")


# ============================================================================
# BOT KODINI SOTIB OLISH (pastki, doimiy tugma orqali)
# ============================================================================

async def _deliver_code_package(bot: Bot, chat_id: int) -> tuple[bool, Exception | None]:
    """bot_source_code.zip'ni yasab, bergan chat_id'ga yuboradi (kerak bo'lsa
    1 marta qayta urinib). Pullik va bepul (admin) yo'llarning ikkalasi ham
    shu funksiyani ishlatadi, shunda kod yuborish mantiqi bitta joyda qoladi."""
    last_error = None
    for attempt in range(2):
        try:
            zip_path = build_code_package()
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError("zip fayl buzilgan chiqdi, qayta yasalmoqda")
            await bot.send_document(
                chat_id, FSInputFile(zip_path, filename="bot_source_code.zip"),
                caption="💻 Mana botning to'liq manba kodi. O'z BOT_TOKEN, ADMIN_ID va LOG_CHAT_ID qiymatlaringizni green.py ichida to'ldiring.",
            )
            return True, None
        except Exception as e:
            last_error = e
            logging.exception(f"code package send failed (attempt {attempt + 1})")
    return False, last_error


@router.message(F.text == BUY_CODE_BUTTON_TEXT)
async def buy_code_pressed(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("✅ Siz botning egasisiz — kod bepul tayyorlanmoqda...")
        sent, last_error = await _deliver_code_package(message.bot, message.chat.id)
        if not sent:
            await message.answer(f"❌ Kodni yuborishda xatolik: {last_error}")
        return

    price = load_price("code")
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="💻 Bot manba kodi",
        description=f"Botning to'liq manba kodi (barcha fayllar bilan), {price} ⭐",
        payload=f"code:{message.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Bot kodi", amount=price)],
    )


# ============================================================================
# BO'LIM 1: NAME EMOJIS (so'zdan tayyor shablon ustiga yozadi)
# ============================================================================

def build_preview():
    text = ""
    entities = []
    for key in TEMPLATE_ORDER:
        label = TEMPLATES[key]["label"]
        emoji_id = EMOJI_IDS.get(key)
        start = _utf16_len(text)
        text += PLACEHOLDER
        if emoji_id:
            entities.append(MessageEntity(
                type="custom_emoji",
                offset=start,
                length=_utf16_len(PLACEHOLDER),
                custom_emoji_id=emoji_id,
            ))
        text += f" {label}\n"
    return text, entities


def choice_keyboard():
    buttons = [
        InlineKeyboardButton(
            text=TEMPLATES[k]["label"],
            callback_data=f"tpl:{k}"
        )
        for k in TEMPLATE_ORDER
    ]

    per_row = 4

    rows = [
        buttons[i:i + per_row]
        for i in range(0, len(buttons), per_row)
    ]

    rows.append([
        InlineKeyboardButton(
            text="Hammasi",
            callback_data="tpl:all",
            style="success"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Bosh menyu",
            callback_data="backmain"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_name_menu(message: Message):
    text, entities = build_preview()

    await message.answer(
        text,
        entities=entities
    )

    await message.answer(
        "Qaysi birini yasaymiz?",
        reply_markup=choice_keyboard()
    )


@router.callback_query(F.data == "section:name")
async def section_name(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(kind="name")
    await callback.answer()
    await _send_name_menu(callback.message)


def build_green_preview():
    """29 ta tayyor Green Emoji uchun preview: har birini haqiqiy
    custom_emoji_id orqali (rasm ko'rinishida) ko'rsatadi."""
    total = len(GREEN_EMOJI_PREVIEW_IDS)

    text = (
        f"🟢 Green Emojis — {total} ta tayyor animatsiyali "
        f"emojidan iborat to'plam:\n\n"
    )

    entities = []

    for i, emoji_id in enumerate(
        GREEN_EMOJI_PREVIEW_IDS,
        start=1
    ):
        offset = _utf16_len(text)

        text += PLACEHOLDER

        entities.append(
            MessageEntity(
                type="custom_emoji",
                offset=offset,
                length=_utf16_len(PLACEHOLDER),
                custom_emoji_id=emoji_id,
            )
        )

        text += "\n" if i % 10 == 0 else " "

    text += (
        "\n\nDavom etsangiz keyingi qadamda MATN va uning "
        "RANGINI so'raymiz, so'ng shu matn barcha 29 taga "
        "qo'shib chiqariladi."
    )

    return text, entities


def green_start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Shu to'plam bilan davom etish",
            callback_data="greenstart",
            style="primary"
        ),
    ], [
        InlineKeyboardButton(
            text="⬅️ Bosh menyu",
            callback_data="backmain"
        ),
    ]])


@router.callback_query(F.data == "section:green")
async def section_green(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(kind="green")
    await callback.answer()

    text, entities = build_green_preview()

    await callback.message.answer(
        text,
        entities=entities,
        reply_markup=green_start_keyboard()
    )


@router.callback_query(F.data == "greenstart")
async def green_start(callback: CallbackQuery, state: FSMContext):
    await state.update_data(kind="green")
    await state.set_state(GreenFlow.waiting_text)
    await callback.answer()

    await callback.message.answer(
        f"✍️ Matn yozing (maksimum {MAX_LEN} ta harf, masalan: Salom):"
    )


@router.message(GreenFlow.waiting_text, F.text)
async def green_got_text(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text or len(text) > MAX_LEN:
        await message.answer(
            f"Matn 1 dan {MAX_LEN} tagacha harf bo'lishi kerak. "
            f"Qaytadan yozing:"
        )
        return

    await state.update_data(
        green_text=text
    )

    await state.set_state(
        GreenFlow.waiting_text_color
    )

    await message.answer(
        "🎨 Endi matn rangini tanlang:",
        reply_markup=color_keyboard("greentext")
    )


@router.message(GreenFlow.waiting_text)
async def green_got_text_wrong_type(message: Message):
    await message.answer(
        "Iltimos, shunchaki matn yozing (masalan: Salom)."
    )


async def _green_generate_and_stage(
    message_or_callback_msg: Message,
    state: FSMContext,
    text_hex: str
):
    """Tanlangan matn+rangni 29 ta Green Emoji shabloniga qo'shib,
    natija fayllarini diskka yozadi va paths/nick'ni FSM'ga joylaydi."""
    data = await state.get_data()

    text = data.get(
        "green_text",
        ""
    )

    user_id = message_or_callback_msg.chat.id

    out_dir = os.path.join(
        os.path.dirname(__file__),
        "output"
    )

    os.makedirs(
        out_dir,
        exist_ok=True
    )

    paths = []

    for i, template_path in enumerate(
        GREEN_EMOJI_TEMPLATE_PATHS,
        start=1
    ):
        tgs_bytes, _ = logo_engine.add_text_overlay_to_tgs(
            template_path,
            text,
            text_hex
        )

        out_path = os.path.join(
            out_dir,
            f"{user_id}_green_{i:03d}.tgs"
        )

        with open(
            out_path,
            "wb"
        ) as f:
            f.write(tgs_bytes)

        paths.append(out_path)

    nick = _random_nick()

    await state.update_data(
        paths=paths,
        nick=nick,
        kind="green"
    )


@router.callback_query(
    GreenFlow.waiting_text_color,
    F.data.startswith("greentext:")
)
async def green_text_color_chosen(
    callback: CallbackQuery,
    state: FSMContext
):
    value = callback.data.split(
        ":",
        1
    )[1]

    if value == "custom":
        await state.set_state(
            GreenFlow.waiting_text_color_hex
        )

        await callback.answer()

        await callback.message.answer(
            "Matn rangini #RRGGBB ko'rinishida yuboring. "
            "Masalan: #FFFFFF"
        )

        return

    await callback.answer(
        f"Matn rangi: {value}"
    )

    try:
        await _green_generate_and_stage(
            callback.message,
            state,
            value
        )

    except Exception as e:
        await callback.message.answer(
            f"❌ Xatolik: {e}\n\n"
            f"Boshqa matn/rang bilan qaytadan urinib ko'ring."
        )
        return

    await state.set_state(
        Flow.pack_title
    )

    await callback.message.answer(
        "To'plam nomini yozing "
        "(bu Telegram'da ko'rinadigan sarlavha bo'ladi):"
    )


@router.message(
    GreenFlow.waiting_text_color_hex,
    F.text
)
async def green_text_color_hex(
    message: Message,
    state: FSMContext
):
    hexcode = _normalize_hex(
        message.text or ""
    )

    if not hexcode:
        await message.answer(
            "Noto'g'ri format. Masalan: #FFFFFF ko'rinishida yuboring."
        )
        return

    try:
        await _green_generate_and_stage(
            message,
            state,
            hexcode
        )

    except Exception as e:
        await message.answer(
            f"❌ Xatolik: {e}\n\n"
            f"Boshqa matn/rang bilan qaytadan urinib ko'ring."
        )
        return

    await state.set_state(
        Flow.pack_title
    )

    await message.answer(
        f"✅ Matn rangi: {hexcode}\n\n"
        f"To'plam nomini yozing "
        f"(bu Telegram'da ko'rinadigan sarlavha bo'ladi):"
    )


@router.callback_query(F.data.startswith("tpl:"))
async def choose_template(
    callback: CallbackQuery,
    state: FSMContext
):
    key = callback.data.split(
        ":"
    )[1]

    await state.update_data(
        template=key,
        kind="name"
    )

    await state.set_state(
        Flow.word
    )

    await callback.message.answer(
        f"So'zni yozing (maksimum {MAX_LEN} ta harf):"
    )

    await callback.answer()


async def _render_sticker(
    message: Message,
    template_key: str,
    word: str
) -> str:
    cfg = TEMPLATES[template_key]

    lottie = render_template(
        cfg,
        word
    )

    out_dir = os.path.join(
        os.path.dirname(__file__),
        "output"
    )

    os.makedirs(
        out_dir,
        exist_ok=True
    )

    out_path = os.path.join(
        out_dir,
        f"{message.from_user.id}_{template_key}.tgs"
    )

    save_as_tgs(
        lottie,
        out_path
    )

    return out_path


def pack_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="💎 Premium custom emoji pack",
            callback_data="packtype:emoji",
            style="primary"
        ),
        InlineKeyboardButton(
            text="🖼 Stickers pack",
            callback_data="packtype:sticker",
            style="primary"
        ),
    ]])


@router.message(Flow.word)
async def got_word(
    message: Message,
    state: FSMContext
):
    word = (message.text or "").strip()

    if not word or len(word) > MAX_LEN:
        await message.answer(
            f"So'z 1 dan {MAX_LEN} tagacha harf bo'lishi kerak. "
            f"Qaytadan yozing:"
        )
        return

    data = await state.get_data()

    template_key = data.get(
        "template",
        "millioner"
    )

    paths = []

    if template_key == "all":
        for key in TEMPLATE_ORDER:
            paths.append(
                await _render_sticker(
                    message,
                    key,
                    word
                )
            )

    else:
        paths.append(
            await _render_sticker(
                message,
                template_key,
                word
            )
        )

    nick = _random_nick()

    await state.update_data(
        paths=paths,
        nick=nick
    )

    await state.set_state(
        Flow.pack_title
    )

    await message.answer(
        "To'plam nomini yozing "
        "(bu Telegram'da ko'rinadigan sarlavha bo'ladi):"
    )


PACK_TITLE_MAX_LEN = 64


@router.message(
    Flow.pack_title,
    F.text
)
async def got_pack_title(
    message: Message,
    state: FSMContext
):
    title = (message.text or "").strip()

    if not title or len(title) > PACK_TITLE_MAX_LEN:
        await message.answer(
            f"Nom 1 dan {PACK_TITLE_MAX_LEN} tagacha belgidan "
            f"iborat bo'lishi kerak. Qaytadan yozing:"
        )
        return

    await state.update_data(
        title=title
    )

    data = await state.get_data()

    kind = data.get(
        "kind",
        "name"
    )

    if kind == "logo":
        await _render_and_stage_logo_pack(
            message,
            state
        )

        await _offer_payment(
            message,
            state,
            message.from_user
        )

        return

    await message.answer(
        "Qayerga qo'shamiz?",
        reply_markup=pack_type_keyboard()
    )


@router.message(
    Flow.pack_nick,
    F.text
)
async def got_pack_nick(
    message: Message,
    state: FSMContext
):
    # No longer reachable in the normal flow (nick is auto-generated),
    # kept only as a safety net in case old FSM state from a previous
    # version is still stored for a user.

    nick = (message.text or "").strip()

    if not nick:
        await message.answer(
            "Nikbo'sh bo'lmasin. Qaytadan yozing:"
        )
        return

    await state.update_data(
        nick=nick
    )

    await message.answer(
        "Qayerga qo'shamiz?",
        reply_markup=pack_type_keyboard()
    )


async def _finalize_pack(
    bot: Bot,
    chat_id: int,
    paths: list[str],
    nick: str,
    pack_kind: str,
    user=None,
    title: str | None = None,
):
    total = len(paths)

    status = await bot.send_message(
        chat_id,
        f"⏳ Tayyorlanmoqda: 0/{total}"
    )

    owner_id = (
        user.id
        if user is not None
        else ADMIN_ID
    )

    pack_name = await add_stickers_to_pack(
        bot,
        paths,
        nick,
        pack_kind,
        progress_message=status,
        owner_id=owner_id,
        title=title,
    )

    if pack_name:
        link = (
            "addemoji"
            if pack_kind == "emoji"
            else "addstickers"
        )

        url = (
            f"https://t.me/{link}/{pack_name}"
        )

        try:
            await status.edit_text(
                f"✅ Tayyor! Mana emojingiz, "
                f"to'lov uchun rahmat 🙏\n{url}"
            )

        except Exception:
            await bot.send_message(
                chat_id,
                f"✅ Tayyor! Mana emojingiz, "
                f"to'lov uchun rahmat 🙏\n{url}"
            )

        try:
            record_pack_created(
                owner_id,
                getattr(user, "username", None),
            )

            await reward_referral_if_pending(
                bot,
                owner_id
            )

        except Exception:
            pass

    else:
        try:
            await status.edit_text(
                "❌ To'plam yaratishda xatolik yuz berdi."
            )

        except Exception:
            await bot.send_message(
                chat_id,
                "❌ To'plam yaratishda xatolik yuz berdi."
            )


@router.callback_query(
    F.data.startswith("packtype:")
)
async def choose_pack_type(
    callback: CallbackQuery,
    state: FSMContext
):
    pack_kind = callback.data.split(
        ":",
        1
    )[1]

    data = await state.get_data()

    paths = data.get(
        "paths",
        []
    )

    nick = data.get(
        "nick"
    )

    title = data.get(
        "title"
    )

    if not paths or not nick:
        await callback.answer(
            "Sessiya muddati tugagan. Qaytadan boshlang.",
            show_alert=True
        )
        await state.clear()
        return

    await state.update_data(
        pack_kind=pack_kind
    )

    await callback.answer()

    await _offer_payment(
        callback.message,
        state,
        callback.from_user
    )


async def _offer_payment(
    message: Message,
    state: FSMContext,
    user
):
    data = await state.get_data()

    kind = data.get(
        "kind",
        "name"
    )

    pack_kind = data.get(
        "pack_kind",
        "emoji"
    )

    # Logo/Name/Green uchun umumiy narx
    price = load_price(
        kind
    )

    credits = get_credits(
        user.id
    )

    keyboard_rows = []

    if credits > 0:
        keyboard_rows.append([
            InlineKeyboardButton(
                text=f"🎟 1 ta bepul kreditdan foydalanish ({credits} mavjud)",
                callback_data="pay:credit"
            )
        ])

    keyboard_rows.append([
        InlineKeyboardButton(
            text=f"⭐ {price} Stars to'lash",
            callback_data="pay:stars"
        )
    ])

    keyboard_rows.append([
        InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data="backmain"
        )
    ])

    await message.answer(
        f"💰 Narxi: {price} ⭐\n\n"
        "To'lov usulini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard_rows
        )
    )


@router.callback_query(
    F.data == "pay:credit"
)
async def pay_with_credit(
    callback: CallbackQuery,
    state: FSMContext
):
    if not use_credit(
        callback.from_user.id
    ):
        await callback.answer(
            "Sizda bepul kredit qolmagan.",
            show_alert=True
        )
        return

    data = await state.get_data()

    paths = data.get(
        "paths",
        []
    )

    nick = data.get(
        "nick"
    )

    pack_kind = data.get(
        "pack_kind",
        "emoji"
    )

    title = data.get(
        "title"
    )

    if not paths or not nick:
        await callback.answer(
            "Sessiya muddati tugagan.",
            show_alert=True
        )
        await state.clear()
        return

    await callback.answer(
        "🎟 Kredit ishlatildi!"
    )

    await _finalize_pack(
        callback.bot,
        callback.message.chat.id,
        paths,
        nick,
        pack_kind,
        callback.from_user,
        title
    )

    await state.clear()


@router.callback_query(
    F.data == "pay:stars"
)
async def pay_with_stars(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    kind = data.get(
        "kind",
        "name"
    )

    price = load_price(
        kind
    )

    await callback.answer()

    await callback.bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=f"{_section_label(kind)}",
        description=f"{_section_label(kind)} yaratish — {price} ⭐",
        payload=f"pack:{callback.from_user.id}:{kind}:{price}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"{_section_label(kind)}",
                amount=price
            )
        ],
    )


@router.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):
    await query.answer(
        ok=True
    )


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    state: FSMContext
):
    payment = message.successful_payment

    payload = payment.invoice_payload

    # Stars orqali oddiy hadya
    if payload.startswith("gift:"):
        parts = payload.split(":")

        try:
            amount = int(parts[-1])
        except ValueError:
            amount = payment.total_amount

        await message.answer(
            f"🎁 {amount} ⭐ Stars hadya qilindi. Rahmat!"
        )

        await state.clear()
        return

    # Bot source kodi xaridi
    if payload.startswith("code:"):
        price = payment.total_amount

        record_stars_spent(
            message.from_user.id,
            message.from_user.username,
            price
        )

        sent, last_error = await _deliver_code_package(
            message.bot,
            message.chat.id
        )

        if sent:
            await message.answer(
                "✅ To'lov qabul qilindi. "
                "Botning manba kodi yuqorida yuborildi."
            )
        else:
            await message.answer(
                f"❌ To'lov qabul qilindi, lekin kodni yuborishda "
                f"xatolik yuz berdi: {last_error}"
            )

        await state.clear()
        return

    # Oddiy emoji/logo/green xaridi
    if payload.startswith("pack:"):
        data = await state.get_data()

        paths = data.get(
            "paths",
            []
        )

        nick = data.get(
            "nick"
        )

        pack_kind = data.get(
            "pack_kind",
            "emoji"
        )

        title = data.get(
            "title"
        )

        if not paths or not nick:
            await message.answer(
                "❌ To'lov qabul qilindi, "
                "lekin yaratish sessiyasi topilmadi. "
                "Admin bilan bog'laning."
            )
            await state.clear()
            return

        record_stars_spent(
            message.from_user.id,
            message.from_user.username,
            payment.total_amount
        )

        await _finalize_pack(
            message.bot,
            message.chat.id,
            paths,
            nick,
            pack_kind,
            message.from_user,
            title
        )

        await state.clear()
        return

    await message.answer(
        "✅ To'lov qabul qilindi."
    )

    await state.clear()