"""
使用 UltraRAG 构建向量库的示例脚本
"""
import asyncio
from ultrarag import PipelineCall

pipeline_file = "my_vector_db.yaml"
parameter_file = "parameter/my_vector_db_parameter.yaml"

result = PipelineCall(pipeline_file, parameter_file)
print(result)
