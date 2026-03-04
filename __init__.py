import threading
import time
import torch
import logging
import json
import urllib.request
import sys
import comfy.model_management

# 設定 logger
logger = logging.getLogger("comfyui-idle-release")
logger.setLevel(logging.INFO)

# 設定檔
CHECK_INTERVAL = 5  # 每 5 秒檢查一次
IDLE_TIMEOUT = 300  # 閒置 5 分鐘 (300 秒)

class VRAMClearer:
    def __init__(self):
        self.idle_time = 0
        self.last_memory_allocated = -1
        self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.thread.start()
        logger.info("[comfyui-idle-release] Plugin loaded. Monitoring GPU VRAM...")

    def monitor_loop(self):
        while True:
            time.sleep(CHECK_INTERVAL)
            
            if not torch.cuda.is_available():
                continue

            try:
                # 檢查 ComfyUI 是否有代辦任務
                if self.check_is_processing():
                    self.idle_time = 0
                    self.last_memory_allocated = torch.cuda.memory_allocated()
                    continue

                # 取得當前已分配的 VRAM
                current_memory = torch.cuda.memory_allocated()
                
                # 判定閒置條件：
                # 1. ComfyUI 沒有在執行任務 (上面已攔截)
                # 2. VRAM 佔用沒有變化，且大於 0（代表有模型載入）
                if current_memory == self.last_memory_allocated and current_memory > 0:
                    self.idle_time += CHECK_INTERVAL
                else:
                    self.idle_time = 0
                    self.last_memory_allocated = current_memory

                # 達到閒置時間上限，清理 VRAM
                if self.idle_time >= IDLE_TIMEOUT:
                    logger.info(f"[comfyui-idle-release] GPU idle for {IDLE_TIMEOUT} seconds. Unloading models and clearing VRAM...")
                    self.clear_vram()
                    self.idle_time = 0  # 重置計時器
                    self.last_memory_allocated = torch.cuda.memory_allocated() # 更新清理後的 VRAM
                    
            except Exception as e:
                logger.error(f"[comfyui-idle-release] Error during monitoring: {e}", exc_info=True)

    def get_api_base_url(self):
        port = 8188  # ComfyUI 預設 port
        host = "127.0.0.1"

        # 嘗試從全域參數解析 --port
        try:
            from comfy.cli_args import args
            if hasattr(args, 'port'):
                port = args.port
        except Exception:
            pass

        # 如果上方方法失敗，備用手動解析 sys.argv
        if port == 8188:
            for i, arg in enumerate(sys.argv):
                if arg == '--port' and i + 1 < len(sys.argv):
                    try:
                        port = int(sys.argv[i+1])
                    except ValueError:
                        pass
                elif arg == '--listen':
                    pass

        return f"http://{host}:{port}"

    def check_is_processing(self):
        # 詢問 ComfyUI 的提示詞佇列狀態，確認是否正在執行任務
        try:
            url = self.get_api_base_url() + "/api/prompt"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                # 如果 queue_remaining > 0 代表還有任務在排隊或執行中
                if result.get('exec_info', {}).get('queue_remaining', 0) > 0:
                    return True
        except Exception as e:
            pass
        return False

    def get_api_url(self):
        return self.get_api_base_url() + "/api/free"

    def clear_vram(self):
        try:
            # 透過 API 呼叫清除 VRAM 以達到完整釋放
            url = self.get_api_url()
            data = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            
            with urllib.request.urlopen(req) as response:
                result = response.read()
                
            logger.info("[comfyui-idle-release] VRAM cleared successfully via API.")
        except Exception as e:
            logger.error(f"[comfyui-idle-release] Failed to clear VRAM via API: {e}", exc_info=True)

# 啟動監控
monitor = VRAMClearer()

# 為了符合 ComfyUI custom node 的規範，必須要有 NODE_CLASS_MAPPINGS，即使我們沒有提供任何 Node
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
