from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import sys
from pathlib import Path
import shutil
import yaml
import os
import hashlib
import aiofiles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_UPLOAD_DIR = Path("data")
BASE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.md', '.json', '.csv', '.xlsx', '.xml', '.html', '.htm', '.ppt', '.pptx'}
MAX_FILE_SIZE = 100 * 1024 * 1024


def validate_file_path(file_path: str) -> bool:
    """验证文件路径安全，防止路径穿越攻击"""
    try:
        resolved = Path(file_path).resolve()
        base_resolved = BASE_UPLOAD_DIR.resolve()
        return str(resolved).startswith(str(base_resolved))
    except Exception:
        return False


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """检查文件类型是否允许"""
    ext = get_file_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def calculate_file_hash(file_path: Path) -> str:
    """计算文件MD5哈希"""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


class IndexRequest(BaseModel):
    """索引生成请求体"""
    pipeline_file: str = "examples/sherpa_index.yaml"


def index_generate(pipeline_file: str = "examples/corpus_index.yaml"):
    """生成索引"""
    cmd = ["ultrarag", "run", pipeline_file]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode


@app.post("/generate-index")
async def generate_index(request: IndexRequest):
    """
    生成索引接口
    
    请求示例:
    {
        "pipeline_file": "examples/sherpa_index.yaml"
    }
    """
    try:
        code = index_generate(request.pipeline_file)
        if code == 0:
            return {"status": "success", "message": "索引生成成功"}
        else:
            return {"status": "error", "message": f"索引生成失败，代码: {code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    save_dir: str = Form("data", description="保存目录")
):
    """
    上传文件到服务器（支持远程传输）
    
    使用 form-data 方式上传文件，客户端示例:
    
    ```python
    import requests
    
    url = "http://localhost:8000/upload"
    files = {"file": open("test.txt", "rb")}
    data = {"save_dir": "data"}
    response = requests.post(url, files=files, data=data)
    print(response.json())
    ```
    
    或者使用 curl:
    ```bash
    curl -X POST -F "file=@test.txt" -F "save_dir=data" http://localhost:8000/upload
    ```
    """
    try:
        if not file.filename:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "文件名不能为空"}
            )

        if not is_allowed_file(file.filename):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error", 
                    "message": f"不支持的文件类型。允许的类型: {', '.join(ALLOWED_EXTENSIONS)}"
                }
            )

        save_dir_path = BASE_UPLOAD_DIR / save_dir
        save_dir_path.mkdir(parents=True, exist_ok=True)

        file_path = save_dir_path / file.filename
        
        content = await file.read()
        
        if len(content) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)"
                }
            )

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        file_hash = calculate_file_hash(file_path)

        return {
            "status": "success",
            "message": "文件上传成功",
            "filename": file.filename,
            "save_path": str(file_path),
            "size": len(content),
            "md5": file_hash
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/download")
@app.get("/download/{file_path:path}")
async def download_file(file_path: str = None):
    """
    从服务器下载文件
    
    使用方式:
    - GET /download?file_path=data/test.txt
    - GET /download/data/test.txt
    
    客户端下载示例:
    
    ```python
    import requests
    
    url = "http://localhost:8000/download"
    params = {"file_path": "data/test.txt"}
    response = requests.get(url, params=params)
    
    # 保存文件
    with open("downloaded.txt", "wb") as f:
        f.write(response.content)
    ```
    
    或者使用 curl:
    ```bash
    curl -o downloaded.txt "http://localhost:8000/download?file_path=data/test.txt"
    ```
    """
    try:
        if file_path is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "请提供 file_path 参数"}
            )

        if not validate_file_path(file_path):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "非法路径访问"}
            )

        full_path = Path(file_path)
        
        if not full_path.exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "文件不存在"}
            )
        
        if not full_path.is_file():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "不是有效文件"}
            )
        
        return FileResponse(
            path=full_path,
            filename=full_path.name,
            media_type="application/octet-stream",
            as_attachment=True
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/upload-multiple")
async def upload_multiple_files(
    files: list[UploadFile] = File(..., description="要上传的多个文件"),
    save_dir: str = Form("data", description="保存目录")
):
    """
    批量上传文件（支持远程传输）
    
    使用 form-data 方式上传多个文件，客户端示例:
    
    ```python
    import requests
    
    url = "http://localhost:8000/upload-multiple"
    files = [
        ("files", ("file1.txt", open("file1.txt", "rb"), "text/plain")),
        ("files", ("file2.pdf", open("file2.pdf", "rb"), "application/pdf")),
    ]
    data = {"save_dir": "data"}
    response = requests.post(url, files=files, data=data)
    print(response.json())
    ```
    
    或者使用 curl:
    ```bash
    curl -X POST -F "files=@file1.txt" -F "files=@file2.txt" -F "save_dir=data" http://localhost:8000/upload-multiple
    ```
    """
    try:
        save_dir_path = BASE_UPLOAD_DIR / save_dir
        save_dir_path.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        errors = []
        
        for file in files:
            try:
                if not file.filename:
                    errors.append({"filename": "unknown", "error": "文件名不能为空"})
                    continue
                
                if not is_allowed_file(file.filename):
                    errors.append({"filename": file.filename, "error": "不支持的文件类型"})
                    continue
                
                file_path = save_dir_path / file.filename
                
                content = await file.read()
                
                if len(content) > MAX_FILE_SIZE:
                    errors.append({"filename": file.filename, "error": f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)"})
                    continue
                
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(content)
                
                file_hash = calculate_file_hash(file_path)
                
                uploaded_files.append({
                    "filename": file.filename,
                    "save_path": str(file_path),
                    "size": len(content),
                    "md5": file_hash
                })
            except Exception as e:
                errors.append({"filename": file.filename if file.filename else "unknown", "error": str(e)})
        
        return {
            "status": "success" if uploaded_files else "error",
            "message": f"成功上传 {len(uploaded_files)} 个文件，失败 {len(errors)} 个",
            "files": uploaded_files,
            "errors": errors
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/list-files")
async def list_files(directory: str = "data", include_details: bool = False):
    """
    列出指定目录下的所有文件
    
    参数:
    - directory: 目录路径 (默认: "data")
    - include_details: 是否包含详细信息 (默认: false)
    
    请求示例:
    - curl: curl "http://localhost:8000/list-files?directory=data"
    - curl: curl "http://localhost:8000/list-files?directory=data/subfolder&include_details=true"
    """
    try:
        dir_path = (BASE_UPLOAD_DIR / directory).resolve()
        
        if not validate_file_path(str(dir_path)):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "非法路径访问"}
            )
        
        if not dir_path.exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "目录不存在"}
            )
        
        if not dir_path.is_dir():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "不是有效目录"}
            )
        
        files = []
        for item in dir_path.iterdir():
            file_info = {
                "name": item.name,
                "type": "file" if item.is_file() else "directory",
                "path": str(item.relative_to(BASE_UPLOAD_DIR))
            }
            
            if include_details and item.is_file():
                stat = item.stat()
                file_info["size"] = stat.st_size
                file_info["size_formatted"] = f"{stat.st_size / 1024:.2f} KB" if stat.st_size < 1024 * 1024 else f"{stat.st_size / 1024 / 1024:.2f} MB"
                file_info["modified_time"] = stat.st_mtime
                file_info["extension"] = item.suffix.lower()
            
            files.append(file_info)
        
        files.sort(key=lambda x: (x["type"] != "file", x["name"].lower()))
        
        return {
            "status": "success",
            "directory": directory,
            "total": len(files),
            "files": files
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.delete("/delete-file")
@app.delete("/delete-file/{file_path:path}")
async def delete_file(file_path: str = None):
    """
    删除服务器上的文件
    
    使用方式:
    - DELETE /delete-file?file_path=data/test.txt
    - DELETE /delete-file/data/test.txt
    
    客户端示例:
    ```python
    import requests
    
    url = "http://localhost:8000/delete-file"
    params = {"file_path": "data/test.txt"}
    response = requests.delete(url, params=params)
    print(response.json())
    ```
    """
    try:
        if file_path is None:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "请提供 file_path 参数"}
            )

        if not validate_file_path(file_path):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": "非法路径访问"}
            )

        full_path = Path(file_path)
        
        if not full_path.exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "文件不存在"}
            )
        
        if not full_path.is_file():
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "不是有效文件"}
            )
        
        full_path.unlink()
        
        return {
            "status": "success",
            "message": "文件删除成功",
            "file_path": file_path
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/pipelines")
async def list_pipelines():
    """
    列出可用的 pipeline 文件
    
    请求示例:
    curl "http://localhost:8000/pipelines"
    """
    try:
        param_dir = Path("examples/parameter")
        
        if not param_dir.exists():
            return {"status": "error", "message": "参数目录不存在"}
        
        pipelines = []
        for yaml_file in param_dir.glob("*.yaml"):
            pipelines.append({
                "name": yaml_file.stem,
                "path": str(yaml_file)
            })
        
        return {
            "status": "success",
            "pipelines": pipelines
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


class PipelineParamsUpdate(BaseModel):
    """Pipeline 参数更新请求体"""
    params: dict


@app.get("/pipeline-params")
async def get_pipeline_params(parameter_file: str):
    """
    读取 pipeline 参数
    
    请求示例:
    curl "http://localhost:8000/pipeline-params?parameter_file=examples/parameter/corpus_index_parameter.yaml"
    
    或者使用 pipelines 接口返回的 path:
    curl "http://localhost:8000/pipeline-params?parameter_file=examples/parameter/corpus_index_parameter.yaml"
    """
    try:
        param_path = Path("examples/parameter") / parameter_file
        
        if not param_path.exists():
            return {"status": "error", "message": f"参数文件不存在: {parameter_file}"}
        
        with open(param_path, "r", encoding="utf-8") as f:
            params = yaml.safe_load(f)
        
        return {
            "status": "success",
            "parameter_file": parameter_file,
            "params": params
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.put("/pipeline-params")
async def update_pipeline_params(parameter_file: str, update: PipelineParamsUpdate):
    """
    更新 pipeline 参数
    
    请求示例:
    curl -X PUT "http://localhost:8000/pipeline-params?parameter_file=examples/parameter/corpus_index_parameter.yaml" \
         -H "Content-Type: application/json" \
         -d '{"params": {"retriever": {"batch_size": 32}}}'
    """
    try:
        param_path = Path("examples/parameter") / parameter_file
        
        if not param_path.exists():
            return {"status": "error", "message": f"参数文件不存在: {parameter_file}"}
        
        with open(param_path, "r", encoding="utf-8") as f:
            current_params = yaml.safe_load(f)
        
        def deep_update(base: dict, update: dict):
            for key, value in update.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    deep_update(base[key], value)
                else:
                    base[key] = value
        
        deep_update(current_params, update.params)
        
        with open(param_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(current_params, f, allow_unicode=True, default_flow_style=False)
        
        return {
            "status": "success",
            "message": "参数更新成功",
            "parameter_file": parameter_file
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


class PipelineRunRequest(BaseModel):
    """Pipeline 运行请求体"""
    pipeline_file: str = "examples/corpus_index.yaml"
    parameter_file: str = "examples/parameter/corpus_index_parameter.yaml"
    query: Optional[str] = None
    corpus_path: Optional[str] = None
    async_mode: bool = False


@app.post("/pipeline/run")
async def run_pipeline(request: PipelineRunRequest):
    """
    运行 UltraRAG Pipeline
    
    请求示例:
    ```python
    import requests
    
    url = "http://localhost:8000/pipeline/run"
    data = {
        "pipeline_file": "examples/corpus_index.yaml",
        "parameter_file": "examples/parameter/corpus_index_parameter.yaml"
    }
    response = requests.post(url, json=data)
    print(response.json())
    ```
    
    或者运行 RAG 查询:
    ```python
    url = "http://localhost:8000/pipeline/run"
    data = {
        "pipeline_file": "examples/rag_deploy.yaml",
        "parameter_file": "examples/parameter/rag_deploy_parameter.yaml",
        "query": "什么是 UltraRAG?"
    }
    response = requests.post(url, json=data)
    ```
    """
    try:
        from ultrarag.api import PipelineCall
        
        pipeline_file = request.pipeline_file
        parameter_file = request.parameter_file
        
        if not Path(pipeline_file).exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"Pipeline 文件不存在: {pipeline_file}"}
            )
        
        if not Path(parameter_file).exists():
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": f"参数文件不存在: {parameter_file}"}
            )
        
        result = PipelineCall(
            pipeline_file=pipeline_file,
            parameter_file=parameter_file
        )
        
        return {
            "status": "success",
            "message": "Pipeline 执行成功",
            "pipeline_file": pipeline_file,
            "parameter_file": parameter_file,
            "result": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/pipeline/index")
async def build_index(
    pipeline_file: str = Form("examples/corpus_index.yaml"),
    parameter_file: str = Form("examples/parameter/corpus_index_parameter.yaml"),
    corpus_path: str = Form(None),
    overwrite: bool = Form(True)
):
    """
    构建索引 API
    
    使用 form-data 方式:
    ```python
    import requests
    
    url = "http://localhost:8000/pipeline/index"
    data = {
        "pipeline_file": "examples/corpus_index.yaml",
        "parameter_file": "examples/parameter/corpus_index_parameter.yaml",
        "corpus_path": "data/sherpa_text.jsonl",
        "overwrite": True
    }
    response = requests.post(url, data=data)
    ```
    """
    try:
        from ultrarag.api import PipelineCall
        
        if corpus_path:
            if not Path(corpus_path).exists():
                return JSONResponse(
                    status_code=404,
                    content={"status": "error", "message": f"语料库文件不存在: {corpus_path}"}
                )
            
            with open(parameter_file, "r", encoding="utf-8") as f:
                params = yaml.safe_load(f)
            
            params["retriever"]["corpus_path"] = corpus_path
            params["retriever"]["overwrite"] = overwrite
            
            with open(parameter_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(params, f, allow_unicode=True, default_flow_style=False)
        
        result = PipelineCall(
            pipeline_file=pipeline_file,
            parameter_file=parameter_file
        )
        
        return {
            "status": "success",
            "message": "索引构建成功",
            "corpus_path": corpus_path,
            "index_path": params.get("retriever", {}).get("index_backend_configs", {}).get("faiss", {}).get("index_path", "index/index_sherpa.index"),
            "result": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/pipeline/query")
async def query_rag(
    pipeline_file: str = Form("examples/rag_deploy.yaml"),
    parameter_file: str = Form("examples/parameter/rag_deploy_parameter.yaml"),
    query: str = Form(..., description="查询内容")
):
    """
    RAG 查询 API
    
    使用 form-data 方式:
    ```python
    import requests
    
    url = "http://localhost:8000/pipeline/query"
    data = {
        "pipeline_file": "examples/rag_deploy.yaml",
        "parameter_file": "examples/parameter/rag_deploy_parameter.yaml",
        "query": "什么是 UltraRAG?"
    }
    response = requests.post(url, data=data)
    print(response.json())
    ```
    """
    try:
        from ultrarag.api import PipelineCall
        
        result = PipelineCall(
            pipeline_file=pipeline_file,
            parameter_file=parameter_file
        )
        
        final_result = result.get("final_result", result)
        
        return {
            "status": "success",
            "query": query,
            "result": final_result,
            "full_result": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "UltraRAG API Server",
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)