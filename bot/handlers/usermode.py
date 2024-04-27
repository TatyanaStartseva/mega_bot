import os
import functools
import json
from datetime import datetime, timedelta
from asyncio import create_task, sleep
import  aiohttp
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    ContentType,
    FSInputFile,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from fluent.runtime import FluentLocalization
from aiogram.exceptions import TelegramAPIError
from aiogram import types
from aiogram.types import InputFile
from bot.config_reader import config
from bot.filters import SupportedMediaFilter
from bot.db import ChatBotDBAPI


router = Router()


class ChatMessage:
    def __init__(self, data: str, chat_id: int, message_id: int):
        self.data = data
        self.message = self.Message(chat_id, message_id)

    class Message:
        def __init__(self, chat_id: int, message_id: int):
            self.chat = self.Chat(chat_id)
            self.message_id = message_id

        class Chat:
            def __init__(self, chat_id: int):
                self.id = chat_id


def _format_date(date):
    return date.strftime("%d.%m")


async def _wrap_promise(promise_fn):
    """
    Оборачивает переданную функцию-обещание (promise_fn) в цикл с возможностью повторного выполнения в случае ошибки.

    :param promise_fn: функция-обещание (promise), которая должна быть выполнена
    :return: результат выполнения promise_fn в случае успеха, в противном случае None
    """
    i = 0

    while i < 10:
        try:
            return await promise_fn()
        except Exception as e:
            print(f"Произошла ошибка в функции {promise_fn}: {str(e)}; Итерация {i}")
            await sleep(2.5)
            i += 1
    return None


def _generate_date_picker():
    current_date = datetime.now()
    days_in_two_weeks = 9
    inline_keyboard = []
    current_row = []

    for day in range(days_in_two_weeks):
        date = current_date + timedelta(days=day)

        if day == 0 and date.hour >= 15:
            continue

        date_button = InlineKeyboardButton(
            text=_format_date(date),
            callback_data=f'{{"date": "{_format_date(date)}", "status": "communicate_call"}}',
        )

        current_row.append(date_button)
        if len(current_row) == 2 or day == days_in_two_weeks - 1:
            inline_keyboard.append(current_row.copy())
            current_row.clear()

    return inline_keyboard


def _generate_time_sub_menu(date):
    time_sub_menu = []
    current_date = datetime.now()
    current_hour = current_date.hour

    for hour in range(9, 18, 2):
        row = []

        for i in range(2):
            current_hour_of_day = hour + i

            if current_hour_of_day > current_hour + 4 or date != current_date.strftime(
                "%d.%m"
            ):
                time = f"{str(current_hour_of_day).zfill(2)}:00"
                callback_data = {
                    "time": time,
                    "status": "communicate_call",
                    "date": date,
                }
                callback_data_str = json.dumps(callback_data)

                row.append(
                    InlineKeyboardButton(
                        text=time,
                        callback_data=callback_data_str,
                    )
                )

        if row:
            time_sub_menu.append(row)

    if time_sub_menu:
        time_sub_menu.append(
            [
                InlineKeyboardButton(
                    text="Выбрать другой день",
                    callback_data=f'{{"status": "communicate_call"}}',
                )
            ]
        )

    return time_sub_menu


