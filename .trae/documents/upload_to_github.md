# 将 UltraRAG 项目上传到个人 GitHub 仓库的计划

## 前提条件
- 用户需要在 GitHub 上拥有一个账号
- 用户需要在 GitHub 上创建一个新的空仓库（获取仓库 URL）

## 执行步骤

### 1. 检查 Git 状态
- 确认当前在 main 分支
- 查看未提交的更改

### 2. 决定是否保留现有更改
用户有修改的文件：
- `examples/deploy_corpus_search.yaml`
- `script/deploy_retriever_config.json`
- `script/deploy_retriever_server.py`

用户新增的未跟踪文件：
- `app.py`
- `data/sherpa_question.jsonl`
- `data/sherpa_text.jsonl`
- `examples/server/parameter/`
- `examples/sherpa_index.yaml`
- `examples/sherpa_search.yaml`
- `model/`
- `test.py`

**选项 A**: 将所有更改一起推送（推荐用于保存用户工作）
**选项 B**: 只推送原始项目，不包含用户的修改

### 3. 添加远程仓库（用户自己的仓库）
```bash
git remote add myrepo <用户自己的GitHub仓库URL>
```

### 4. 提交更改（如果选择选项 A）
```bash
# 添加所有更改
git add .
# 或只添加特定文件
git add app.py script/deploy_retriever_server.py

# 提交
git commit -m "添加自定义 app.py 和修复 retriever 服务"

# 推送到用户仓库
git push myrepo main
```

### 5. 推送到新仓库
```bash
git push myrepo main
```

## 注意事项
- `.gitignore` 已经配置，会自动忽略 `__pycache__`、`data/`、`index/` 等目录
- `model/` 目录默认被忽略（包含大型模型文件）
- 如果需要推送 model 目录，需要修改 `.gitignore`
