# -*- coding: utf-8 -*-
"""
@desc: Process manager for managing and terminating child processes
"""
import platform
import logging
import atexit
import subprocess
import concurrent.futures

from backend.diagnostics import runtime as diag

class ProcessManager:
    """
    Process manager that tracks child process lifecycles.
    Uses weak references to avoid memory leaks.
    """
    _instance = None
    
    @classmethod
    def instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = ProcessManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the process manager"""
        self.processes = {}
        self.logger = logging.getLogger(__name__)
        self._terminating_all = False
        
        # Register exit handler
        atexit.register(self.terminate_all)
    
    def add_process(self, process, name=None):
        """
        Add a process to the manager
        
        Args:
            process: Process object to add (subprocess.Popen instance)
            name: Process name; if omitted, uses the process ID
        """
        if process is None:
            return
            
        process_id = name or f"Process:{id(process)}"
        self.processes[process_id] = process
        pid = process.pid if hasattr(process, "pid") else "unknown"
        diag.process(f"added  {process_id}  pid={pid}")
        return process_id

    def add_pid(self, pid, name=None):
        process_id = name or f"Pid:{pid}"
        self.processes[process_id] = pid
        diag.process(f"added  {process_id}  pid={pid}")
        return process_id
    
    def remove_process(self, process_id):
        """
        Remove a process from the manager
        
        Args:
            process_id: Process ID or name
        """
        if process_id in self.processes:
            del self.processes[process_id]
            return True
        return False

    def _forget_process(self, process) -> None:
        """Drop registry entries matching this process object or pid."""
        if process is None:
            return
        pid = getattr(process, "pid", None)
        for process_id, tracked in list(self.processes.items()):
            if tracked is process:
                del self.processes[process_id]
            elif pid is not None and (tracked == pid or getattr(tracked, "pid", None) == pid):
                del self.processes[process_id]
    
    def terminate_all(self):
        """Concurrently terminate all managed processes"""
        if not self.processes:
            return
        if self._terminating_all:
            return
        self._terminating_all = True
        try:
            items = list(self.processes.items())
            diag.worker(f"terminate_all  count={len(items)}")
            self.processes.clear()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = []
                for _process_id, process in items:
                    if isinstance(process, int):
                        futures.append(executor.submit(self.terminate_by_pid, process))
                    else:
                        futures.append(
                            executor.submit(self.terminate_by_process, process, True)
                        )
                concurrent.futures.wait(futures)
        finally:
            self._terminating_all = False
    
    def terminate_by_process(self, process, quiet: bool = False):
        if process is None:
            return
        self._forget_process(process)
        try:
            pid = getattr(process, "pid", None)
            alive = True
            if hasattr(process, "poll") and process.poll() is not None:
                alive = False
            elif hasattr(process, "is_alive") and not process.is_alive():
                alive = False
            if not quiet and alive and pid is not None:
                diag.worker(f"stop  pid={pid}")
            if not alive:
                return
                
            # Process is still running
            process.terminate()
            if hasattr(process, 'join'):
                try:
                    process.join(timeout=3)
                except Exception:
                    pass
            if hasattr(process, 'wait'):
                try:
                    process.wait(timeout=3)
                except Exception:
                    pass
            # Process did not exit cleanly; force kill
            if hasattr(process, 'kill'):
                try:
                    process.kill()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.terminate_by_pid(process.pid)
        except Exception:
            pass

    def terminate_by_pid(self, pid):
        try:
            # Force-kill the process via system commands
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], 
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            else:
                subprocess.run(['pkill', '-9', '-P', str(pid)], 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
                subprocess.run(['kill', '-9', str(pid)], 
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        except Exception as e:
            diag.error(f"force-kill failed  pid={pid}  err={e}")