def _inline_keyboard_status(callback_data, text=None):
    """
    Генерирует встроенные подскази-кнопки для заданного статуса и текста.

    :param status: статус для коллбэка
    :param text: текст кнопки (по умолчанию "Следующее видео")
    :return: объект InlineKeyboardMarkup
    """
    button_text = text or "Следующее видео"
    keyboard = [
        [InlineKeyboardButton(text=button_text, callback_data=str(callback_data))]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def _clear_keyboard(bot, chat_id, message_id, add_markup=None):
    """Очищает разметку сообщения и добавляет новую."""
    await bot.edit_message_reply_markup(
        chat_id=chat_id, message_id=message_id, reply_markup=add_markup
    )

async def _send_expiring_notification(message: Message, l10n: FluentLocalization):
    """
    Отправляет "самоуничтожающееся" через 5 секунд сообщение

    :param message: сообщение, на которое бот отвечает подтверждением отправки
    :param l10n: объект локализации
    """
    msg = await message.reply(l10n.format_value("sent-confirmation"))
    if config.remove_sent_confirmation:
        await sleep(5.0)
        await msg.delete()


async def _send_video_to_user(bot, chat_id, video_link, inline_keyboard ):
    try:
        async with aiohttp.ClientSession() as session:
                async with session.get(video_link) as response:
                    video_bytes = await response.read()
                    if inline_keyboard is not None:
                        sent_message = await bot.send_video(chat_id, video=types.BufferedInputFile(file=video_bytes,
                                                                                                   filename='video.mp4'),
                                                            reply_markup=inline_keyboard)
                    else:
                        sent_message = await bot.send_video(chat_id, video=types.BufferedInputFile(file=video_bytes,
                                                                                                   filename='video.mp4'))
        return sent_message.message_id
    except Exception as e:
        print("Ошибка отправки видео:", e)
        return None
import asyncio

async def _automatic_transition(callback_query, bot, l10n, status, timeout):
    try:
        await asyncio.sleep(timeout)
        user_DB = ChatBotDBAPI().get_document_by_id(callback_query.message.chat.id)
        if (
            not user_DB
            or "status" not in user_DB
            or user_DB["status"] is None
            or user_DB["status"] != status
        ):
            return
        await handle_callback_query(callback_query, bot, l10n)
    except Exception as e:
        print("Error in automatic transition:", e)

@router.message(Command(commands=["start"]))
async def cmd_start(message: Message, bot: Bot, l10n: FluentLocalization):
    """
    Приветственное сообщение от бота к пользователю

    :param message: сообщение от пользователя с командой /start
    :param l10n: объект локализации
    """
    user = await bot.get_chat(message.chat.id)
    user_data = {
        "id": user.id,
        "first_name": user.full_name,
        "last_name": user.last_name,
        "username": message.chat.username,
        "bio": user.bio,
        "status": 0,
    }
    user_DB = ChatBotDBAPI().get_document_by_id(user.id)
    if not user_DB or "topic_id" not in user_DB or user_DB["topic_id"] is None:
        topic = await bot.create_forum_topic(
                config.admin_chat_id,
                user.full_name,
                icon_custom_emoji_id=5357121491508928442,
            )
        user_data["topic_id"] = topic.message_thread_id
        user_data["link"] = (
                f"https://t.me/c/{str(config.admin_chat_id).replace('-100', '')}/{topic.message_thread_id}"
            )
        ChatBotDBAPI().add_or_update_document(user_data)
    with open('setup.json', 'r') as file:
        setup_data = json.load(file)
    step = setup_data['steps'][0]
    automatic_step = step['automatic_step']
    if step.get('button', False):
        inline_keyboard_status= _inline_keyboard_status({"status":1}, step['button'] if isinstance(step['button'], str) else None)
    else:
        inline_keyboard_status = None
    for stage_key, stage_value in step['type'].items():
        if 'text' in stage_key:
            await message.answer(stage_value)
        elif 'video' in stage_key:
            video_id = await _send_video_to_user(
                bot, message.chat.id, stage_value, inline_keyboard_status
            )
            if automatic_step:
                create_task(
                    _automatic_transition(
                        ChatMessage(str({"status": 1}), message.chat.id, video_id),
                        bot,
                        l10n,
                        0,
                        automatic_step,
                    )
                )
    if user.username:
        await bot.send_message(config.admin_chat_id, l10n.format_value("comminicate_start", user_data), reply_to_message_id=user_DB['topic_id'],)
        await bot.send_message(
            config.admin_chat_id,
            l10n.format_value("funnel_started_general", user_data),
            parse_mode="HTML",
        )
    else:
        await bot.send_message(config.admin_chat_id, l10n.format_value("comminicate_start", user_data),
                               reply_to_message_id=user_DB['topic_id'], )
        await bot.send_message(
            config.admin_chat_id,
            l10n.format_value(
                "funnel_started_without_username", user_data
            ),
        )

@router.callback_query()
async def handle_callback_query(
    callback_query: CallbackQuery, bot: Bot, l10n: FluentLocalization
):
    try:
        callback_query_data = json.loads(callback_query.data.replace("'", '"'))
        status = callback_query_data.get("status")
        date = callback_query_data.get("date")
        time = callback_query_data.get("time")
        chat_id = callback_query.message.chat.id
        message_id = callback_query.message.message_id
        user = await bot.get_chat(chat_id)
        user_data = {
            "id": user.id,
            "first_name": user.full_name,
            "last_name": user.last_name,
            "username": user.username,
            "bio": user.bio,
            "status": status,
            "date": date,
            "time": time,
        }
        with open('setup.json', 'r') as file:
            setup_data = json.load(file)
        steps = len(setup_data['steps'])
        if isinstance(status, int):
            if  status < steps :
                ChatBotDBAPI().add_or_update_document(user_data)
                user_DB = ChatBotDBAPI().get_document_by_id(user.id)
                user_data["link"] = user_DB["link"]
                step = setup_data['steps'][status]
                if setup_data['steps'][status-1].get('button'):
                    await _clear_keyboard(bot, chat_id, message_id)
                for stage_key, stage_value in step['type'].items():
                        if 'text' in stage_key:
                            await bot.send_message(
                                chat_id,
                                stage_value,
                            )
                        if 'video' in stage_key:
                            if step.get('button', False) or isinstance(step, str):
                                inline_keyboard_status = _inline_keyboard_status({"status": status + 1},
                                                                                 step.get('button') if isinstance(
                                                                                     step.get('button'),
                                                                                     str) else None)
                            else:
                                inline_keyboard_status = None
                            video_id = await _send_video_to_user(
                                bot, chat_id, stage_value, inline_keyboard_status
                            )
                            if step.get('automatic_step') is not None:
                                create_task(
                                    _automatic_transition(
                                        ChatMessage(str({"status": status+1}), chat_id, video_id),
                                        bot,
                                        l10n,
                                        status,
                                        step['automatic_step'],
                                    )
                                )
                        if 'website' in stage_key:
                            botton_value = [[InlineKeyboardButton(text=stage_value[0], url=stage_value[1])]]
                            keyboard = InlineKeyboardMarkup(inline_keyboard=botton_value)
                            await bot.send_message(chat_id, text=stage_value[2], reply_markup=keyboard)
                            if step.get('automatic_step') is not None:
                                create_task(
                                    _automatic_transition(
                                        ChatMessage(str({"status": status+1}), chat_id, stage_value[1]),
                                        bot,
                                        l10n,
                                        status,
                                        step['automatic_step'],
                                    )
                                )

                        if 'zoomcall' in stage_key:
                            user_DB = ChatBotDBAPI().get_document_by_id(user.id)
                            user_data["link"] = user_DB["link"]
                            if user.username:
                                await bot.send_message(config.admin_chat_id, l10n.format_value("funnel_final_mini", user_data),reply_to_message_id=user_DB['topic_id'],)
                                await bot.send_message(
                                    config.admin_chat_id,
                                    l10n.format_value("funnel_final", user_data),
                                    parse_mode="HTML",
                                )
                            else:
                                await bot.send_message(config.admin_chat_id,
                                                       l10n.format_value("funnel_final_mini", user_data),
                                                       reply_to_message_id=user_DB['topic_id'], )
                                await bot.send_message(
                                    config.admin_chat_id,
                                    l10n.format_value("funnel_final_without_username", user_data),
                                    parse_mode="HTML",
                                )
                            ChatBotDBAPI().add_or_update_document(user_data)
                            await bot.send_message(
                                chat_id,
                                l10n.format_value("intro_final"),
                                reply_markup=_inline_keyboard_status(
                                    {"status": "final"}, "ЗАПИСАТЬСЯ НА ВСТРЕЧУ"
                                ),
                            )
                            if step.get('automatic_step') is not None:
                                create_task(
                                    _automatic_transition(
                                        ChatMessage(str({"status": status+1}), chat_id, video_id),
                                        bot,
                                        l10n,
                                        status,
                                        step['automatic_step'],
                                    )
                                )

        if isinstance(status, str):
                ChatBotDBAPI().add_or_update_document(user_data)
                await _clear_keyboard(bot, chat_id, message_id)
                if not date:
                    await bot.send_message(
                        chat_id,
                        l10n.format_value("camminicate_call_date"),
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=_generate_date_picker()
                        ),
                    )
                elif not time:
                    user_DB = ChatBotDBAPI().get_document_by_id(user.id)
                    user_data["link"] = user_DB["link"]
                    await bot.send_message(
                        config.admin_chat_id,
                        l10n.format_value("comminicate_call_started_mini", user_data),
                        reply_to_message_id=user_DB["topic_id"],
                    )
                    if user.username:
                        await bot.send_message(
                            config.admin_chat_id,
                            l10n.format_value("comminicate_call_started", user_data),
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_message(
                            config.admin_chat_id,
                            l10n.format_value(
                                "comminicate_call_started_without_username", user_data
                            ),
                        )
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=l10n.format_value("camminicate_call_time"),
                        )
                    except Exception as e:
                        print(e)
                    await _clear_keyboard(
                        bot,
                        chat_id,
                        message_id,
                        InlineKeyboardMarkup(inline_keyboard=_generate_time_sub_menu(date)),
                    )
                    try:
                        await bot.edit_forum_topic(
                            config.admin_chat_id,
                            message_thread_id=user_DB["topic_id"],
                            icon_custom_emoji_id="5433614043006903194",
                        )
                    except Exception as e:
                        print(e)
                else:
                    user_DB = ChatBotDBAPI().get_document_by_id(user.id)
                    user_data["link"] = user_DB["link"]
                    await bot.send_message(
                        config.admin_chat_id,
                        l10n.format_value("comminicate_call_final_mini", user_data),
                        reply_to_message_id=user_DB["topic_id"],
                    )
                    if user.username:
                        await bot.send_message(
                            config.admin_chat_id,
                            l10n.format_value("comminicate_call_final", user_data),
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_message(
                            config.admin_chat_id,
                            l10n.format_value(
                                "comminicate_call_final_without_username", user_data
                            ),
                        )
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=l10n.format_value(
                                "camminicate_call_finish", {"date": date, "time": time}
                            ),
                        )
                    except Exception as e:
                        print(e)
                    try:
                        await bot.edit_forum_topic(
                            config.admin_chat_id,
                            message_thread_id=user_DB["topic_id"],
                            icon_custom_emoji_id="5377544228505134960",
                        )
                    except Exception as e:
                        print(e)
    except Exception as e:
        print("Error:", e)


