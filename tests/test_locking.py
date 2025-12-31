
import threading
import multiprocessing
import time
import os
import pytest
from pyclog.locking import FileLock

def test_lock_acquire_release(tmp_path):
    """测试基本的获取和释放锁"""
    lock_file = tmp_path / "test.lock"
    lock = FileLock(str(lock_file))
    
    with lock:
        assert os.path.exists(lock_file)
        # Hold lock
        pass
    
    # Lock should be released (file remains, but handle closed)
    # We can check if we can acquire it again
    with lock:
        pass

def holder_process(lock_path, hold_time, ready_event):
    """持有锁一段时间的进程"""
    with FileLock(lock_path):
        ready_event.set()
        time.sleep(hold_time)

def test_lock_contention(tmp_path):
    """测试锁争用"""
    lock_file = str(tmp_path / "contention.lock")
    
    # 使用 multiprocessing 来测试跨进程锁
    # 注意：在 Windows 上，spawn 是默认的启动方法，所以参数需要可序列化
    ready = multiprocessing.Event()
    p = multiprocessing.Process(target=holder_process, args=(lock_file, 2, ready))
    p.start()
    
    # 等待子进程获取锁
    if not ready.wait(timeout=5):
        p.terminate()
        pytest.fail("子进程未能获取锁")

    try:
        # 尝试在主进程获取锁，应该会阻塞等待直到子进程释放
        start_t = time.time()
        with FileLock(lock_file, timeout=5):
            end_t = time.time()
            # 应该至少等待了不久（子进程持有2秒，也就是稍微小于2秒因为ready event是在acquire后设置的）
            # 但考虑到系统调度，这里只断言没超时且确实获取到了
            pass
        
        # 确保确实发生了等待
        assert end_t - start_t > 0.5 
        
    finally:
        p.join()

def test_lock_timeout(tmp_path):
    """测试获取锁超时"""
    lock_file = str(tmp_path / "timeout.lock")
    
    ready = multiprocessing.Event()
    # 子进程持有锁 5 秒
    p = multiprocessing.Process(target=holder_process, args=(lock_file, 5, ready))
    p.start()
    
    if not ready.wait(timeout=5):
        p.terminate()
        pytest.fail("子进程未能获取锁")
        
    try:
        # 主进程只等待 1 秒，应该由 TimeoutError
        with pytest.raises(TimeoutError):
            with FileLock(lock_file, timeout=1):
                pass
    finally:
        p.terminate()
        p.join()
