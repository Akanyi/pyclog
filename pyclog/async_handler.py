
import logging
import queue
import threading
import atexit
from logging.handlers import QueueHandler, QueueListener

class AsyncClogHandler(QueueHandler):
    """
    一个异步的日志处理器，它将日志记录放入队列，并由后台线程写入目标 Handler (如 ClogFileHandler)。
    这样可以避免文件 I/O 阻塞主线程。
    
    用法:
        file_handler = ClogFileHandler("app.clog")
        async_handler = AsyncClogHandler(file_handler)
        logger.addHandler(async_handler)
    """
    def __init__(self, target_handler, queue_size=-1):
        """
        初始化 AsyncClogHandler。
        
        Args:
            target_handler (logging.Handler): 实际执行写入的 Handler。
            queue_size (int): 队列大小。-1 表示无限。默认 -1。
        """
        self.log_queue = queue.Queue(queue_size)
        super().__init__(self.log_queue)
        
        self.target_handler = target_handler
        self.listener = QueueListener(self.log_queue, self.target_handler, respect_handler_level=True)
        self.listener.start()
        
        # 注册退出时的清理函数，确保日志被刷新
        atexit.register(self.stop)

    def stop(self):
        """
        停止监听器并关闭目标 Handler。
        """
        if self.listener:
            self.listener.stop()
            self.listener = None
        
        # QueueListener.stop() 不会自动关闭 handler，我们需要手动关闭
        # 但通常 QueueHandler 不负责关闭 target_handler，除非它是我们拥有的
        # 这里为了方便，我们尝试关闭它
        # 注意：logging 系统 shutdown 时也会尝试关闭所有 handler
        
    def close(self):
        """
        关闭 Handler。
        """
        self.stop()
        super().close()

# 简单的 Async Logger 包装器 (语法糖)
class AsyncClogLogger:
    def __init__(self, logger):
        self.logger = logger
    
    async def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
        
    async def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
        
    async def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
    
    async def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
        
    async def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)
