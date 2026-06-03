# data-structure-agent-mvp

本科数据结构知识 Agent MVP。当前只覆盖第 2 章“线性表”相关内容，使用本地 Markdown 知识库 + DeepSeek API + Streamlit 页面。

这个版本适合课堂展示和小组内试用。

## 现在能做什么

- 像聊天一样提问线性表问题
- 从 `knowledge/` 目录检索本地教材笔记
- 基于检索到的内容调用 DeepSeek 回答
- 演示类问题会输出较完整的教学讲解，包括过程、原因、结果和易错点
- 发送完整历史对话，支持连续追问
- 右侧显示从对话中自动提取的交互演示板，可以点“上一步 / 下一步”
- 普通问题默认隐藏 C 代码
- 明确要求代码时，会保存为 `temp.c`，并尝试用 `gcc` 编译运行

## 当前支持的演示

- 顺序表插入
- 顺序表删除
- 顺序表查找
- 单链表插入
- 单链表删除
- 单链表查找
- 单链表头插法 / 尾插法建表
- 栈 push / pop
- 队列 enqueue / dequeue

树、图、排序等内容暂不在第一阶段实现。

## 项目结构

```text
data-structure-agent-mvp/
├─ app.py                    # Streamlit 页面和主流程
├─ llm.py                    # DeepSeek API 调用
├─ rag.py                    # Markdown 关键词检索
├─ code_checker.py           # C 代码提取、保存、编译运行
├─ operation_visualizer.py   # 旧版演示兼容文件
├─ visualizer/
│  ├─ protocol.py            # DSVP 协议和 Pydantic 校验
│  ├─ intent_parser.py       # 自然语言 -> OperationRequest
│  ├─ dispatcher.py          # structure + operation 分发
│  ├─ simulators/            # 纯本地模拟器
│  ├─ renderers/             # HTML / Markdown / Mermaid 渲染
│  └─ tests/                 # pytest 测试
├─ prompts/
│  └─ system_prompt.txt      # 助教回答约束
├─ knowledge/
│  ├─ linear_list.md
│  ├─ sequential_list.md
│  └─ linked_list.md
├─ examples/
│  └─ sample_questions.md
├─ requirements.txt
├─ packages.txt              # Streamlit Cloud 上安装 gcc
├─ .env.example
└─ run_windows.ps1
```

## 安装环境

建议使用 Python 3.10 或更高版本。

进入项目目录：

```powershell
cd data-structure-agent-mvp
```

创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

## 配置 DeepSeek API Key

复制 `.env.example`，新建 `.env`：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

注意：

- `.env` 只放在自己电脑上，不要发给别人
- 交付包里只包含 `.env.example`
- 每个人需要填自己的 DeepSeek API Key

## 启动方式

方式一：直接运行

```powershell
streamlit run app.py
```

方式二：Windows 脚本启动

```powershell
.\run_windows.ps1
```

启动后浏览器打开：

```text
http://localhost:8501
```

## 部署到 Streamlit Cloud

推荐用 GitHub + Streamlit Community Cloud。这样老师和队员不用本地部署，打开网页就能用；你后续修改代码后，只要 push 到 GitHub，线上会自动更新。

### 1. 推送到 GitHub

在项目目录执行：

```powershell
git init
git add .
git commit -m "initial data structure agent mvp"
```

然后在 GitHub 新建仓库，把远程地址换成你自己的：

```powershell
git remote add origin https://github.com/你的用户名/data-structure-agent-mvp.git
git branch -M main
git push -u origin main
```

不要上传 `.env`。它已经在 `.gitignore` 里。

### 2. 创建 Streamlit Cloud 应用

打开：

```text
https://share.streamlit.io
```

选择刚才的 GitHub 仓库。

关键配置：

```text
Main file path: app.py
```

### 3. 配置 Secrets

在 Streamlit Cloud 的 App settings / Secrets 中填写：

```toml
DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
```

不要把 API Key 写进代码或 README。

### 4. 后续如何更新线上版本

本地修改后执行：

```powershell
git add .
git commit -m "update app"
git push
```

Streamlit Cloud 会自动重新部署。老师和队员刷新网页即可看到新版本。

## gcc 说明

如果用户要求生成完整 C 代码，项目会尝试调用 `gcc` 编译运行。

没有安装 `gcc` 时，聊天和演示仍可用，只是 C 代码自动编译检查会跳过。

Windows 可以安装 MinGW-w64，或使用带 gcc 的开发环境。

## knowledge 怎么用

`knowledge/` 是本地知识库。

每次提问后，程序会：