@router.message(F.text)
async def text_message(message: Message, bot: Bot, l10n: FluentLocalization):
    """
    Хэндлер на текстовые сообщения от пользователя

    :param message: сообщение от пользователя для админа(-ов)
    :param l10n: объект локализации
    """
    if len(message.text) > 4000:
        return await message.reply(l10n.format_value("too-long-text-error"))

    try:
        user = await bot.get_chat(message.from_user.id)
    except TelegramAPIError:
        return

    user_DB = ChatBotDBAPI().get_document_by_id(user.id)

    if not user_DB or "topic_id" not in user_DB or user_DB["topic_id"] is None:
        return

    await bot.send_message(
        config.admin_chat_id,
        message.html_text,
        reply_to_message_id=user_DB["topic_id"],
    )

    create_task(_send_expiring_notification(message, l10n))


@router.message(SupportedMediaFilter())
async def supported_media(message: Message, bot: Bot, l10n: FluentLocalization):
    """
    Хэндлер на медиафайлы от пользователя.
    Поддерживаются только типы, к которым можно добавить подпись (полный список см. в регистраторе внизу)

    :param message: медиафайл от пользователя
    :param l10n: объект локализации
    """
    if message.caption and len(message.caption) > 1000:
        return await message.reply(l10n.format_value("too-long-caption-error"))

    try:
        user = await bot.get_chat(message.from_user.id)
    except TelegramAPIError:
        return

    user_DB = ChatBotDBAPI().get_document_by_id(user.id)

    if not user_DB or "topic_id" not in user_DB or user_DB["topic_id"] is None:
        return

    await message.copy_to(
        config.admin_chat_id,
        message.caption,
        reply_to_message_id=user_DB["topic_id"],
    )

    create_task(_send_expiring_notification(message, l10n))


@router.message()
async def unsupported_types(message: Message, l10n: FluentLocalization):
    """
    Хэндлер на неподдерживаемые типы сообщений, т.е. те, к которым нельзя добавить подпись

    :param message: сообщение от пользователя
    :param l10n: объект локализации
    """

    if message.content_type not in (
        ContentType.NEW_CHAT_MEMBERS,
        ContentType.LEFT_CHAT_MEMBER,
        ContentType.VIDEO_CHAT_STARTED,
        ContentType.VIDEO_CHAT_ENDED,
        ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED,
        ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED,
        ContentType.NEW_CHAT_PHOTO,
        ContentType.DELETE_CHAT_PHOTO,
        ContentType.SUCCESSFUL_PAYMENT,
        "proximity_alert_triggered",
        ContentType.NEW_CHAT_TITLE,
        ContentType.PINNED_MESSAGE,
    ):
        await message.reply(l10n.format_value("unsupported-message-type-error"))
