import os
import json
from typing import List, Dict, Any
import logging

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# =============================
# 日志配置
# =============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# =============================
# 环境变量与配置解析
# =============================
SUPABASE_CONFIG_RAW = os.getenv("SUPABASE_CONFIG", "[]")

config_list: List[Dict[str, Any]] = []
startup_error: str | None = None

try:
    # 解析 JSON 数组
    config_list = json.loads(SUPABASE_CONFIG_RAW)
    if not isinstance(config_list, list):
        raise ValueError("SUPABASE_CONFIG 必须是 JSON 数组格式")
    if len(config_list) == 0:
        raise ValueError("SUPABASE_CONFIG 不能为空数组")

    # 校验每一项的必要字段
    required_fields = {"name", "supabase_url", "supabase_key", "table_name"}
    for idx, conf in enumerate(config_list):
        missing = required_fields - conf.keys()
        if missing:
            raise ValueError(
                f"配置 index={idx} 缺少字段: {', '.join(missing)}"
            )
    
    # 记录成功加载的配置数量（不记录敏感信息）
    logger.info(f"成功加载 {len(config_list)} 个Supabase配置")
    
except Exception as e:
    startup_error = str(e)
    logger.error(f"启动配置加载失败: {startup_error}")
    print(f"Startup Error: {startup_error}")

# =============================
# 工具函数
# =============================
def _perform_ping(conf: Dict[str, Any]):
    """对指定配置执行 keep‑alive 查询，返回 (success: bool, msg: str)"""
    try:
        # 记录尝试连接的数据库名称（不记录密钥等敏感信息）
        logger.info(f"正在尝试连接数据库: {conf['name']}")
        
        supa: Client = create_client(conf["supabase_url"], conf["supabase_key"])
        # 只做一次轻量查询
        supa.table(conf["table_name"]).select("*").limit(1).execute()
        
        logger.info(f"成功连接数据库: {conf['name']}")
        return True, "ok"
    except Exception as e:
        logger.error(f"连接数据库 {conf['name']} 失败: {str(e)}")
        return False, str(e)


def _get_conf_by_index(idx: int):
    if idx < 0 or idx >= len(config_list):
        logger.warning(f"请求了不存在的配置索引: {idx}")
        raise HTTPException(status_code=404, detail=f"index {idx} 不存在")
    return config_list[idx]


def _get_conf_by_name(name: str):
    for conf in config_list:
        if conf["name"] == name:
            return conf
    logger.warning(f"请求了不存在的配置名称: {name}")
    raise HTTPException(status_code=404, detail=f"name '{name}' 未找到对应配置")


# =============================
# 路由
# =============================


@app.get("/api/keepalive")
@app.get("/api/keepalive/all")
async def keepalive_all(request: Request):
    """遍历所有配置并执行 keep‑alive"""
    logger.info("收到对 /api/keepalive/all 的请求")
    
    if startup_error:
        logger.error("由于启动错误，无法处理请求")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Startup failed: {startup_error}"})

    success_count = 0
    failure_count = 0
    
    for idx, conf in enumerate(config_list):
        success, msg = _perform_ping(conf)
        if success:
            success_count += 1
        else:
            failure_count += 1

    if success_count == len(config_list):
        logger.info(f"所有 {len(config_list)} 个数据库连接成功")
        return JSONResponse(status_code=200, content={"status": "success", "message": "ok"})
    elif success_count > 0:
        logger.warning(f"{success_count} 个数据库连接成功，{failure_count} 个失败")
        return JSONResponse(status_code=500, content={"status": "error", "message": "partial_failure"})
    else:
        logger.error(f"所有 {len(config_list)} 个数据库连接失败")
        return JSONResponse(status_code=500, content={"status": "error", "message": "all_failure"})

@app.get("/api/keepalive/index")
@app.get("/api/keepalive/index/{idx}")
async def keepalive_by_index(request: Request, idx: int = 0):
    logger.info(f"收到对 /api/keepalive/index/{idx} 的请求")
    
    if startup_error:
        logger.error("由于启动错误，无法处理请求")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Startup failed: {startup_error}"})

    conf = _get_conf_by_index(idx)
    success, msg = _perform_ping(conf)
    status_code = 200 if success else 500
    
    if success:
        logger.info(f"索引 {idx} 的数据库连接成功")
    else:
        logger.error(f"索引 {idx} 的数据库连接失败: {msg}")
        
    return JSONResponse(status_code=status_code, content={"status": "success" if success else "error", "message": msg})


@app.get("/api/keepalive/name/{conf_name}")
async def keepalive_by_name(request: Request, conf_name: str):
    logger.info(f"收到对 /api/keepalive/name/{conf_name} 的请求")
    
    if startup_error:
        logger.error("由于启动错误，无法处理请求")
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Startup failed: {startup_error}"})

    conf = _get_conf_by_name(conf_name)
    success, msg = _perform_ping(conf)
    status_code = 200 if success else 500
    
    if success:
        logger.info(f"名称 '{conf_name}' 的数据库连接成功")
    else:
        logger.error(f"名称 '{conf_name}' 的数据库连接失败: {msg}")
        
    return JSONResponse(status_code=status_code, content={"status": "success" if success else "error", "message": msg})