1. 把用户问题和此前完整对话合成检索 query
2. 在 `knowledge/*.md` 中按关键词匹配
3. 取最相关的 3 个片段
4. 把这些片段和用户问题一起发给 DeepSeek

所以回答会尽量贴近本地教材笔记。后续要提高准确度，优先补充 `knowledge/`。

## 演示板怎么工作

演示板不是直接运行任意 C 代码，也不让 DeepSeek 生成步骤或动画。

新的 DSVP（Data Structure Visualization Protocol）流程是：

```text
用户自然语言
-> DeepSeek 判断是否需要演示
-> 若需要演示，左侧回答必须输出完整可运行 C 程序
-> DeepSeek 根据用户问题、助手回答和 C 代码规整为 OperationRequest JSON
-> Pydantic 校验 schema 和必要字段
-> dispatcher 调用本地纯函数模拟器
-> 模拟器输出 VisualizationTrace JSON
-> Streamlit 根据 state.kind 渲染每一步
```

演示是否触发、演示参数是什么，都由 DeepSeek 根据当前问题、完整历史对话、助手刚输出的文字和 C 代码判断；本地不再用关键词或正则去猜演示意图和参数。
演示类回答的 C 代码会被优先作为右侧演示板理解数据、操作和值的依据。
数组移动、链表指针变化、栈顶变化、队头队尾变化仍然由本地可验证代码决定。

### OperationRequest

第一阶段支持：

- `structure`: `sequential_list`, `singly_linked_list`, `stack`, `queue`
- `operation`: `insert`, `delete`, `search`, `build`, `push`, `pop`, `enqueue`, `dequeue`

示例：

```json
{
  "version": "1.0",
  "structure": "singly_linked_list",
  "operation": "insert",
  "params": {
    "mode": "by_position",
    "position": 2,
    "value": 9
  },
  "initial_state": {
    "data": [3, 5, 7],
    "metadata": {
      "index_base": 1,
      "use_head_node": true,
      "capacity": 10
    }
  },
  "options": {
    "language": "c",
    "explain_level": "beginner"
  }
}
```

### VisualizationTrace

模拟器输出统一的 `VisualizationTrace`，每一步包含：

- `state.kind`: `sequence`, `linked`, `stack`, `queue`
- `actions`: `shift`, `link`, `unlink`, `compare`, `push`, `pop`, `enqueue`, `dequeue` 等
- `highlights`: 节点、边、单元格、指针的高亮角色
- `errors` / `warnings`: 统一错误和提示格式

### 对话中触发演示

在普通对话输入框里直接输入：

```text
用 3,5,7 演示单链表在第 2 位插入 9
```

系统会从对话中提取 OperationRequest JSON，并在右侧按教材常见带头结点写法逐步展示：

- 初始链表
- 创建新结点 `s`
- 查找前驱结点 `pre`
- 执行 `s->next = pre->next`
- 执行 `pre->next = s`
- 最终链表

也可以输入：

```text
用顺序表 1,2,3,4 演示在第 3 位插入 8
```

系统会逐步展示顺序表从后向前移动元素，再写入新值。

如果问题超出当前支持范围，例如排序，演示板会提示暂不支持。

## 测试

安装依赖后运行：

```powershell
pytest visualizer/tests -q
```

测试覆盖顺序表插入、删除、查找，单链表插入、删除、查找，栈 push/pop，队列 enqueue/dequeue，以及空表、空栈、空队列、非法位置和查找失败等错误路径。

## 适合展示的问题

可以试：

```text
我想学学头插法
尾插法怎么做
我有链表 10 12 15 39 49，想逆置，演示一下
单链表怎么删除一个结点
顺序表插入为什么要移动元素
循环链表怎么遍历
```

## 常见问题

### 1. 页面提示没有 API Key

检查项目根目录是否有 `.env`，内容是否类似：

```text
DEEPSEEK_API_KEY=sk-xxxx
```

### 2. pip 安装慢

可以换国内源：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 端口被占用

换端口启动：

```powershell
streamlit run app.py --server.port 8502
```

### 4. 代码编译失败

先确认是否安装了 `gcc`：

```powershell
gcc --version
```

没有 gcc 不影响聊天和演示。

## 后续可以做

- 把 `knowledge/` 按教材继续补全
- 把关键词检索升级为 Chroma 向量检索
- 给每类操作补更精确的本地模拟器
- 增加“教师模式 / 学生模式”
- 增加更多章节

## 说明

本项目的知识库是根据教材范围整理的学习摘要，不包含教材原文扫描内容。
