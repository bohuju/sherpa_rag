from typing import TypedDict, Annotated, Optional, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pathlib import Path
import json
import requests
from dataclasses import dataclass


API_BASE_URL = "http://localhost:8000"


@dataclass
class UltraRAGConfig:
    api_base_url: str = "http://localhost:8000"
    timeout: int = 300
    use_api: bool = True


ultrarag_config = UltraRAGConfig()


def set_ultrarag_config(api_base_url: str = "http://localhost:8000", timeout: int = 300, use_api: bool = True):
    """配置 UltraRAG 客户端"""
    global ultrarag_config
    ultrarag_config = UltraRAGConfig(
        api_base_url=api_base_url,
        timeout=timeout,
        use_api=use_api
    )


class UltraRAGState(TypedDict):
    query: Optional[str]
    corpus_path: Optional[str]
    pipeline_file: Optional[str]
    parameter_file: Optional[str]
    index_path: Optional[str]
    results: Optional[dict]
    status: str
    error: Optional[str]


def load_ultrarag_modules():
    try:
        from ultrarag.api import PipelineCall, ToolCall
        return PipelineCall, ToolCall
    except ImportError:
        raise ImportError(
            "UltraRAG package not found. Please ensure ultrarag is installed: "
            "pip install ultrarag"
        )


def call_api(endpoint: str, data: dict = None, params: dict = None) -> dict:
    """调用 UltraRAG API"""
    url = f"{ultrarag_config.api_base_url}{endpoint}"
    
    try:
        response = requests.post(url, json=data, params=params, timeout=ultrarag_config.timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"API call failed: {str(e)}")


def corpus_index_node(state: UltraRAGState) -> UltraRAGState:
    """
    LangGraph 节点: 构建语料库索引
    
    支持两种模式:
    1. API 模式 (默认): 调用远程 UltraRAG API
    2. 直接模式: 直接调用 PipelineCall
    
    输入状态:
        - corpus_path: 语料库文件路径
        - pipeline_file: pipeline 配置文件
        - parameter_file: 参数配置文件
        - index_path: 索引路径
    
    输出状态:
        - status: 状态 (success/error)
        - index_path: 生成的索引路径
        - results: 完整返回结果
        - error: 错误信息
    """
    try:
        corpus_path = state.get("corpus_path")
        pipeline_file = state.get("pipeline_file", "examples/corpus_index.yaml")
        parameter_file = state.get("parameter_file", "examples/parameter/corpus_index_parameter.yaml")
        
        if ultrarag_config.use_api:
            api_data = {
                "pipeline_file": pipeline_file,
                "parameter_file": parameter_file,
                "corpus_path": corpus_path
            }
            
            result = call_api("/pipeline/index", data=api_data)
            
            if result.get("status") == "success":
                return {
                    **state,
                    "status": "success",
                    "results": result.get("result"),
                    "index_path": result.get("index_path"),
                    "error": None
                }
            else:
                return {
                    **state,
                    "status": "error",
                    "results": None,
                    "error": result.get("message", "Unknown error")
                }
        else:
            PipelineCall, _ = load_ultrarag_modules()
            
            if not corpus_path:
                raise ValueError("corpus_path is required for indexing")
            
            if not Path(corpus_path).exists():
                raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
            
            result = PipelineCall(
                pipeline_file=pipeline_file,
                parameter_file=parameter_file
            )
            
            return {
                **state,
                "status": "success",
                "results": result,
                "index_path": result.get("index_path", "index/index_sherpa.index"),
                "error": None
            }
        
    except Exception as e:
        return {
            **state,
            "status": "error",
            "results": None,
            "error": str(e)
        }


def rag_query_node(state: UltraRAGState) -> UltraRAGState:
    """
    LangGraph 节点: RAG 查询
    
    支持两种模式:
    1. API 模式 (默认): 调用远程 UltraRAG API
    2. 直接模式: 直接调用 PipelineCall
    
    输入状态:
        - query: 查询字符串
        - pipeline_file: pipeline 配置文件
        - parameter_file: 参数配置文件
    
    输出状态:
        - status: 状态
        - results: 查询结果
        - error: 错误信息
    """
    try:
        query = state.get("query")
        pipeline_file = state.get("pipeline_file", "examples/rag_deploy.yaml")
        parameter_file = state.get("parameter_file", "examples/parameter/rag_deploy_parameter.yaml")
        
        if not query:
            raise ValueError("query is required for RAG query")
        
        if ultrarag_config.use_api:
            api_data = {
                "pipeline_file": pipeline_file,
                "parameter_file": parameter_file,
                "query": query
            }
            
            result = call_api("/pipeline/query", data=api_data)
            
            if result.get("status") == "success":
                return {
                    **state,
                    "status": "success",
                    "results": result.get("result"),
                    "error": None
                }
            else:
                return {
                    **state,
                    "status": "error",
                    "results": None,
                    "error": result.get("message", "Unknown error")
                }
        else:
            PipelineCall, _ = load_ultrarag_modules()
            
            result = PipelineCall(
                pipeline_file=pipeline_file,
                parameter_file=parameter_file
            )
            
            return {
                **state,
                "status": "success",
                "results": result,
                "error": None
            }
        
    except Exception as e:
        return {
            **state,
            "status": "error",
            "results": None,
            "error": str(e)
        }


