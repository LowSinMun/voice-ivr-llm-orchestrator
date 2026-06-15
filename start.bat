@echo off
title ABC 虚拟服务器一键启动器
color 0A

echo ===================================================
echo 1. 正在检查并自动安装缺失的 Python 依赖包...
echo ===================================================
pip install fastapi uvicorn pandas pydantic pyngrok

echo.
echo ===================================================
echo 2. 依赖包检查完毕，正在启动核心服务器与穿透服务...
echo ===================================================
python main.py

pause