# Scripts

脚本实现只面向新的 contracts 模型：
- `SERVICE.yaml`
- `Controller.spec.yaml`
- `Controller.doc.md`
- `indexes/global.index.json`
- `indexes/services/<service>/...`

## 入口

统一入口：

```bash
python3 scripts/api_contract_cli.py ...
```

支持命令：

```bash
python3 scripts/api_contract_cli.py provider sync ...
python3 scripts/api_contract_cli.py provider delete-controller ...
python3 scripts/api_contract_cli.py consumer search ...
python3 scripts/api_contract_cli.py consumer generate ...
python3 scripts/api_contract_cli.py contracts rebuild-index
```

## 模块分层

### 真源层
- `models.py`
- `service_io.py`
- `spec_io.py`

### 派生与检索层
- `doc_renderer.py`
- `indexer.py`
- `search.py`
- `text_normalizer.py`

### 行为层
- `provider.py`
- `java_feign_generator.py`
- `consumer_local_rules.py`

### 接入层
- `contract_store.py`
- `cli.py`

## 当前实现约束

- 仅支持 Java/OpenFeign
- 不支持 Node/PHP
- 默认通过 Git over SSH 访问，也支持通过 GitLab API + token 访问远端 contracts 仓库
- 不提供 local fallback
- consumer 本地规则只在 consumer 仓库本地读取

## 检索链路

```text
query -> global.index.json -> service shard -> spec
```

约束：
- Top3 service 路由
- Top50 shard 候选
- Top5 spec 回源
- 未收敛直接终止

## provider 产出

`provider sync` 生成并写回：
- `services/<service>/SERVICE.yaml`
- `services/<service>/controllers/<Controller>/<Controller>.spec.yaml`
- `services/<service>/controllers/<Controller>/<Controller>.doc.md`
- `indexes/global.index.json`
- `indexes/services/<service>/manifest.json`
- `indexes/services/<service>/operations.jsonl`
- `indexes/services/<service>/inverted/*.json`

## consumer 生成

`consumer generate` 读取：
- `SERVICE.yaml`
- `Spec`
- consumer 本地规则

并按以下优先级决定落位：
1. consumer 仓库根目录本地 YAML
2. 本地项目结构推断
3. 公司默认规则

## 验证

```bash
python3 -m py_compile scripts/api_contract_cli.py scripts/api_contract/*.py
python3 -m unittest discover -s tests -v
```
