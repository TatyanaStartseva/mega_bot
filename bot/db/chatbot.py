import time
import datetime

from pymongo import MongoClient
from bot.config_reader import config


class ChatBotDBAPI:
    _instance = None
    _connection_retry_interval = 600

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChatBotDBAPI, cls).__new__(cls)
            cls._instance.client = MongoClient(config.database_uri)
            cls._instance.db = cls._instance.client[config.database_name]
            cls._instance.collection = cls._instance.db[config.database_collection]
        return cls._instance

    def get_document_by_id(self, document_id):
        return self.collection.find_one({"_id": document_id})

    def get_document_by_topic_id(self, topic_id):
        return self.collection.find_one({"topic_id": topic_id})

    def add_or_update_document(self, data):
        document_id = data.get("id")
        existing_document = self.get_document_by_id(document_id)

        current_time = datetime.datetime.utcnow()
        if not existing_document:
            data["date_created"] = current_time

        data["date_updated"] = current_time

        self.collection.update_one({"_id": document_id}, {"$set": data}, upsert=True)
