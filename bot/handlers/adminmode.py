from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from fluent.runtime import FluentLocalization
from bot.db import ChatBotDBAPI
from asyncio import create_task, sleep

from bot.config_reader import config

router = Router()
router.message.filter(F.chat.id == config.admin_chat_id)


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


def extract_id(message: Message) -> int:
    """
    Извлекает ID юзера по сообщению

    :param message: сообщение, из хэштега в котором нужно достать айди пользователя
    :return: ID пользователя, извлечённый из хэштега в сообщении
    """

    topic_id = message.message_thread_id
    user_DB = ChatBotDBAPI().get_document_by_topic_id(topic_id)

    if not user_DB or "id" not in user_DB:
        raise ValueError("Отсутствует связь топика с пользователем из бота :(")

    return int(user_DB["id"])


@router.message(F.reply_to_message)
async def reply_to_user(message: Message, l10n: FluentLocalization):
    """
    Ответ администратора на сообщение юзера (отправленное ботом).
    Используется метод copy_message, поэтому ответить можно чем угодно, хоть опросом.

    :param message: сообщение от админа, являющееся ответом на другое сообщение
    :param l10n: объект локализации
    """

    if (
        message.forum_topic_edited
        or message.forum_topic_closed
        or message.forum_topic_created
        or message.forum_topic_reopened
    ):
        await message.delete()
        return

    try:
        user_id = extract_id(message.reply_to_message)
    except ValueError as ex:
        return await message.reply(str(ex))

    try:
        await message.copy_to(user_id)
        create_task(_send_expiring_notification(message, l10n))
    except TelegramAPIError as ex:
        await message.reply(
            l10n.format_value(
                msg_id="cannot-answer-to-user-error", args={"error": ex.message}
            )
        )
