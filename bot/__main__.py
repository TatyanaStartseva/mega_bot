import asyncio
import logging

from aiogram import Bot, Dispatcher
from bot.handlers import setup_routers
from fluent.runtime import FluentLocalization, FluentResourceLoader
from bot.middlewares import L10nMiddleware
from pathlib import Path

from bot.config_reader import config
import json

async def main():

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    locales_dir = Path(__file__).parent.joinpath("locales")

    l10n_loader = FluentResourceLoader(str(locales_dir) + "/{locale}")
    l10n = FluentLocalization(["ru"], ["main.ftl", "errors.ftl"], l10n_loader)

    bot = Bot(token=config.bot_token.get_secret_value())
    dp = Dispatcher()
    router = setup_routers()
    dp.include_router(router)
    dp.update.middleware(L10nMiddleware(l10n))

    try:
        await bot.delete_webhook()
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


asyncio.run(main())
