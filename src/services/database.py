import certifi
from pymongo import MongoClient
from config import settings
from urllib.parse import quote_plus


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is not None:
            return cls._instance

        username = quote_plus(settings.mongodb_username)
        password = quote_plus(settings.mongodb_password)
        uri = (
            f"mongodb+srv://{username}:{password}@{settings.mongodb_host}"
            "/?retryWrites=true&w=majority"
        )
        client = MongoClient(
            uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
        )

        # Only cache once construction succeeded. Publishing a half-built
        # instance would make one transient DNS failure permanent for the
        # lifetime of the process.
        instance = super().__new__(cls)
        instance.client = client
        instance.db = client[settings.db_name]
        cls._instance = instance
        return instance

    def get_db(self):
        return self.db


def get_db():
    return Database().get_db()
