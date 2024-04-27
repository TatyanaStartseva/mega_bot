from aiogram import Router, F
from aiogram.types import ContentType, Message
from fluent.runtime import FluentLocalization
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
    msg = await message.reply(l10n.format_value("message-deleted-now"))
    if config.remove_sent_confirmation:
        await sleep(15.0)
        await msg.delete()
        await message.delete()


@router.message(~F.reply_to_message)
async def has_no_reply(message: Message, l10n: FluentLocalization):
    """
    Хэндлер на сообщение от админа, не содержащее ответ (reply).
    В этом случае надо кинуть ошибку.

    :param message: сообщение от админа, не являющееся ответом на другое сообщение
    :param l10n: объект локализации
    """

    if message.content_type not in (
        ContentType.NEW_CHAT_MEMBERS,
        ContentType.LEFT_CHAT_MEMBER,
        ContentType.FORUM_TOPIC_CREATED,
        ContentType.FORUM_TOPIC_CLOSED,
        ContentType.FORUM_TOPIC_REOPENED,
        ContentType.FORUM_TOPIC_EDITED,
    ):
        create_task(_send_expiring_notification(message, l10n))
