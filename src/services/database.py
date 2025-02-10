from pymongo import MongoClient
from config import settings
from urllib.parse import quote_plus


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            encoded_password = quote_plus(settings.mongodb_password)
            username = settings.mongodb_username
            mongodb_uri = f"mongodb+srv://{username}:{encoded_password}@ai-cv-db.audhy.mongodb.net/?tls=true&tlsAllowInvalidCertificates=true"
            cls._instance.client = MongoClient(mongodb_uri)
            cls._instance.db = cls._instance.client[settings.db_name]
        return cls._instance

    def get_db(self):
        return self.db

def get_db():
    return Database().get_db()