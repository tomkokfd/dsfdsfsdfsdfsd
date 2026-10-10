"""Menu callback handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from xrocket.config import EMOJI, URL_NEWS, URL_SUPPORT
from xrocket.database import db
from xrocket.keyboards.menu import main_menu_keyboard
from xrocket.services import balance as balance_service
from xrocket.utils.formatters import tg_emoji, user_mention_html

router = Router(name="menu")
log = logging.getLogger("xrocket-fun")


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")]
        ]
    )


def _settings_kb() -> InlineKeyboardMarkup:
    e = EMOJI
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Поддержка",
                    url=URL_SUPPORT,
                    icon_custom_emoji_id=e["support"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отображение балансов",
                    callback_data="noop",
                    icon_custom_emoji_id=e["wallet"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Управление токенами",
                    callback_data="noop",
                    icon_custom_emoji_id=e["eye"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Привилегии",
                    callback_data="noop",
                    icon_custom_emoji_id=e["lock"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Язык бота",
                    callback_data="noop",
                    icon_custom_emoji_id=e["lang"],
                ),
                InlineKeyboardButton(
                    text="Валюта бота",
                    callback_data="noop",
                    icon_custom_emoji_id=e["currency"],
                ),
            ],
            [
                InlineKeyboardButton(
                    text="История ваших действий",
                    callback_data="noop",
                    icon_custom_emoji_id=e["history"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Заявка на листинг токена",
                    callback_data="noop",
                    icon_custom_emoji_id=e["listing"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Настройки биржи",
                    callback_data="noop",
                    icon_custom_emoji_id=e["exchange"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Привязать кошелёк",
                    callback_data="noop",
                    icon_custom_emoji_id=e["link"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Управление группами",
                    callback_data="noop",
                    icon_custom_emoji_id=e["groups"],
                )
            ],
            [
                InlineKeyboardButton(
                    text="Лимиты и комиссии",
                    callback_data="noop",
                    icon_custom_emoji_id=e["limits"],
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")],
        ]
    )


def _about_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подробнее",
                    callback_data="noop",
                    icon_custom_emoji_id=EMOJI["about"],
                )
            ],
            [InlineKeyboardButton(text="‹ Назад", callback_data="menu:home")],
        ]
    )


def _about_text(user_id: int, full_name: str) -> str:
    name = user_mention_html(user_id, full_name or "друг")
    info = tg_emoji("about", "ℹ️")
    rocket = tg_emoji("rocket", "🚀")
    books = tg_emoji("books", "📚")
    note = tg_emoji("listing", "📝")
    lock = tg_emoji("lock", "🔒")
    phone = tg_emoji("phone", "📞")
    return (
        f"{info} <b>Привет, {name}! Добро пожаловать в xRocket! </b><b>{rocket}</b>\n"
        f"\n"
        f"Ты сделал отличный выбор, решив присоединиться к нам! xRocket — это твой "
        f"надежный помощник для торговли и управления криптовалютами прямо в Telegram. "
        f"Давай быстро освоим его возможности, и ты начнешь зарабатывать на «крипте» вместе с нами!\n"
        f"\n"
        f"<b>{books} Что такое xRocket?</b>\n"
        f"\n"
        f"xRocket объединяет функции криптовалютного кошелька и централизованной биржи. С ним ты можешь:\n"
        f" • <b>Торговать криптовалютами</b> с использованием лимитных и рыночных ордеров "
        f"(подробнее об ордерах я расскажу дальше).\n"
        f" • <b>Покупать крипту за фиат</b> (Фиат - обычная валюта, выпускаемая государством – "
        f"рубли, евро, тенге и т.д.) на P2P-рынке.\n"
        f" • <b>Хранить свои активы</b> в безопасном кошельке.\n"
        f" • <b>Создавать чеки и инвойсы</b> для расчетов. (подробнее о чеках и инвойсах я расскажу дальше)\n"
        f" • <b>Интегрировать свои решения</b> с помощью Rocket API.\n"
        f"\n"
        f"<b>{note} Как пользоваться ботом?</b>\n"
        f"Ты можешь использовать бот несколькими способами:\n"
        f"1. Через <b>меню</b> в нижнем левом углу экрана.\n"
        f"2. <b>Вводя команды</b> в строку сообщений.\n"
        f"3. Используя <b>интерактивные кнопки</b> бота.\n"
        f"\n"
        f"<b>{lock} Безопасность</b>\n"
        f"Твоя безопасность — наш приоритет! Все твои сделки защищены и полностью легальны.\n"
        f"\n"
        f"<b>{phone} Поддержка</b>\n"
        f"Нужна помощь? Напиши в @hollysceo, и мы сразу поможем!\n"
        f"\n"
        f"<b>Готов погрузиться в мир криптовалют?</b> Следуй этим шагам, и ты освоишься в "
        f"xRocket за считанные минуты. Удачи и не забывай — мы всегда рядом, чтобы помочь! {rocket}"
    )


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup) -> None:
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.exception("menu edit failed data=%s: %s", callback.data, exc)
        try:
            await callback.message.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception:
            log.exception("menu answer fallback failed data=%s", callback.data)


@router.callback_query(F.data.in_({"noop", "menu:commands"}))
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery) -> None:
    user = callback.from_user
    db.ensure_user(user.id, user.username, user.full_name)
    total = balance_service.total_usd(user.id)
    cheques_n = db.count_active_cheques(user.id)
    rocket = tg_emoji("rocket", "🚀")
    text = (
        f"{rocket} <b>xRocket</b> — это бот-кошелёк для получения, отправки, "
        f"покупки и хранения криптовалюты в Telegram.\n\n"
        f"Обо всех возможностях читай в "
        f'<a href="{URL_NEWS}">официальном канале</a>'
    )
    await _safe_edit(callback, text, main_menu_keyboard(total, cheques_n, user.id))
    await callback.answer()


@router.callback_query(F.data == "menu:collapse")
async def menu_collapse(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()


@router.callback_query(F.data.in_({"menu:settings", "nav:settings"}))
async def menu_settings(callback: CallbackQuery) -> None:
    gear = tg_emoji("settings", "⚙️")
    text = (
        f"{gear} <b>Настройки</b>\n"
        f"\n"
        f"Ваш язык: <b>Русский</b>\n"
        f"Валюта бота: <b>USD · $</b>"
    )
    log.info("menu:settings from %s", callback.from_user.id if callback.from_user else None)
    await _safe_edit(callback, text, _settings_kb())
    await callback.answer()


@router.callback_query(F.data.in_({"menu:about", "nav:about"}))
async def menu_about(callback: CallbackQuery) -> None:
    user = callback.from_user
    text = _about_text(user.id, user.full_name or user.first_name or "друг")
    log.info("menu:about from %s len=%s", user.id, len(text))
    await _safe_edit(callback, text, _about_kb())
    await callback.answer()
