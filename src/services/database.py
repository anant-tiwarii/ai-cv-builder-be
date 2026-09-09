import certifi
from pymongo import MongoClient
from config import settings
from urllib.parse import quote_plus


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            username = quote_plus(settings.mongodb_username)
            password = quote_plus(settings.mongodb_password)
            uri = (
                f"mongodb+srv://{username}:{password}@{settings.mongodb_host}"
                "/?retryWrites=true&w=majority"
            )
            cls._instance.client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
            )
            cls._instance.db = cls._instance.client[settings.db_name]
        return cls._instance

    def get_db(self):
        return self.db


def get_db():
    return Database().get_db()