def retriever_search_node(state: UltraRAGState) -> UltraRAGState:
    """
    LangGraph 节点: 检索器搜索
    
    输入状态:
        - query: 查询字符串
        - top_k: 返回结果数量
    
    输出状态:
        - status: 状态
        - results: 检索结果
        - error: 错误信息
    """
    try:
        _, ToolCall = load_ultrarag_modules()
        
        query = state.get("query")
        top_k = state.get("top_k", 5)
        
        if not query:
            raise ValueError("query is required for retriever search")
        
        result = ToolCall.retriever.retriever_search(
            query_list=[query],
            top_k=top_k
        )
        
        return {
            **state,
            "status": "success",
            "results": result,
            "error": None
        }
        
    except Exception as e:
        return {
            **state,
            "status": "error",
            "results": None,
            "error": str(e)
        }


def create_index_workflow():
    """创建索引构建工作流"""
    workflow = StateGraph(UltraRAGState)
    
    workflow.add_node("build_index", corpus_index_node)
    
    workflow.set_entry_point("build_index")
    workflow.add_edge("build_index", END)
    
    return workflow


def create_rag_workflow():
    """创建 RAG 查询工作流"""
    workflow = StateGraph(UltraRAGState)
    
    workflow.add_node("rag_query", rag_query_node)
    
    workflow.set_entry_point("rag_query")
    workflow.add_edge("rag_query", END)
    
    return workflow


def create_full_rag_workflow():
    """创建完整的 RAG 工作流 (检索 + 生成)"""
    workflow = StateGraph(UltraRAGState)
    
    workflow.add_node("build_index", corpus_index_node)
    workflow.add_node("rag_query", rag_query_node)
    
    workflow.set_entry_point("build_index")
    workflow.add_edge("build_index", "rag_query")
    workflow.add_edge("rag_query", END)
    
    return workflow


def create_conditional_rag_workflow():
    """创建带条件的 RAG 工作流 (检查索引是否存在)"""
    workflow = StateGraph(UltraRAGState)
    
    workflow.add_node("build_index", corpus_index_node)
    workflow.add_node("rag_query", rag_query_node)
    
    workflow.set_entry_point("check_index")
    
    workflow.add_conditional_edges(
        "check_index",
        should_continue_build_index,
        {
            "build_index": "build_index",
            "skip_build": "rag_query"
        }
    )
    
    workflow.add_edge("build_index", "rag_query")
    workflow.add_edge("rag_query", END)
    
    return workflow


def should_continue_build_index(state: UltraRAGState) -> str:
    """条件边: 检查索引是否需要重建"""
    index_path = state.get("index_path")
    if index_path and Path(index_path).exists():
        return "skip_build"
    return "build_index"


def check_index_exists(state: UltraRAGState) -> UltraRAGState:
    """检查索引是否存在"""
    index_path = state.get("index_path")
    if index_path and Path(index_path).exists():
        return {**state, "index_exists": True}
    return {**state, "index_exists": False}


def create_conditional_rag_workflow_v2():
    """创建带条件的 RAG 工作流 v2"""
    workflow = StateGraph(UltraRAGState)
    
    workflow.add_node("check_index", check_index_exists)
    workflow.add_node("build_index", corpus_index_node)
    workflow.add_node("rag_query", rag_query_node)
    
    workflow.set_entry_point("check_index")
    
    def route_based_on_index(state: UltraRAGState) -> str:
        if state.get("index_exists", False):
            return "skip_build"
        return "build_index"
    
    workflow.add_conditional_edges(
        "check_index",
        route_based_on_index,
        {
            "build_index": "build_index",
            "skip_build": "rag_query"
        }
    )
    
    workflow.add_edge("build_index", "rag_query")
    workflow.add_edge("rag_query", END)
    
    return workflow


def health_check() -> bool:
    """检查 UltraRAG API 服务是否健康"""
    try:
        url = f"{ultrarag_config.api_base_url}/health"
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    print("UltraRAG LangGraph Nodes")
    print("=" * 50)
    print("\n配置 API 客户端:")
    print('  set_ultrarag_config("http://localhost:8000")')
    print("\n检查服务健康:")
    print("  health_check()")
    print("\nAvailable nodes:")
    print("  - corpus_index_node: 构建语料库索引")
    print("  - rag_query_node: RAG 查询")
    print("  - retriever_search_node: 检索器搜索")
    
    print("\nAvailable workflows:")
    print("  - create_index_workflow(): 创建索引构建工作流")
    print("  - create_rag_workflow(): 创建 RAG 查询工作流")
    print("  - create_full_rag_workflow(): 创建完整 RAG 工作流")
    print("  - create_conditional_rag_workflow(): 创建带条件的 RAG 工作流")
    
    print("\n" + "=" * 50)
    print("Usage example (API mode):")
    print("""
from langgraph_nodes import (
    set_ultrarag_config,
    create_full_rag_workflow,
    UltraRAGState,
    health_check
)

# 配置 API 地址
set_ultrarag_config("http://localhost:8000")

# 检查服务健康
if health_check():
    print("UltraRAG API 服务正常")
    
    workflow = create_full_rag_workflow()
    app = workflow.compile()
    
    initial_state = {
        "query": "什么是 UltraRAG?",
        "corpus_path": "data/sherpa_text.jsonl",
        "pipeline_file": "examples/corpus_index.yaml",
        "parameter_file": "examples/parameter/corpus_index_parameter.yaml",
        "results": None,
        "status": "pending",
        "error": None
    }
    
    result = app.invoke(initial_state)
    print(result)
else:
    print("UltraRAG API 服务未启动")
""")
