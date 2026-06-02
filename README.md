# data-structure-agent-mvp

本科数据结构知识 Agent MVP。当前只覆盖第 2 章“线性表”相关内容，使用本地 Markdown 知识库 + DeepSeek API + Streamlit 页面。

这个版本适合课堂展示和小组内试用。

## 现在能做什么

- 像聊天一样提问线性表问题
- 从 `knowledge/` 目录检索本地教材笔记
- 基于检索到的内容调用 DeepSeek 回答
- 维护简短上下文摘要，支持简单追问
- 右侧显示交互演示板，可以点“上一步 / 下一步”
- 普通问题默认隐藏 C 代码
- 明确要求代码时，会保存为 `temp.c`，并尝试用 `gcc` 编译运行

## 当前支持的演示

- 顺序表插入
- 顺序表删除
- 单链表插入
- 单链表删除
- 单链表查找
- 单链表长度统计
- 头插法
- 尾插法
- 链表逆置
- 循环链表遍历

排序、栈、队列、树、图等内容暂不支持演示。

## 项目结构

```text
data-structure-agent-mvp/
├─ app.py                    # Streamlit 页面和主流程
├─ llm.py                    # DeepSeek API 调用
├─ rag.py                    # Markdown 关键词检索
├─ code_checker.py           # C 代码提取、保存、编译运行
├─ operation_visualizer.py   # 右侧交互演示板和本地模拟器
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

1. 把用户问题和简短上下文摘要合成检索 query
2. 在 `knowledge/*.md` 中按关键词匹配
3. 取最相关的 3 个片段
4. 把这些片段和用户问题一起发给 DeepSeek

所以回答会尽量贴近本地教材笔记。后续要提高准确度，优先补充 `knowledge/`。

## 演示板怎么工作

演示板不是直接运行任意 C 代码。

当前流程是：

```text
用户问题
-> DeepSeek 输出结构化特征 JSON
-> Python 判断是否支持该操作
-> 调用本地模拟器生成步骤
-> Streamlit 渲染演示板
```

这样比让 AI 临时编动画更稳定。

如果问题超出当前支持范围，例如排序，演示板会提示暂不支持。

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
