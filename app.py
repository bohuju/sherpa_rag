from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import sys
from pathlib import Path
import shutil
import yaml

app = FastAPI()


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


class UploadRequest(BaseModel):
    """文件上传请求体"""
    file_path: str
    save_dir: str = "data"


class DownloadRequest(BaseModel):
    """文件下载请求体"""
    file_path: str


@app.post("/upload")
async def upload_file(request: UploadRequest):
    """
    上传文件文档库（通过文件路径）
    
    请求示例:
    {
        "file_path": "C:/Users/yfdwx/Desktop/test.txt",
        "save_dir": "data"
    }
    """
    try:
        source_path = Path(request.file_path)
        
        if not source_path.exists():
            return {"status": "error", "message": f"源文件不存在: {request.file_path}"}
        
        if not source_path.is_file():
            return {"status": "error", "message": f"不是有效文件: {request.file_path}"}
        
        save_dir = Path(request.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        dest_path = save_dir / source_path.name
        shutil.copy2(source_path, dest_path)
        
        return {
            "status": "success",
            "message": "文件上传成功",
            "filename": source_path.name,
            "save_path": str(dest_path)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/download")
async def download_file(request: DownloadRequest):
    """
    从服务器下载文件
    
    请求示例:
    {
        "file_path": "data/test.txt"
    }
    
    返回: 文件二进制内容
    """
    try:
        full_path = Path(request.file_path)
        
        if not full_path.exists():
            return {"status": "error", "message": "文件不存在"}
        
        if not full_path.is_file():
            return {"status": "error", "message": "不是有效文件"}
        
        return FileResponse(
            path=full_path,
            filename=full_path.name,
            media_type="application/octet-stream"
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/upload-multiple")
async def upload_multiple_files(file_paths: list[str], save_dir: str = "data"):
    """
    批量上传文件（通过文件路径）
    
    请求示例:
    {
        "file_paths": ["C:/Users/yfdwx/Desktop/file1.txt", "C:/Users/yfdwx/Desktop/file2.txt"],
        "save_dir": "data"
    }
    """
    try:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        errors = []
        
        for file_path in file_paths:
            source = Path(file_path)
            if source.exists() and source.is_file():
                dest = save_dir / source.name
                shutil.copy2(source, dest)
                uploaded_files.append(str(dest))
            else:
                errors.append(f"{file_path}: 文件不存在")
        
        return {
            "status": "success" if uploaded_files else "error",
            "message": f"成功上传 {len(uploaded_files)} 个文件",
            "files": uploaded_files,
            "errors": errors
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/list-files")
async def list_files(directory: str = "data"):
    """
    列出指定目录下的所有文件
    
    请求示例:
    - curl: curl "http://localhost:8000/list-files?directory=data"
    - curl: curl "http://localhost:8000/list-files?directory=data/subfolder"
    """
    try:
        # 安全检查
        dir_path = Path(directory).resolve()
        base_dir = Path("data").resolve()
        
        if not str(dir_path).startswith(str(base_dir)):
            return {"status": "error", "message": "非法路径访问"}
        
        if not dir_path.exists():
            return {"status": "error", "message": "目录不存在"}
        
        files = []
        for item in dir_path.iterdir():
            files.append({
                "name": item.name,
                "type": "file" if item.is_file() else "directory",
                "path": str(item.relative_to(Path("data")))
            })
        
        return {
            "status": "success",
            "directory": directory,
            "files": files
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)