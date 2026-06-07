# ScriptYAML Schema

ScriptYAML 是小说转剧本流程的结构化输出格式，用于在生成、校验、编辑和导出阶段保持数据一致。根对象包含五个必填字段：

```text
project
characters
locations
scenes
script
```

## 字段设计

### project

项目元信息。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 项目或剧本标题 |
| `version` | string | 否 | Schema 或输出版本，默认 `1.0` |
| `genre` | string | 否 | 类型，如悬疑、短剧、电影 |
| `logline` | string | 否 | 一句话故事简介 |
| `source` | string | 否 | 来源小说、文件名或章节范围 |

### characters

人物列表。每个人物必须有唯一 `id`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 人物稳定 ID，格式为字母开头，可包含数字、`_`、`-` |
| `name` | string | 是 | 人物显示名称 |
| `role` | string | 否 | 叙事功能或角色定位 |
| `description` | string | 否 | 人物设定补充 |

### locations

场景地点列表。每个地点必须有唯一 `id`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 地点稳定 ID |
| `name` | string | 是 | 地点显示名称 |
| `description` | string | 否 | 地点视觉或叙事说明 |

### scenes

场景元信息列表。场景描述地点、登场人物和剧情摘要。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 场景稳定 ID |
| `title` | string | 是 | 场景标题 |
| `location_id` | string | 是 | 引用 `locations[].id` |
| `characters` | string[] | 否 | 引用 `characters[].id` |
| `summary` | string | 否 | 场景剧情摘要 |

### script

剧本文本行列表。每一行必须引用一个已定义场景。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `scene_id` | string | 是 | 引用 `scenes[].id` |
| `type` | enum | 是 | `action`、`dialogue`、`transition`、`note` |
| `content` | string | 是 | 动作、对白、转场或注释内容 |
| `character_id` | string | 对白必填 | 当 `type=dialogue` 时引用 `characters[].id` |

## 完整性校验

`backend/schemas/script_yaml.py` 中的 Pydantic 模型会校验：

- `characters`、`locations`、`scenes` 内部 ID 不重复
- 每个 `scene.location_id` 必须存在于 `locations`
- 每个 `scene.characters[]` 必须存在于 `characters`
- 每个 `script[].scene_id` 必须存在于 `scenes`
- 每个 `script[].character_id` 必须存在于 `characters`
- 对白行必须提供 `character_id`
- 对白行角色必须列在对应场景的 `characters` 中
- 每个场景至少有一条 `script` 内容

## 示例 YAML

```yaml
project:
  title: 雨夜来信
  version: "1.0"
  genre: 悬疑短剧
  logline: 旧影院重逢的一夜，让两个人重新面对十年前错过的答案。
  source: sample_novel_3chapters.txt
characters:
  - id: lin_che
    name: 林澈
    role: 男主角
    description: 带着旧信来到影院门口的人。
  - id: shen_wei
    name: 沈微
    role: 女主角
    description: 等待多年并递出旧电影票的人。
locations:
  - id: old_cinema
    name: 旧影院门口
    description: 雨停后的长街尽头，灯箱仍然亮着。
scenes:
  - id: scene_1
    title: 雨夜重逢
    location_id: old_cinema
    characters:
      - lin_che
      - shen_wei
    summary: 林澈在旧影院门口见到沈微，并收到十年前的电影票。
script:
  - scene_id: scene_1
    type: action
    content: 雨停后的长街泛着冷光。林澈握着没有署名的信，停在旧影院门口。
  - scene_id: scene_1
    type: dialogue
    content: 如果今晚不进去，我们会再错过一次。
    character_id: shen_wei
  - scene_id: scene_1
    type: transition
    content: 镜头推向亮起的银幕。
```
