"""
green.py — Birlashtirilgan bot: "Name Emojis" (newbot_fixed) + "Logo/Text Emojis"
(tgs_make_bot) bitta botda.

/start bosilganda 2 ta bo'lim ko'rsatiladi:
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
    fonts/*.ttf            <- Har ikkala bo'lim uchun shriftlar
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
    return {"logo": "Logo/Text emoji", "green": "Green Emojis", "name": "Name emoji"}.get(kind, "Name emoji")


ADMIN_ID = 0  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing  # <-- shu yerga o'zingizning Telegram user_id'ingizni yozing
LOG_CHAT_ID = 0  # <-- shu yerga o'z log kanalingizning id'sini yozing  # <-- shu yerga o'z log kanalingizning id'sini yozing
ALLOWED_FILE = os.path.join(os.path.dirname(__file__), "allowed_users.json")
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
EMOJI_PACK_FILE = os.path.join(os.path.dirname(__file__), "emoji_pack.json")
PRICE_FILES = {
    "name": os.path.join(os.path.dirname(__file__), "price_name.json"),
    "logo": os.path.join(os.path.dirname(__file__), "price_logo.json"),
    "code": os.path.join(os.path.dirname(__file__), "price_code.json"),
    "green": os.path.join(os.path.dirname(__file__), "price_green.json"),
}

# ---------- "🟢 Green Emojis" bo'limi: tayyor (o'zgarmas) 29 ta animatsiyali
# emoji to'plami. Bular boshqa 103 ta "Logo/Text" shabloni kabi rangi/matni
# almashtiriladigan bo'sh qolip EMAS — Salescopys pack'idan olingan tayyor,
# to'liq animatsiyalar, shuning uchun alohida papkada (green_emojis/*.tgs)
# saqlanadi va foydalanuvchi tanlagach o'zgarishsiz, to'liq 29 tasi birga
# pack sifatida qo'shiladi.
GREEN_EMOJI_DIR = os.path.join(os.path.dirname(__file__), "green_emojis")
# Bular tayyor animatsiyalarning XOM (siqilmagan) Lottie JSON'lari — 103 ta
# Logo/Text shablonidan farqli o'laroq, "Svg Group 0" joyi yo'q, shuning
# uchun rang emas, faqat matn (add_text_overlay_to_tgs orqali) qo'shiladi.
GREEN_EMOJI_TEMPLATE_PATHS = [
    os.path.join(GREEN_EMOJI_DIR, f"{i:03d}.json") for i in range(1, 30)
]
# Har bir fayl (001..029.tgs) uchun preview sifatida ko'rsatiladigan haqiqiy
# custom_emoji_id (@kxalil ning "Salescopys" pack'idan, xuddi shu tartibda).
GREEN_EMOJI_PREVIEW_IDS = [
    "5449413509702001244", "5447566038109560980", "5447363161034367576",
    "5447583398367370838", "5447175999244507666", "5447380731745575376",
    "5447113975621794813", "5447180062283571572", "5449389045568284712",
    "5449439532908851080", "5447582251611105317", "5449782206874559979",
    "5447120095950185848", "5449592751572167022", "5447233822389217314",
    "5447570921487379718", "5447188351570454981", "5449492760438547397",
    "5447224918922010955", "5447352084313712339", "5449864369598933552",
    "5447264823463162476", "5447266133428185558", "5447304534730776164",
    "5449821239537345805", "5447356611209242428", "5447416573247660061",
    "5447418540342682118", "5449719758050075099",
]
CREDITS_FILE = os.path.join(os.path.dirname(__file__), "credits.json")
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")
REFUND_REQUESTS_FILE = os.path.join(os.path.dirname(__file__), "refund_requests.json")
REFERRALS_FILE = os.path.join(os.path.dirname(__file__), "referrals.json")
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
DEFAULT_PRICE_STARS = 15
DEFAULT_CODE_PRICE_STARS = 5000
# Placeholder shown to anyone running a copy of this code who hasn't set
# their own support contact yet (settings.json isn't included in the sold
# .zip, so buyers never see the seller's real contact here).
DEFAULT_SUPPORT_CONTACT = "@your_support_username"
LOGO_PAGE_SIZE = 10
TOTAL_LOGO_TEMPLATES = 103

logging.basicConfig(level=logging.INFO)
router = Router()


# ============================================================================
# Umumiy: pack saqlash, ruxsatlar, foydalanuvchilar, narx, kreditlar, referal,
# majburiy kanallar — ikkala bo'lim (Name / Logo) uchun ham baravar ishlatiladi.
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
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", nick)
    return cleaned or "pack"


async def add_stickers_to_pack(
    bot: Bot, sticker_paths: list[str], nick: str, pack_kind: str, progress_message: Message | None = None,
    owner_id: int | None = None, title: str | None = None,
):
    """Create or reuse a sticker set for this nick+kind and add all the
    given stickers to it. pack_kind is 'emoji' (premium custom emoji pack)
    or 'sticker' (regular stickers pack). Returns the pack name, or None
    if it failed.

    owner_id is the Telegram user who ordered the pack - the set is
    created under their account (so it shows up in their own sticker/emoji
    catalog in Telegram), not the bot admin's. Falls back to ADMIN_ID if
    no user is available (e.g. an internal/admin-triggered call).

    Telegram enforces its own rate limit on sticker-set edits: if we hit
    it, the API raises TelegramRetryAfter rather than adding the sticker.
    We catch it per-sticker, sleep for the time Telegram asks for, and
    retry that same sticker - so the pack always finishes once the wait
    is over, instead of stopping partway.

    Progress is shown by editing a single message in place (not by
    sending a new message per sticker), so the chat doesn't get flooded
    with one line per item."""
    from aiogram.types import InputSticker

    sticker_type = "custom_emoji" if pack_kind == "emoji" else "regular"
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
            name = f"{_safe_nick(nick)}_{owner_id}_by_{me.username}"

        for i, sticker_path in enumerate(sticker_paths):
            item = InputSticker(sticker=FSInputFile(sticker_path), format="animated", emoji_list=["🙂"])
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
                            await bot.add_sticker_to_set(user_id=owner_id, name=name, sticker=item)
                        packs[storage_key] = name
                        save_packs(packs)
                    else:
                        await bot.add_sticker_to_set(user_id=owner_id, name=name, sticker=item)
                    break
                except TelegramRetryAfter as e:
                    await update(
                        f"⏳ Telegram cheklovi sababli {e.retry_after}s kutyapmiz "
                        f"({i}/{total} qo'shildi), keyin davom etamiz..."
                    )
                    await asyncio.sleep(e.retry_after + 1)
                    continue

            await update(f"⏳ Tayyorlanmoqda: {i + 1}/{total} qo'shildi")
        return name
    except Exception as e:
        logging.warning(f"pack update failed: {e}")
        return None


def load_allowed() -> set[int]:
    if not os.path.exists(ALLOWED_FILE):
        return set()
    try:
        with open(ALLOWED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_allowed(ids: set[int]):
    with open(ALLOWED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def is_free_user(user_id: int) -> bool:
    return user_id == ADMIN_ID or user_id in load_allowed()


def load_users() -> set[int]:
    if not os.path.exists(USERS_FILE):
        return set()
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_users(ids: set[int]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f)


def record_user(user_id: int):
    """Remember that this user has started the bot, so broadcasts can reach them."""
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        save_users(users)


def load_price(kind: str = "name") -> int:
    path = PRICE_FILES.get(kind, PRICE_FILES["name"])
    default = DEFAULT_CODE_PRICE_STARS if kind == "code" else DEFAULT_PRICE_STARS
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("stars", default))
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return default


def save_price(kind: str, stars: int):
    path = PRICE_FILES.get(kind, PRICE_FILES["name"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"stars": stars}, f)


# ---------- Bot manba kodini sotish uchun toza (sanitized) .zip paket ----------

_CODE_PACKAGE_DIR = os.path.join(os.path.dirname(__file__), "output")
_CODE_PACKAGE_PATH = os.path.join(_CODE_PACKAGE_DIR, "bot_source_code.zip")

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
            "🎉 Siz taklif qilgan foydalanuvchi birinchi packini yaratdi! "
            "Sizga 1 ta bepul kredit berildi."
        )
    except Exception:
        pass


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
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get_support_contact() -> str:
    settings = load_settings()
    return settings.get("support_contact", DEFAULT_SUPPORT_CONTACT)


def set_support_contact(value: str):
    settings = load_settings()
    settings["support_contact"] = value
    save_settings(settings)


# ---------- Majburiy kanal ----------

def get_required_channels() -> list[str]:
    settings = load_settings()
    channels = settings.get("required_channels", [])
    if isinstance(channels, str):
        channels = [channels]
    return [str(x).strip() for x in channels if str(x).strip()]


def save_required_channels(channels: list[str]):
    settings = load_settings()
    settings["required_channels"] = channels
    save_settings(settings)


async def check_required_channels(bot: Bot, user_id: int) -> tuple[bool, list[str]]:
    """Return (ok, missing_channels). A channel is considered joined if
    Telegram reports the user as creator/administrator/member. If a channel
    cannot be checked (e.g. the bot is not an admin/member), it is skipped
    rather than blocking every user."""
    missing = []

    for channel in get_required_channels():
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in {"creator", "administrator", "member"}:
                missing.append(channel)
        except Exception as e:
            logging.warning("Required channel check failed for %s: %s", channel, e)

    return not missing, missing


def required_channels_keyboard(channels: list[str]) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        username = channel.lstrip("@")

        rows.append([
            InlineKeyboardButton(
                text=f"📢 {channel}",
                url=f"https://t.me/{username}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="✅ Tekshirish",
            callback_data="check_subscription"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ensure_subscription(
    bot: Bot,
    message: Message,
) -> bool:
    channels = get_required_channels()

    if not channels:
        return True

    ok, missing = await check_required_channels(
        bot,
        message.from_user.id
    )

    if ok:
        return True

    await message.answer(
        "🔒 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
        reply_markup=required_channels_keyboard(missing)
    )

    return False


# ---------- Umumiy keyboardlar ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔤 Name Emojis",
                    callback_data="section:name"
                ),
                InlineKeyboardButton(
                    text="🖼 Logo/Text Emojis",
                    callback_data="section:logo"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🟢 Green Emojis",
                    callback_data="section:green"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Profil",
                    callback_data="profile"
                ),
                InlineKeyboardButton(
                    text="🎁 Referal",
                    callback_data="referral"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Yordam",
                    callback_data="help"
                )
            ],
        ]
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )


# ---------- FSM ----------

class NameStates(StatesGroup):
    waiting_text = State()
    waiting_template = State()


class LogoStates(StatesGroup):
    waiting_text = State()
    waiting_template = State()


class GreenStates(StatesGroup):
    waiting_text = State()


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_price = State()
    waiting_support = State()
    waiting_channel = State()


# ---------- Start ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    if not message.from_user:
        return

    user_id = message.from_user.id
    record_user(user_id)

    args = message.text.split(maxsplit=1)

    if len(args) > 1:
        payload = args[1].strip()

        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload[4:])
                record_referral(user_id, referrer_id)
            except ValueError:
                pass

    bot = message.bot

    if not await ensure_subscription(bot, message):
        return

    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text(
        "🏠 Asosiy menyu:",
        reply_markup=main_menu_keyboard()
    )

    await callback.answer()


# ---------- Subscription ----------

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(
    callback: CallbackQuery
):
    bot = callback.bot

    if not callback.from_user:
        return

    ok, missing = await check_required_channels(
        bot,
        callback.from_user.id
    )

    if not ok:
        await callback.answer(
            "❌ Hali barcha kanallarga obuna bo'lmagansiz.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "✅ Obuna tasdiqlandi!\n\n"
        "🏠 Asosiy menyu:",
        reply_markup=main_menu_keyboard()
    )

    await callback.answer()


# ---------- Section ----------

@router.callback_query(F.data.startswith("section:"))
async def section_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    if not callback.from_user:
        return

    bot = callback.bot

    ok, _ = await check_required_channels(
        bot,
        callback.from_user.id
    )

    if not ok:
        await callback.message.edit_text(
            "🔒 Avval majburiy kanallarga obuna bo'ling.",
            reply_markup=required_channels_keyboard(
                get_required_channels()
            )
        )
        await callback.answer()
        return

    kind = callback.data.split(":", 1)[1]

    await state.clear()

    if kind == "name":
        await state.set_state(NameStates.waiting_text)

        await callback.message.edit_text(
            "🔤 <b>Name Emojis</b>\n\n"
            f"12 tagacha belgi yuboring.\n"
            f"Masalan: <code>XAFIZULLO</code>",
            reply_markup=back_to_menu_keyboard()
        )

    elif kind == "logo":
        await state.set_state(LogoStates.waiting_text)

        await callback.message.edit_text(
            "🖼 <b>Logo/Text Emojis</b>\n\n"
            "Emoji ustiga yoziladigan matnni yuboring.",
            reply_markup=back_to_menu_keyboard()
        )

    elif kind == "green":
        await state.set_state(GreenStates.waiting_text)

        await callback.message.edit_text(
            "🟢 <b>Green Emojis</b>\n\n"
            "Emoji ustiga yoziladigan matnni yuboring.",
            reply_markup=back_to_menu_keyboard()
        )

    await callback.answer()


# ============================================================================
# NAME EMOJIS
# ============================================================================

@router.message(NameStates.waiting_text)
async def name_receive_text(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "❌ Iltimos, matn yuboring."
        )
        return

    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Matn bo'sh bo'lmasligi kerak."
        )
        return

    if len(text) > MAX_LEN:
        await message.answer(
            f"❌ Maksimal uzunlik: {MAX_LEN} ta belgi."
        )
        return

    await state.update_data(text=text)

    await state.set_state(
        NameStates.waiting_template
    )

    keyboard = []

    for template_id in TEMPLATE_ORDER:
        emoji_id = EMOJI_IDS.get(template_id)

        if emoji_id:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"🔹 {template_id}",
                    callback_data=f"name_template:{template_id}"
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga",
            callback_data="back_to_menu"
        )
    ])

    await message.answer(
        "🎨 Shablonni tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )


@router.callback_query(
    F.data.startswith("name_template:")
)
async def name_template_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    text = data.get("text")

    if not text:
        await callback.answer(
            "❌ Matn topilmadi. Qaytadan boshlang.",
            show_alert=True
        )
        return

    template_id = callback.data.split(
        ":",
        1
    )[1]

    if template_id not in TEMPLATES:
        await callback.answer(
            "❌ Shablon topilmadi.",
            show_alert=True
        )
        return

    price = load_price("name")

    if not is_free_user(callback.from_user.id):
        if get_credits(callback.from_user.id) <= 0:
            await callback.message.edit_text(
                f"💳 Ushbu pack narxi: <b>{price} Stars</b>\n\n"
                "Davom etish uchun to'lov qiling.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"⭐ {price} Stars",
                                callback_data=f"buy_name:{template_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="⬅️ Orqaga",
                                callback_data="back_to_menu"
                            )
                        ]
                    ]
                )
            )

            await callback.answer()
            return

    await callback.message.edit_text(
        "⏳ Tayyorlanmoqda..."
    )

    try:
        output_dir = os.path.join(
            os.path.dirname(__file__),
            "output"
        )

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        safe_text = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            text
        ) or "emoji"

        output_path = os.path.join(
            output_dir,
            f"{safe_text}_{template_id}.tgs"
        )

        render_template(
            template_id,
            text,
            output_path
        )

        pack_name = await add_stickers_to_pack(
            callback.bot,
            [output_path],
            safe_text,
            "emoji",
            progress_message=callback.message,
            owner_id=callback.from_user.id,
            title=f"{text} — Name Emoji"
        )

        if not pack_name:
            await callback.message.edit_text(
                "❌ Pack yaratishda xatolik yuz berdi."
            )
            return

        record_pack_created(
            callback.from_user.id,
            callback.from_user.username
        )

        await callback.message.edit_text(
            "✅ <b>Name Emoji tayyor!</b>\n\n"
            f"🔤 Matn: <code>{text}</code>\n"
            f"🎨 Shablon: {template_id}\n\n"
            f"📦 Pack nomi:\n<code>{pack_name}</code>",
            reply_markup=back_to_menu_keyboard()
        )

        if not is_free_user(callback.from_user.id):
            use_credit(callback.from_user.id)

        await reward_referral_if_pending(
            callback.bot,
            callback.from_user.id
        )

    except Exception as e:
        logging.exception(
            "Name emoji generation failed"
        )

        await callback.message.edit_text(
            "❌ Xatolik yuz berdi.\n\n"
            f"<code>{e}</code>",
            reply_markup=back_to_menu_keyboard()
        )

    await callback.answer()
# ============================================================================
# LOGO / TEXT EMOJIS
# ============================================================================

@router.callback_query(F.data.startswith("buy_name:"))
async def buy_name_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    template_id = callback.data.split(":", 1)[1]

    price = load_price("name")

    await callback.message.edit_text(
        "💳 <b>To'lov</b>\n\n"
        f"🔤 Name Emoji pack narxi: <b>{price} Stars</b>\n\n"
        "To'lovni amalga oshirish uchun quyidagi tugmani bosing.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⭐ {price} Stars",
                        callback_data=f"pay_name:{template_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.callback_query(F.data.startswith("pay_name:"))
async def pay_name_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    template_id = callback.data.split(":", 1)[1]

    price = load_price("name")

    await state.update_data(
        pending_purchase={
            "kind": "name",
            "template_id": template_id,
            "price": price,
        }
    )

    prices = [
        LabeledPrice(
            label="Name Emoji",
            amount=price
        )
    ]

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Name Emoji",
        description="Animatsiyali Name Emoji pack yaratish",
        payload=f"name:{template_id}:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(
    query: PreCheckoutQuery
):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    state: FSMContext
):
    payment = message.successful_payment

    if not payment:
        return

    payload = payment.invoice_payload

    parts = payload.split(":")

    if len(parts) < 2:
        return

    kind = parts[0]

    if kind == "name":
        template_id = parts[1]

        await state.update_data(
            paid=True,
            paid_kind="name",
            paid_template_id=template_id,
        )

        record_stars_spent(
            message.from_user.id,
            message.from_user.username,
            payment.total_amount
        )

        await message.answer(
            "✅ To'lov muvaffaqiyatli amalga oshirildi!\n\n"
            "Endi Name Emoji yaratishingiz mumkin."
        )

        await state.set_state(
            NameStates.waiting_text
        )

        await message.answer(
            "🔤 Name Emoji uchun matn yuboring:"
        )


# ============================================================================
# LOGO / TEXT EMOJIS
# ============================================================================

@router.message(LogoStates.waiting_text)
async def logo_receive_text(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "❌ Iltimos, matn yuboring."
        )
        return

    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Matn bo'sh bo'lmasligi kerak."
        )
        return

    if len(text) > MAX_LEN:
        await message.answer(
            f"❌ Maksimal uzunlik: {MAX_LEN} ta belgi."
        )
        return

    await state.update_data(
        text=text
    )

    await state.set_state(
        LogoStates.waiting_template
    )

    keyboard = []

    for page in range(
        (TOTAL_LOGO_TEMPLATES + LOGO_PAGE_SIZE - 1)
        // LOGO_PAGE_SIZE
    ):
        start = page * LOGO_PAGE_SIZE
        end = min(
            start + LOGO_PAGE_SIZE,
            TOTAL_LOGO_TEMPLATES
        )

        keyboard.append([
            InlineKeyboardButton(
                text=f"🖼 {start + 1}-{end}",
                callback_data=f"logo_page:{page}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga",
            callback_data="back_to_menu"
        )
    ])

    await message.answer(
        "🖼 <b>Logo/Text Emoji</b>\n\n"
        "Kerakli shablonlar sahifasini tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )


@router.callback_query(
    F.data.startswith("logo_page:")
)
async def logo_page_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    page = int(
        callback.data.split(":", 1)[1]
    )

    start = page * LOGO_PAGE_SIZE

    end = min(
        start + LOGO_PAGE_SIZE,
        TOTAL_LOGO_TEMPLATES
    )

    keyboard = []

    for index in range(start, end):
        template_id = index + 1

        emoji_id = LOGO_TEMPLATE_EMOJI_IDS.get(
            template_id
        )

        text = f"🖼 {template_id}"

        if emoji_id:
            text += " 🔹"

        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"logo_template:{template_id}"
            )
        ])

    if page > 0:
        keyboard.append([
            InlineKeyboardButton(
                text="⬅️ Oldingi",
                callback_data=f"logo_page:{page - 1}"
            )
        ])

    if end < TOTAL_LOGO_TEMPLATES:
        keyboard.append([
            InlineKeyboardButton(
                text="➡️ Keyingi",
                callback_data=f"logo_page:{page + 1}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga",
            callback_data="section:logo"
        )
    ])

    await callback.message.edit_text(
        f"🖼 Shablonlar: {start + 1}–{end}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("logo_template:")
)
async def logo_template_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    text = data.get("text")

    if not text:
        await callback.answer(
            "❌ Matn topilmadi.",
            show_alert=True
        )
        return

    template_id = int(
        callback.data.split(":", 1)[1]
    )

    price = load_price("logo")

    if (
        not is_free_user(callback.from_user.id)
        and get_credits(callback.from_user.id) <= 0
    ):
        await callback.message.edit_text(
            f"💳 Logo/Text Emoji pack narxi: "
            f"<b>{price} Stars</b>\n\n"
            "Davom etish uchun to'lov qiling.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"⭐ {price} Stars",
                            callback_data=f"buy_logo:{template_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Orqaga",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
        )

        await callback.answer()
        return

    await generate_logo_pack(
        callback,
        state,
        text,
        template_id
    )


async def generate_logo_pack(
    callback: CallbackQuery,
    state: FSMContext,
    text: str,
    template_id: int
):
    await callback.message.edit_text(
        "⏳ Logo/Text Emoji tayyorlanmoqda..."
    )

    try:
        output_dir = os.path.join(
            os.path.dirname(__file__),
            "output"
        )

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        safe_text = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            text
        ) or "emoji"

        json_path = os.path.join(
            os.path.dirname(__file__),
            "templates_tgs",
            f"{template_id:03d}.json"
        )

        output_path = os.path.join(
            output_dir,
            f"{safe_text}_logo_{template_id}.tgs"
        )

        logo_engine.render_logo_template(
            json_path,
            text,
            output_path
        )

        pack_name = await add_stickers_to_pack(
            callback.bot,
            [output_path],
            safe_text,
            "emoji",
            progress_message=callback.message,
            owner_id=callback.from_user.id,
            title=f"{text} — Logo Emoji"
        )

        if not pack_name:
            await callback.message.edit_text(
                "❌ Pack yaratilmadi."
            )
            return

        record_pack_created(
            callback.from_user.id,
            callback.from_user.username
        )

        if not is_free_user(
            callback.from_user.id
        ):
            use_credit(
                callback.from_user.id
            )

        await reward_referral_if_pending(
            callback.bot,
            callback.from_user.id
        )

        await callback.message.edit_text(
            "✅ <b>Logo/Text Emoji tayyor!</b>\n\n"
            f"📝 Matn: <code>{text}</code>\n"
            f"🎨 Shablon: <b>{template_id}</b>\n\n"
            f"📦 Pack:\n<code>{pack_name}</code>",
            reply_markup=back_to_menu_keyboard()
        )

    except Exception as e:
        logging.exception(
            "Logo emoji generation failed"
        )

        await callback.message.edit_text(
            "❌ Logo/Text Emoji yaratishda xatolik:\n\n"
            f"<code>{e}</code>",
            reply_markup=back_to_menu_keyboard()
        )


@router.callback_query(
    F.data.startswith("buy_logo:")
)
async def buy_logo_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    template_id = int(
        callback.data.split(":", 1)[1]
    )

    price = load_price("logo")

    await callback.message.edit_text(
        "💳 <b>Logo/Text Emoji</b>\n\n"
        f"Narxi: <b>{price} Stars</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⭐ {price} Stars",
                        callback_data=f"pay_logo:{template_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("pay_logo:")
)
async def pay_logo_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    template_id = int(
        callback.data.split(":", 1)[1]
    )

    price = load_price("logo")

    await state.update_data(
        pending_purchase={
            "kind": "logo",
            "template_id": template_id,
            "price": price
        }
    )

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Logo/Text Emoji",
        description="Logo/Text Emoji pack yaratish",
        payload=f"logo:{template_id}:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label="Logo/Text Emoji",
                amount=price
            )
        ]
    )

    await callback.answer()


# ============================================================================
# GREEN EMOJIS
# ============================================================================

@router.message(GreenStates.waiting_text)
async def green_receive_text(
    message: Message,
    state: FSMContext
):
    if not message.text:
        await message.answer(
            "❌ Iltimos, matn yuboring."
        )
        return

    text = message.text.strip()

    if len(text) > MAX_LEN:
        await message.answer(
            f"❌ Maksimal uzunlik {MAX_LEN} ta belgi."
        )
        return

    await state.update_data(
        text=text
    )

    price = load_price("green")

    keyboard = [
        [
            InlineKeyboardButton(
                text=f"⭐ {price} Stars",
                callback_data="buy_green"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="back_to_menu"
            )
        ]
    ]

    await message.answer(
        "🟢 <b>Green Emojis</b>\n\n"
        f"29 ta tayyor Green Emoji pack.\n"
        f"Narxi: <b>{price} Stars</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )
    )


@router.callback_query(
    F.data == "buy_green"
)
async def buy_green_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    price = load_price("green")

    if (
        is_free_user(callback.from_user.id)
        or get_credits(callback.from_user.id) > 0
    ):
        await generate_green_pack(
            callback,
            state
        )
        await callback.answer()
        return

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Green Emojis",
        description="29 ta Green Emoji pack",
        payload=f"green:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label="Green Emojis",
                amount=price
            )
        ]
    )

    await callback.answer()


async def generate_green_pack(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    text = data.get("text")

    if not text:
        await callback.message.edit_text(
            "❌ Matn topilmadi.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    await callback.message.edit_text(
        "⏳ Green Emojis tayyorlanmoqda..."
    )

    try:
        output_dir = os.path.join(
            os.path.dirname(__file__),
            "output"
        )

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        safe_text = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            text
        ) or "green"

        sticker_paths = []

        for i, template_path in enumerate(
            GREEN_EMOJI_TEMPLATE_PATHS,
            start=1
        ):
            output_path = os.path.join(
                output_dir,
                f"{safe_text}_green_{i:03d}.tgs"
            )

            logo_engine.add_text_overlay_to_tgs(
                template_path,
                text,
                output_path
            )

            sticker_paths.append(
                output_path
            )

            try:
                await callback.message.edit_text(
                    f"⏳ Tayyorlanmoqda: "
                    f"{i}/{len(GREEN_EMOJI_TEMPLATE_PATHS)}"
                )
            except Exception:
                pass

        pack_name = await add_stickers_to_pack(
            callback.bot,
            sticker_paths,
            safe_text,
            "emoji",
            progress_message=callback.message,
            owner_id=callback.from_user.id,
            title=f"{text} — Green Emojis"
        )

        if not pack_name:
            await callback.message.edit_text(
                "❌ Green Emoji pack yaratilmadi."
            )
            return

        record_pack_created(
            callback.from_user.id,
            callback.from_user.username
        )

        if not is_free_user(
            callback.from_user.id
        ):
            use_credit(
                callback.from_user.id
            )

        await reward_referral_if_pending(
            callback.bot,
            callback.from_user.id
        )

        await callback.message.edit_text(
            "✅ <b>Green Emojis tayyor!</b>\n\n"
            f"📝 Matn: <code>{text}</code>\n"
            f"🟢 Emoji soni: 29\n\n"
            f"📦 Pack:\n<code>{pack_name}</code>",
            reply_markup=back_to_menu_keyboard()
        )

    except Exception as e:
        logging.exception(
            "Green emoji generation failed"
        )

        await callback.message.edit_text(
            "❌ Xatolik:\n\n"
            f"<code>{e}</code>",
            reply_markup=back_to_menu_keyboard()
        )


# ============================================================================
# PROFIL
# ============================================================================

@router.callback_query(
    F.data == "profile"
)
async def profile_callback(
    callback: CallbackQuery
):
    user_id = callback.from_user.id

    credits = get_credits(
        user_id
    )

    stats = load_stats()

    user_stats = stats.get(
        str(user_id),
        {}
    )

    packs = user_stats.get(
        "packs",
        0
    )

    stars = user_stats.get(
        "stars",
        0
    )

    username = callback.from_user.username

    username_text = (
        f"@{username}"
        if username
        else "username yo'q"
    )

    await callback.message.edit_text(
        "👤 <b>Sizning profilingiz</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: {username_text}\n\n"
        f"🎁 Kreditlar: <b>{credits}</b>\n"
        f"📦 Yaratilgan packlar: <b>{packs}</b>\n"
        f"⭐ Sarflangan Stars: <b>{stars}</b>",
        reply_markup=back_to_menu_keyboard()
    )

    await callback.answer()


# ============================================================================
# REFERAL
# ============================================================================

@router.callback_query(
    F.data == "referral"
)
async def referral_callback(
    callback: CallbackQuery
):
    user_id = callback.from_user.id

    bot = callback.bot

    me = await bot.get_me()

    link = (
        f"https://t.me/{me.username}"
        f"?start=ref_{user_id}"
    )

    referrals = load_referrals()

    count = 0

    for entry in referrals.values():
        if (
            entry.get("referrer")
            == user_id
        ):
            count += 1

    await callback.message.edit_text(
        "🎁 <b>Referal dasturi</b>\n\n"
        f"👥 Siz taklif qilganlar: <b>{count}</b>\n\n"
        "Do'stingiz botga kirib, birinchi packini "
        "yaratsa sizga 1 ta kredit beriladi.\n\n"
        f"🔗 Sizning referal linkingiz:\n"
        f"<code>{link}</code>",
        reply_markup=back_to_menu_keyboard()
    )

    await callback.answer()


# ============================================================================
# YORDAM
# ============================================================================

@router.callback_query(
    F.data == "help"
)
async def help_callback(
    callback: CallbackQuery
):
    support = get_support_contact()

    await callback.message.edit_text(
        "ℹ️ <b>Yordam</b>\n\n"
        "🔤 <b>Name Emojis</b> — tayyor shablon asosida "
        "animatsiyali emoji yaratadi.\n\n"
        "🖼 <b>Logo/Text Emojis</b> — 103 ta shablondan "
        "birini tanlab, matn joylashtiradi.\n\n"
        "🟢 <b>Green Emojis</b> — 29 ta tayyor animatsiyaga "
        "matn qo'shadi.\n\n"
        f"🆘 Muammo bo'lsa: {support}",
        reply_markup=back_to_menu_keyboard()
    )

    await callback.answer()
# ============================================================================
# ADMIN
# ============================================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Statistika",
                    callback_data="admin_stats"
                ),
                InlineKeyboardButton(
                    text="👥 Foydalanuvchilar",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Narxlar",
                    callback_data="admin_prices"
                ),
                InlineKeyboardButton(
                    text="📢 Kanallar",
                    callback_data="admin_channels"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📣 Broadcast",
                    callback_data="admin_broadcast"
                ),
                InlineKeyboardButton(
                    text="🆘 Support",
                    callback_data="admin_support"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Kod",
                    callback_data="admin_code"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    state: FSMContext
):
    if not message.from_user:
        return

    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "❌ Siz admin emassiz."
        )
        return

    await state.clear()

    await message.answer(
        "⚙️ <b>Admin panel</b>\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=admin_keyboard()
    )


@router.callback_query(
    F.data == "admin_stats"
)
async def admin_stats_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    users = load_users()
    credits = load_credits()
    stats = load_stats()

    total_credits = sum(
        credits.values()
    )

    total_packs = sum(
        x.get("packs", 0)
        for x in stats.values()
    )

    total_stars = sum(
        x.get("stars", 0)
        for x in stats.values()
    )

    await callback.message.edit_text(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(users)}</b>\n"
        f"🎁 Jami kreditlar: <b>{total_credits}</b>\n"
        f"📦 Yaratilgan packlar: <b>{total_packs}</b>\n"
        f"⭐ Sarflangan Stars: <b>{total_stars}</b>",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@router.callback_query(
    F.data == "admin_users"
)
async def admin_users_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    users = load_users()

    await callback.message.edit_text(
        "👥 <b>Foydalanuvchilar</b>\n\n"
        f"Jami foydalanuvchilar: "
        f"<b>{len(users)}</b>",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@router.callback_query(
    F.data == "admin_prices"
)
async def admin_prices_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "💰 <b>Joriy narxlar</b>\n\n"
        f"🔤 Name: <b>{load_price('name')} Stars</b>\n"
        f"🖼 Logo: <b>{load_price('logo')} Stars</b>\n"
        f"🟢 Green: <b>{load_price('green')} Stars</b>\n"
        f"💻 Kod: <b>{load_price('code')} Stars</b>\n\n"
        "O'zgartirish uchun kerakli bo'limni tanlang:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔤 Name",
                        callback_data="set_price:name"
                    ),
                    InlineKeyboardButton(
                        text="🖼 Logo",
                        callback_data="set_price:logo"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🟢 Green",
                        callback_data="set_price:green"
                    ),
                    InlineKeyboardButton(
                        text="💻 Kod",
                        callback_data="set_price:code"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Admin",
                        callback_data="admin_back"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.callback_query(
    F.data.startswith("set_price:")
)
async def set_price_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    kind = callback.data.split(
        ":",
        1
    )[1]

    await state.update_data(
        price_kind=kind
    )

    await state.set_state(
        AdminStates.waiting_price
    )

    await callback.message.edit_text(
        f"💰 {kind} uchun yangi Stars narxini yuboring.\n\n"
        "Masalan: <code>20</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga",
                        callback_data="admin_prices"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.message(
    AdminStates.waiting_price
)
async def admin_receive_price(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        return

    try:
        price = int(
            message.text.strip()
        )

        if price <= 0:
            raise ValueError

    except (ValueError, AttributeError):
        await message.answer(
            "❌ To'g'ri musbat son yuboring."
        )
        return

    data = await state.get_data()

    kind = data.get(
        "price_kind",
        "name"
    )

    save_price(
        kind,
        price
    )

    await state.clear()

    await message.answer(
        f"✅ {kind} narxi "
        f"<b>{price} Stars</b> qilib o'rnatildi.",
        reply_markup=admin_keyboard()
    )


@router.callback_query(
    F.data == "admin_channels"
)
async def admin_channels_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    channels = get_required_channels()

    text = (
        "📢 <b>Majburiy kanallar</b>\n\n"
    )

    if channels:
        text += "\n".join(
            f"• {channel}"
            for channel in channels
        )
    else:
        text += "Hozircha kanal qo'shilmagan."

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Kanal qo'shish",
                        callback_data="add_channel"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🗑 Kanallarni tozalash",
                        callback_data="clear_channels"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Admin",
                        callback_data="admin_back"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.callback_query(
    F.data == "add_channel"
)
async def add_channel_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        return

    await state.set_state(
        AdminStates.waiting_channel
    )

    await callback.message.edit_text(
        "📢 Kanal username'ini yuboring.\n\n"
        "Masalan:\n"
        "<code>@mychannel</code>"
    )

    await callback.answer()


@router.message(
    AdminStates.waiting_channel
)
async def admin_receive_channel(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        return

    channel = message.text.strip()

    if not channel.startswith("@"):
        channel = "@" + channel

    channels = get_required_channels()

    if channel not in channels:
        channels.append(channel)

    save_required_channels(
        channels
    )

    await state.clear()

    await message.answer(
        f"✅ Kanal qo'shildi:\n"
        f"<code>{channel}</code>",
        reply_markup=admin_keyboard()
    )


@router.callback_query(
    F.data == "clear_channels"
)
async def clear_channels_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        return

    save_required_channels([])

    await callback.message.edit_text(
        "✅ Majburiy kanallar tozalandi.",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@router.callback_query(
    F.data == "admin_support"
)
async def admin_support_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        return

    await state.set_state(
        AdminStates.waiting_support
    )

    await callback.message.edit_text(
        "🆘 Support username'ini yuboring.\n\n"
        "Masalan:\n"
        "<code>@support</code>"
    )

    await callback.answer()


@router.message(
    AdminStates.waiting_support
)
async def admin_receive_support(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        return

    support = message.text.strip()

    set_support_contact(
        support
    )

    await state.clear()

    await message.answer(
        "✅ Support kontakti yangilandi.",
        reply_markup=admin_keyboard()
    )


@router.callback_query(
    F.data == "admin_broadcast"
)
async def admin_broadcast_callback(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        return

    await state.set_state(
        AdminStates.waiting_broadcast
    )

    await callback.message.edit_text(
        "📣 Broadcast uchun yuboriladigan "
        "xabarni shu yerga yuboring.\n\n"
        "Matn, rasm yoki video yuborishingiz mumkin."
    )

    await callback.answer()


@router.message(
    AdminStates.waiting_broadcast
)
async def admin_receive_broadcast(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        return

    users = load_users()

    success = 0
    failed = 0

    for user_id in users:
        try:
            await message.copy_to(
                chat_id=user_id
            )

            success += 1

        except Exception:
            failed += 1

        await asyncio.sleep(
            0.05
        )

    await state.clear()

    await message.answer(
        "📣 <b>Broadcast tugadi</b>\n\n"
        f"✅ Yuborildi: <b>{success}</b>\n"
        f"❌ Yuborilmadi: <b>{failed}</b>",
        reply_markup=admin_keyboard()
    )


# ============================================================================
# ADMIN KOD SOTUV BO'LIMI
# ============================================================================

@router.callback_query(
    F.data == "admin_code"
)
async def admin_code_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )
        return

    price = load_price(
        "code"
    )

    await callback.message.edit_text(
        "💻 <b>Bot source code</b>\n\n"
        f"Joriy narx: <b>{price} Stars</b>\n\n"
        "Xaridor to'lov qilgandan keyin bot "
        "manba kodining tozalangan ZIP faylini yuboradi.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Narxni o'zgartirish",
                        callback_data="set_price:code"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Admin",
                        callback_data="admin_back"
                    )
                ]
            ]
        )
    )

    await callback.answer()


@router.callback_query(
    F.data == "admin_back"
)
async def admin_back_callback(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        return

    await callback.message.edit_text(
        "⚙️ <b>Admin panel</b>",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================================
# SOURCE CODE SOTIB OLISH
# ============================================================================

@router.message(
    Command("code")
)
async def code_command(
    message: Message
):
    if not message.from_user:
        return

    price = load_price(
        "code"
    )

    await message.answer(
        "💻 <b>Bot Source Code</b>\n\n"
        "Botning to'liq manba kodini olish mumkin.\n\n"
        f"💰 Narxi: <b>{price} Stars</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⭐ {price} Stars",
                        callback_data="buy_code"
                    )
                ]
            ]
        )
    )


@router.callback_query(
    F.data == "buy_code"
)
async def buy_code_callback(
    callback: CallbackQuery
):
    price = load_price(
        "code"
    )

    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Bot Source Code",
        description="Telegram botning to'liq source kodi",
        payload=f"code:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label="Bot Source Code",
                amount=price
            )
        ]
    )

    await callback.answer()


async def send_code_package(
    bot: Bot,
    user_id: int
):
    try:
        package_path = build_code_package()

        document = FSInputFile(
            package_path
        )

        await bot.send_document(
            chat_id=user_id,
            document=document,
            caption=(
                "✅ <b>Source code tayyor!</b>\n\n"
                "ZIP fayl ichida botning barcha "
                "kerakli manba kodlari mavjud.\n\n"
                "⚠️ BOT_TOKEN, ADMIN_ID va LOG_CHAT_ID "
                "xavfsizlik sababli olib tashlangan."
            )
        )

    except Exception as e:
        logging.exception(
            "Code package sending failed"
        )

        await bot.send_message(
            user_id,
            "❌ Source code yuborishda xatolik yuz berdi."
        )


# ============================================================================
# TO'LOVNI QAYTA ISHLASH
# ============================================================================

@router.message(
    F.successful_payment
)
async def successful_payment_handler(
    message: Message,
    state: FSMContext
):
    payment = message.successful_payment

    if not payment:
        return

    payload = payment.invoice_payload

    parts = payload.split(":")

    if not parts:
        return

    kind = parts[0]

    user_id = message.from_user.id

    if kind == "code":
        record_stars_spent(
            user_id,
            message.from_user.username,
            payment.total_amount
        )

        await message.answer(
            "⏳ To'lov qabul qilindi.\n"
            "Source code tayyorlanmoqda..."
        )

        await send_code_package(
            message.bot,
            user_id
        )

        return

    if kind == "logo":
        if len(parts) >= 2:
            template_id = int(
                parts[1]
            )

            record_stars_spent(
                user_id,
                message.from_user.username,
                payment.total_amount
            )

            await state.update_data(
                paid=True,
                paid_kind="logo",
                paid_template_id=template_id
            )

            await message.answer(
                "✅ To'lov qabul qilindi!\n\n"
                "🖼 Logo/Text Emoji uchun "
                "matn yuboring:"
            )

            await state.set_state(
                LogoStates.waiting_text
            )

        return

    if kind == "green":
        record_stars_spent(
            user_id,
            message.from_user.username,
            payment.total_amount
        )

        await state.update_data(
            paid=True,
            paid_kind="green"
        )

        await message.answer(
            "✅ To'lov qabul qilindi!\n\n"
            "🟢 Green Emoji uchun matn yuboring:"
        )

        await state.set_state(
            GreenStates.waiting_text
        )

        return


# ============================================================================
# BOT ISHGA TUSHISHI
# ============================================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi."
        )

    bot = Bot(
        token=BOT_TOKEN
    )

    dp = Dispatcher(
        storage=MemoryStorage()
    )

    dp.include_router(
        router
    )

    logging.info(
        "Bot ishga tushmoqda..."
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )