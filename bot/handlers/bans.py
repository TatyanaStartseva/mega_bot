from aiogram import Router, F

from bot.config_reader import config

router = Router()
router.message.filter(F.chat.id == config.admin_chat_id)
