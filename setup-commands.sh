#!/bin/bash
# ============================================================
# opencap-api 本地开发环境搭建命令
# 使用方法: bash ~/open-campus-demo-v3/setup-commands.sh
# ============================================================

echo "===== 第一步：安装 PostgreSQL ====="
sudo apt update
sudo apt install -y postgresql postgresql-contrib

echo ""
echo "===== 第二步：启动 PostgreSQL ====="
sudo systemctl start postgresql
sudo systemctl status postgresql --no-pager

echo ""
echo "===== 第三步：创建数据库和用户 ====="
sudo -u postgres psql <<SQL
CREATE USER opencap WITH PASSWORD 'opencap';
CREATE DATABASE opencap OWNER opencap;
GRANT ALL PRIVILEGES ON DATABASE opencap TO opencap;
ALTER USER opencap CREATEDB;
\q
SQL

echo ""
echo "===== 第四步：验证数据库连接 ====="
sudo -u postgres psql -c "\du" | grep opencap
sudo -u postgres psql -c "\l" | grep opencap

echo ""
echo "===== 第五步：激活 conda 环境并进入项目 ====="
source ~/anaconda3/etc/profile.d/conda.sh
conda activate opencap
cd ~/open-campus-demo-v3/opencap-api

echo ""
echo "===== 第六步：Django 检查 ====="
python manage.py check

echo ""
echo "===== 第七步：数据库迁移 ====="
python manage.py migrate

echo ""
echo "===== 第八步：启动开发服务器 ====="
echo "启动后访问 http://127.0.0.1:8000/"
echo "按 Ctrl+C 停止服务器"
echo ""
python manage.py runserver 0.0.0.0:8000 &
SERVER_PID=$!
sleep 2

echo ""
echo "===== 第九步：检查防火墙并放行端口 8000 ====="
sudo ufw status verbose
echo ""
echo "如果 ufw 是 active 且没有 8000 规则，执行："
echo "  sudo ufw allow 8000/tcp"
echo ""

echo "===== 测试连接 ====="
echo "本地测试："
curl -s -o /dev/null -w "  localhost:8000 -> HTTP %{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "  $HOSTNAME:8000 -> HTTP %{http_code}\n" http://100.111.140.103:8000/

echo ""
echo "===== Mac 访问地址 ====="
echo "在 Mac 浏览器打开: http://100.111.140.103:8000/admin/"
echo ""
echo "如果 Mac 无法访问，在终端执行放行防火墙："
echo "  sudo ufw allow 8000/tcp"
echo ""
echo "服务器 PID: $SERVER_PID"
echo "停止服务器: kill $SERVER_PID"
wait $SERVER_PID
