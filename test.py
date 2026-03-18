"""
将 PKL 文件转换为语料库并拆分成长文档
"""
import sys
import os
os.environ['OPENAI_API_KEY'] = 'mock-api-key'

project_root = os.path.dirname(__file__)
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

import pickle
import types
import json

api_package = types.ModuleType('api')
api_package.__path__ = [os.path.join(src_path, 'ultrarag')]
sys.modules['api'] = api_package

openai_client = types.ModuleType('api.openai_client')

def get_first_message_content(*args, **kwargs):
    return None

def OpenAIClient(*args, **kwargs):
    return None

def get_response_text(*args, **kwargs):
    return None

openai_client.get_first_message_content = get_first_message_content
openai_client.OpenAIClient = OpenAIClient
openai_client.get_response_text = get_response_text

sys.modules['api.openai_client'] = openai_client
api_package.openai_client = openai_client

import ultrarag.api
import ultrarag.client
import ultrarag.mcp_logging
import ultrarag.utils
import ultrarag.server

api_package.api = ultrarag.api
api_package.client = ultrarag.client
api_package.mcp_logging = ultrarag.mcp_logging
api_package.utils = ultrarag.utils
api_package.server = ultrarag.server

print("=" * 60)
print("加载 PKL 文件")
print("=" * 60)

with open("data/google_leveldb.pkl", "rb") as f:
    vector_db = pickle.load(f)

print(f"原始文档数量: {len(vector_db.items)}")

CHUNK_SIZE = 2000
OVERLAP = 200

def split_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

corpus_data = []
chunk_id = 0

for doc in vector_db.items:
    text = doc.text
    file_path = doc.meta_data.get('file_path', '')
    file_type = doc.meta_data.get('type', '')

    if len(text) > CHUNK_SIZE:
        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            corpus_data.append({
                'id': f"{doc.id}_chunk_{i}",
                'contents': chunk,
                'file_path': file_path,
                'title': f"{file_path} (chunk {i+1}/{len(chunks)})",
                'type': file_type,
            })
            chunk_id += 1
    else:
        corpus_data.append({
            'id': doc.id,
            'contents': text,
            'file_path': file_path,
            'title': file_path,
            'type': file_type,
        })

os.makedirs("data", exist_ok=True)

corpus_path = "data/leveldb_corpus.jsonl"
with open(corpus_path, 'w', encoding='utf-8') as f:
    for item in corpus_data:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

print(f"\n✅ 语料库已保存到: {corpus_path}")
print(f"   原始文档: {len(vector_db.items)}")
print(f"   拆分后: {len(corpus_data)} 个 chunks")
print(f"   平均每 chunk: ~{CHUNK_SIZE} 字符")
