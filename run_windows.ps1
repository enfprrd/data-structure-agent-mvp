$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Write-Host "未找到 .env 文件。请复制 .env.example 为 .env，并填写 DEEPSEEK_API_KEY。" -ForegroundColor Yellow
}

python -m streamlit run app.py
