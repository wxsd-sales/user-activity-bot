import os

from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

class Settings(object):
    api_url = os.environ.get("API_URL")
    
    bot_id = os.environ.get("MY_BOT_ID")
    token = os.environ.get("MY_BOT_TOKEN")
    port = os.environ.get("PORT", os.environ.get("MY_BOT_PORT"))
    secret = os.environ.get("MY_WEBHOOK_SECRET")

    client_id=os.environ.get("MY_CLIENT_ID")
    client_secret=os.environ.get("MY_CLIENT_SECRET")
    base_uri=os.environ.get("MY_BASE_URI")
    redirect_uri=base_uri + os.environ.get("MY_REDIRECT_URI")
    scopes=os.environ.get("MY_SCOPES")

    mongo_uri=os.environ.get("MY_MONGO_URI")
    mongo_db = os.environ.get("MY_MONGO_DB")


