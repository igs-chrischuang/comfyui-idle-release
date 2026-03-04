import threading
import time
import torch
import logging
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
                # 取得當前已分配的 VRAM
                current_memory = torch.cuda.memory_allocated()
                
                # 如果 VRAM 佔用沒有變化，且大於 0（代表有模型載入），則視為閒置
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

    def clear_vram(self):
        try:
            # 卸載所有模型
            comfy.model_management.unload_all_models()
            # 清除 PyTorch 的 VRAM 緩存
            comfy.model_management.soft_empty_cache()
            logger.info("[comfyui-idle-release] VRAM cleared successfully.")
        except Exception as e:
            logger.error(f"[comfyui-idle-release] Failed to clear VRAM: {e}", exc_info=True)

# 啟動監控
monitor = VRAMClearer()

# 為了符合 ComfyUI custom node 的規範，必須要有 NODE_CLASS_MAPPINGS，即使我們沒有提供任何 Node
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
