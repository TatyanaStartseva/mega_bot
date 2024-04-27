from pydantic import BaseSettings, SecretStr
import json

class Settings(BaseSettings):
    bot_token: SecretStr
    admin_chat_id: int
    remove_sent_confirmation: bool = False
    database_uri: str = ''
    database_name: str = ''
    database_collection: str = ''

    @classmethod
    def load_from_json(cls):
        with open("setup.json", 'r') as file:
            setup_data = json.load(file)
        return cls(
            bot_token=SecretStr(setup_data['bot_token']),
            admin_chat_id=setup_data['admin_chat_id'],
        )
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"


config = Settings.load_from_json()
