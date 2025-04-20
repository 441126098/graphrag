# GraphRag

这是一个使用 Poetry 管理的 Python 项目。

## 安装

```bash
# 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

## 开发

```bash
# 运行测试
poetry run pytest
```

## GraphRAG项目

本项目是基于GraphRAG的应用实现。

### 环境设置

本项目使用uv进行包管理。

#### 使用uv管理依赖

```bash
# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv pip install -e .

# 安装开发依赖
uv pip install -e ".[dev]"

# 添加新依赖
uv pip install package_name

# 导出依赖到requirements.txt
uv pip freeze > requirements.txt

# 从requirements.txt安装依赖
uv pip install -r requirements.txt
```

#### 退出虚拟环境

```bash
deactivate
```

### 运行项目

```bash
# 启动应用
python -m graphrag.app
``` 