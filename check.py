# check_db.py
import os, pathlib, chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

BASE_DIR = pathlib.Path(__file__).resolve().parent
DB_DIR = str((BASE_DIR / "vectordb").resolve())

load_dotenv(BASE_DIR / ".env")
name = os.getenv("COLLECTION_NAME", "knowledge_base")

print("DB path =", DB_DIR)
client = chromadb.Client(Settings(persist_directory=DB_DIR, anonymized_telemetry=False))
print("Collections =", [c.name for c in client.list_collections()])

coll = client.get_or_create_collection(name)
print("Active collection =", name)
print("Count =", coll.count())
print("Peek =", coll.peek())
