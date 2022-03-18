import traceback

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from datetime import datetime, timedelta

from lib.settings import Settings

class MongoUserController(object):
    def __init__(self):
        self.client = MongoClient(Settings.mongo_uri)
        self.db = self.client[Settings.mongo_db]
        self.users = self.db["users"]
        #expireAfterSeconds:0 actually means that the document will expire at the datetime specified by expire_date
        self.users.create_index("expire_date", expireAfterSeconds=0)
        self.expires_seconds = 3600 * 8#hours

    def count(self):
        return self.users.estimated_document_count()

    def find(self, args):
        return self.users.find(args)

    def find_one(self, args):
        return self.users.find_one(args)

    def get_expire_date(self):
        return datetime.utcnow() + timedelta(seconds=self.expires_seconds)

    def insert_user(self, person_id, token):
        result = None
        try:
            document = {
                        "person_id":person_id,
                        "token":token,
                        "expire_date":self.get_expire_date(),
                        #"refresh_token":refresh_token
            }
            self.users.update_one({"person_id":person_id}, {"$set": document}, upsert=True)
            result = document
        except Exception as e:
            traceback.print_exc()
        return result

    def get_token(self, person_id):
        token = None
        user = self.users.find_one({"person_id":person_id})
        if user != None:
            token = user.get('token')
        return token

    def is_user(self, person_id):
        user = self.get_user(person_id)
        if user != None:
            user = True
        return user
        
    def get_user(self, person_id):
        return self.users.find_one({"person_id":person_id})

    def update_user(self, person_id, update_payload):
        self.users.update_one({"person_id":person_id}, {"$set":update_payload})

    def update_expire_date(self, person_id):
        update_payload = {"expire_date":self.get_expire_date()}
        self.update_user(person_id, update_payload)

    def delete_user(self, person_id):
        self.users.delete_one({"person_id":person_id})

    def delete_one(self, query):
        deleted_count = 0
        try:
            x = self.users.delete_one(query)
            deleted_count = x.deleted_count
        except Exception as e:
            traceback.print_exc()
        return deleted_count


class UserDB(object):
    db = MongoUserController()
