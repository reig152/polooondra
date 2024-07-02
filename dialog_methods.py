import re
import asyncio
from math import ceil
from aiogram_dialog.widgets.input.text import ManagedTextInput
from aiogram_dialog import DialogManager, StartMode
from typing import Any

from aiogram.types import CallbackQuery, Message

import tgbot.windows.chat_infos_1 as ci
from tgbot.windows.states.all_states import (
    MarketingStates, BrokerStates
)
import tgbot.templates.text_templates as tp
from tgbot.config.use_case import CORE_USE_CASE

from .dialog_methods_utils import get_method_result


async def switch_to_main_menu(
    msg: Message, widget: Any,
    manager: DialogManager
):
    """Проверка пользователя и начало соответствующего диалога."""

    group = await CORE_USE_CASE.get_user_group(
        username=msg.from_user.username
    )
    if group == "marketing":
        await manager.start(
            MarketingStates.choose_market,
            mode=StartMode.RESET_STACK
        )

    elif group == "sales":
        await manager.start(
            BrokerStates.main_menu,
            mode=StartMode.RESET_STACK
        )


async def on_market_selected(
    callback: CallbackQuery, widget: Any,
    dialog_manager: DialogManager,
):
    """Выбор площадки для чата."""
    # устнавливаем площадку
    dialog_manager.dialog_data['market'] = callback.data.split('_')[0]
    await dialog_manager.switch_to(MarketingStates.main_menu)


async def main_menu_window_data(dialog_manager: DialogManager, **kwargs):
    """getter главного меню с обработкой ошибочного статуса."""
    market = dialog_manager.dialog_data.get('market')

    # получаем данные
    acquired_data = await get_method_result(
        market, "count_unread"
    )

    # если int, значит статус 200
    condition = isinstance(acquired_data, int)

    return {
        "unread_count": f"({acquired_data})" if condition else "(0)",
        "success": True if condition else False,
        "failure": True if not condition else False
    }


async def dialogs_window_data(dialog_manager: DialogManager, **kwargs):
    """Данные для вывода кнопок непрочитанных диалогов."""
    dialog_type = dialog_manager.event.data.split("_")[1]

    # получаем диалоги
    dialogs = await get_method_result(
        dialog_manager.dialog_data.get('market'),
        "get_dialogs_list",
        True if dialog_type == "unread" else None
    )

    return {
        "dialogs": dialogs
    }


async def on_chat_selected(
    callback: CallbackQuery, widget: Any,
    manager: DialogManager, item_id: str
):
    """on_click функция для перехода в диалог."""
    market = manager.dialog_data.get("market")

    state_id = callback.data.split(':')[0]
    state = {
        's_unread_dialog': MarketingStates.select_unread,
        's_read_dialog': MarketingStates.select_read
    }

    # получаем диалог по его chat_id
    messages = await get_method_result(
        market,
        "get_all_messages",
        item_id
    )
    # передаем сообщения для рендера
    manager.dialog_data['messages'] = messages
    manager.dialog_data['chatId'] = item_id
    if messages:
        manager.dialog_data['offer_link'] = await get_method_result(
            market, "get_offer_link", item_id
        )
        manager.dialog_data['dialog_messages'] = messages
        await manager.switch_to(state[state_id])


async def on_chat_selected_getter(
    dialog_manager: DialogManager, **kwargs
):
    """getter для обработки отсутствующего по id диалогу."""
    messages = dialog_manager.dialog_data.get("messages", None)
    return {
        "broken": True if not messages else False,
        "operable": True if messages else False
    }


async def answer_message(
    callback: CallbackQuery, widget: Any,
    manager: DialogManager
):
    """on_click для ожидания текста сообщения от пользователя."""
    manager.dialog_data['type_answer'] = "Напечатайте текст сообщения"
    await manager.switch_to(MarketingStates.type_answer)


async def send_message(
    msg: Message, _: ManagedTextInput[str],
    manager: DialogManager, data: str
):
    """on_click для отправки сообщения клиенту."""
    chat_id = manager.dialog_data['chatId']
    # вызываем метод отправки сообщения
    await get_method_result(
        manager.dialog_data.get("market"),
        "send_api_message",
        chat_id,
        msg.text
    )
    # await ci.send_api_cian_message(chat_id, msg.text)
    manager.dialog_data['message_sent'] = "Ваше сообщение отправлено!"
    await manager.switch_to(MarketingStates.message_sent)


async def send_message_template(
    callback: CallbackQuery, widget: Any,
    manager: DialogManager
):
    """Функция для формирования шаблонных сообщений."""
    chat_id = manager.dialog_data['chatId']
    template_dict = {
        "greeting_answer": tp.template_greeting(
            manager.dialog_data.get('market')
        ),
        "delegate_answer": tp.template_delegate,
        "template_greeting_1": tp.template_greeting_1,
        "template_info": tp.template_info,
    }
    text_answer = template_dict.get(callback.data, "")
    # вызываем метод отправки сообщения
    await get_method_result(
        manager.dialog_data.get('market'),
        "send_api_message",
        chat_id,
        text_answer
    )
    manager.dialog_data['message_sent'] = "Ваше сообщение отправлено!"
    await manager.switch_to(MarketingStates.message_sent)


async def finisih_dialog(
    callback: CallbackQuery, widget: Any,
    manager: DialogManager
):
    """Функция завершения диалога."""
    chat_id = manager.dialog_data['chatId']
    # вызываем метод отправки сообщения
    await get_method_result(
        manager.dialog_data.get('market'),
        "mark_as_read_dialog",
        chat_id
    )
    await manager.switch_to(MarketingStates.dialog_finished)


async def notification_getter(dialog_manager: DialogManager, **kwargs) -> dict:
    """getter информации об уведомлении."""
    # получаем market
    market = dialog_manager.start_data

    # вызываем метод отправки сообщения
    chatId, offer_link, messages = await get_method_result(
        market,
        "data_for_notification",
    )

    # объявляем market для остальных функций
    dialog_manager.dialog_data['market'] = market
    dialog_manager.dialog_data['chatId'] = chatId

    condition = chatId and offer_link and messages

    return {
        "dialog_messages": messages,
        "offer_link": offer_link,
        "success": True if condition else False,
        "failure": True if not condition else False
    }
