import os

from dotenv import load_dotenv


load_dotenv()


OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
)


OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5"
)


TARGET_URL = os.getenv(
    "TARGET_URL",
    "http://127.0.0.1:8000"
)