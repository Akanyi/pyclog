import os
import time
import sys

# 根据操作系统导入相应的模块
if os.name == 'nt':
    import msvcrt
else:
    import fcntl

class FileLock:
    """
    一个简单的基于文件的锁，用于多进程同步。
    支持 Windows (msvcrt) 和 Linux/Unix (fcntl)。
    """
    def __init__(self, lock_file, timeout=10, delay=0.05):
        self.lock_file = lock_file
        self.timeout = timeout
        self.delay = delay
        self.fd = None

    def acquire(self):
        """
        尝试获取锁。如果锁被占用，则重试直到超时。
        """
        start_time = time.time()
        while True:
            try:
                # 打开锁文件。如果不存在则创建。
                self.fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT)
                
                if os.name == 'nt':
                    # Windows: 尝试锁定文件的第一个字节。
                    # LK_NBLCK: 非阻塞锁定。如果无法锁定，抛出 IOError。
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    # Unix/Linux: 使用 flock 获取排他锁 (LOCK_EX)
                    # LOCK_NB: 非阻塞模式。如果无法锁定，抛出 IOError/BlockingIOError。
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                # print(f"DEBUG: Lock acquired {os.getpid()}")
                return
            except (OSError, IOError, BlockingIOError):
                # print(f"DEBUG: Lock fail {os.getpid()}")
                # 如果锁定失败或打开失败，清理并重试
                if self.fd is not None:
                    try:
                        os.close(self.fd)
                    except OSError:
                        pass
                    self.fd = None
                
                if time.time() - start_time >= self.timeout:
                    raise TimeoutError(f"Timeout waiting for lock: {self.lock_file}")
                
                time.sleep(self.delay)

    def release(self):
        """
        释放锁并关闭文件。
        """
        if self.fd is not None:
            try:
                if os.name == 'nt':
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            finally:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
