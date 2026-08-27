#!/bin/bash

# ScholarLens - 启动所有服务脚本
# 包含: PDF提取、文本切分、向量数据库、对话检索

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 创建必要的目录
mkdir -p logs
mkdir -p pids

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 启动 ScholarLens 所有服务${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 检查并激活Conda虚拟环境
if [ -f "/root/anaconda3/envs/vlm_rag/bin/python" ]; then
    PYTHON_CMD="/root/anaconda3/envs/vlm_rag/bin/python"
    echo -e "${GREEN}✓ 使用Conda虚拟环境: vlm_rag${NC}"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo -e "${YELLOW}⚠️  使用系统Python (可能缺少依赖)${NC}"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    echo -e "${YELLOW}⚠️  使用系统Python (可能缺少依赖)${NC}"
else
    echo -e "${RED}❌ 错误: 未找到Python${NC}"
    exit 1
fi

echo -e "${YELLOW}Python路径: $PYTHON_CMD${NC}\n"

# 函数: 启动服务
start_service() {
    local service_name=$1
    local service_path=$2
    local service_file=$3
    local port=$4
    local pid_file="pids/${service_name}.pid"
    local log_file="logs/${service_name}.log"

    echo -e "${YELLOW}启动 ${service_name} (端口 ${port})...${NC}"

    # 检查服务文件是否存在
    if [ ! -f "${service_path}/${service_file}" ]; then
        echo -e "${RED}  ❌ 错误: 文件不存在 ${service_path}/${service_file}${NC}"
        return 1
    fi

    # 检查端口是否被占用
    if lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${YELLOW}  ⚠️  端口 ${port} 已被占用，正在清理...${NC}"

        # 获取占用端口的进程PID
        local occupied_pid=$(lsof -Pi :${port} -sTCP:LISTEN -t)

        if [ -n "$occupied_pid" ]; then
            echo -e "${YELLOW}  正在停止占用端口的进程 (PID: $occupied_pid)...${NC}"

            # 尝试优雅停止
            kill $occupied_pid 2>/dev/null || true

            # 等待进程结束
            local count=0
            while ps -p $occupied_pid > /dev/null 2>&1 && [ $count -lt 5 ]; do
                sleep 1
                count=$((count + 1))
            done

            # 如果还没结束，强制杀死
            if ps -p $occupied_pid > /dev/null 2>&1; then
                echo -e "${YELLOW}  强制停止进程...${NC}"
                kill -9 $occupied_pid 2>/dev/null || true
                sleep 1
            fi

            echo -e "${GREEN}  ✓ 端口 ${port} 已清理${NC}"
        fi
    fi

    # 启动服务
    cd "${service_path}"
    nohup $PYTHON_CMD "${service_file}" > "${SCRIPT_DIR}/${log_file}" 2>&1 &
    local pid=$!

    # 保存PID
    echo $pid > "${SCRIPT_DIR}/${pid_file}"

    # 等待服务启动
    sleep 2

    # 检查进程是否还在运行
    if ps -p $pid > /dev/null; then
        echo -e "${GREEN}  ✓ ${service_name} 启动成功 (PID: $pid)${NC}"
        echo -e "${BLUE}    日志: logs/${service_name}.log${NC}"
        echo -e "${BLUE}    访问: http://localhost:${port}${NC}"
    else
        echo -e "${RED}  ❌ ${service_name} 启动失败，请查看日志: logs/${service_name}.log${NC}"
        rm -f "${SCRIPT_DIR}/${pid_file}"
        return 1
    fi

    cd "${SCRIPT_DIR}"
    echo ""
}

# 1. 启动PDF提取服务
start_service "pdf_extraction" \
    "Information-Extraction/unified" \
    "unified_pdf_extraction_service.py" \
    "8006"

# 2. 启动文本切分服务
start_service "chunker" \
    "Text_segmentation" \
    "markdown_chunker_api.py" \
    "8001"

# 3. 启动向量数据库服务
start_service "milvus_api" \
    "Database/milvus_server" \
    "milvus_api.py" \
    "8000"

# 4. 启动对话检索服务
start_service "chat" \
    "chat" \
    "kb_chat.py" \
    "8501"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ 所有服务启动完成！${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${YELLOW}服务列表:${NC}"
echo -e "  📄 PDF提取服务:     http://localhost:8006"
echo -e "  ✂️  文本切分服务:     http://localhost:8001"
echo -e "  🗄️  向量数据库服务:   http://localhost:8000"
echo -e "  💬 对话检索服务:     http://localhost:8501"

echo -e "\n${YELLOW}常用命令:${NC}"
echo -e "  查看服务状态: ${GREEN}./status_services.sh${NC}"
echo -e "  查看所有日志: ${GREEN}tail -f logs/*.log${NC}"
echo -e "  查看单个日志: ${GREEN}tail -f logs/chat.log${NC}"
echo -e "  停止所有服务: ${GREEN}./stop_all_services.sh${NC}"

echo -e "\n${BLUE}========================================${NC}\n"
