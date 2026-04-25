# ================================================
# File: chatbot_routes.py
# (Đã chuyển đổi từ FastAPI sang Flask Blueprint)
# ================================================

import os
import google.generativeai as genai
import chromadb
from flask import Blueprint, request, jsonify, render_template
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# =======================
# Tải .env (Từ thư mục gốc của dự án)
# =======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Thư mục 'duanquantibenhvien'
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

# =======================
# Cấu hình / DEBUG
# =======================
CHAT_MODEL = os.getenv("MODEL_NAME", "gemini-1.5-flash") # Sửa thành 1.5
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "knowledge_base")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY", "")

print(">>> [Chatbot] Tải model:", CHAT_MODEL)
print(">>> [Chatbot] Tải collection:", COLLECTION_NAME)

if not GOOGLE_KEY:
    print(">>> [Chatbot] LỖI: GOOGLE_API_KEY chưa được cấu hình trong .env")
    # raise RuntimeError("GOOGLE_API_KEY chưa được cấu hình trong .env")
else:
    genai.configure(api_key=GOOGLE_KEY)

# =======================
# Tải model embedding (phải giống hệt model trong ingest.py)
# =======================
print(">>> [Chatbot] Đang tải model embedding (SentenceTransformer)...")
try:
    emb_model = SentenceTransformer("intfloat/multilingual-e5-small")
    print(">>> [Chatbot] Tải model embedding thành công.")
except Exception as e:
    print(f">>> [Chatbot] LỖI khi tải model embedding: {e}")
    emb_model = None

# =======================
# Chroma client (Kết nối DB vector)
# =======================
try:
    client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "vectordb"))
    coll = client.get_collection(COLLECTION_NAME) # Dùng get_collection, vì ingest.py đã tạo
    print(f">>> [Chatbot] Đã kết nối collection '{COLLECTION_NAME}' với {coll.count()} tài liệu.")
except Exception as e:
    print(f">>> [Chatbot] LỖI: Không kết nối được ChromaDB/Collection: {e}")
    print(">>> [Chatbot] Vui lòng chạy file 'ingest.py' trước.")
    coll = None

# =======================
# Prompt & Helpers
# =======================
SYSTEM_PROMPT = (
    "Bạn là trợ lý y tế ảo của bệnh viện HOPITAL, nói tiếng Việt. "
    "Bạn chỉ được trả lời dựa trên các tài liệu tham khảo được cung cấp dưới đây. "
    "Tuyệt đối không tự ý bịa ra thông tin. "
    "Nếu tài liệu không đủ, hãy trả lời: 'Xin lỗi, thông tin này không có trong tài liệu của tôi. Bạn vui lòng liên hệ nhân viên y tế để được tư vấn chính xác.' "
    "Luôn trích dẫn nguồn [1], [2]... sau mỗi câu có dùng thông tin từ tài liệu."
)

def embed_query(text: str):
    if emb_model is None:
        raise RuntimeError("Embedding model chưa được tải.")
    embedding = emb_model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

def retrieve(question: str, top_k: int = 5):
    if coll is None:
        raise RuntimeError("Collection chưa sẵn sàng.")
    q_emb = embed_query(question)
    res = coll.query(
        query_embeddings=[q_emb],
        n_results=max(1, top_k),
        include=["documents", "metadatas", "distances"],
    )
    items = []
    if res and res.get("documents"):
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            items.append({
                "text": doc,
                "source": (meta or {}).get("source", "N/A"),
                "score": float(dist) if dist is not None else 0.0
            })
    return items

def build_prompt(question: str, contexts: list[dict]):
    if contexts:
        ctx = "\n\n---\n\n".join(
            f"[{i+1}] (Nguồn: {c['source']})\n{c['text']}"
            for i, c in enumerate(contexts)
        )
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Tài liệu tham chiếu:\n{ctx}\n\n"
            f"Câu hỏi: {question}\n"
            f"Hãy trả lời bằng tiếng Việt, có đánh số tham chiếu [1], [2] tương ứng."
        )
    else:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"(Không tìm thấy tài liệu tham chiếu nào phù hợp.)\n"
            f"Câu hỏi: {question}\n"
            f"Hãy trả lời dựa trên hướng dẫn (nói rằng không có thông tin)."
        )

# ==================================
# === TẠO FLASK BLUEPRINT (Module) ===
# ==================================
chatbot_bp = Blueprint(
    'chatbot', 
    __name__,
    # Trỏ đến thư mục 'static' của dự án chính
    # Chúng ta không cần trang demo riêng nữa
    template_folder='templates',
    static_folder='static'
)

# =======================
# API (dùng cho Chat Widget)
# =======================
@chatbot_bp.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        # Lấy dữ liệu từ yêu cầu (JSON)
        data = request.json
        question = data.get('query', '').strip()  # Câu hỏi người dùng gửi lên
        top_k = data.get('top_k', 5)  # Số lượng tài liệu cần truy xuất

        # Kiểm tra nếu không có câu hỏi
        if not question:
            return jsonify({"error": "Không có câu hỏi"}), 400
        
        # Kiểm tra nếu không có dữ liệu ChromaDB hoặc model embedding
        if coll is None or emb_model is None:
            return jsonify({"answer": "Xin lỗi, hệ thống chatbot đang bảo trì. Vui lòng thử lại sau."}), 500

        # 1. Tìm tài liệu (Retrieval)
        ctx = retrieve(question, top_k)
        
        # 2. Xây dựng prompt cho câu trả lời
        prompt = build_prompt(question, ctx)

        # 3. Gọi model Google Gemini (hoặc model AI khác) để sinh câu trả lời
        model = genai.GenerativeModel(CHAT_MODEL)
        resp = model.generate_content(prompt)
        answer = (getattr(resp, "text", None) or "").strip()

        # Nếu không có câu trả lời, trả lại thông báo lỗi
        if not answer:
            answer = "Xin lỗi, tôi không thể tạo câu trả lời cho câu hỏi này."

        # Trả về câu trả lời và các context tham chiếu
        return jsonify({
            "answer": answer,
            "contexts": ctx  # Gửi cả context để debug (tùy chọn)
        })

    except genai.types.generation_types.BlockedPromptException as e:
        return jsonify({"error": f"Prompt bị chặn: {e}"}), 400
    except Exception as e:
        print(">>> LỖI TRONG /api/chat:", repr(e))
        return jsonify({"error": "Lỗi máy chủ khi xử lý câu hỏi."}), 500