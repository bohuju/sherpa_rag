import requests

file_path = r"C:\Users\yfdwx\Desktop\ultra-rag.docx"
with open(file_path, "rb") as f:
    files = {"file": f}
    response = requests.post("http://127.0.0.1:8001/upload-file", files=files)

print(response.json())