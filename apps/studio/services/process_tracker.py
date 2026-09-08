import time
import logging
import threading

logger = logging.getLogger(__name__)

class RenderProcessTracker:
    """
    Thread-safe tracker for managing active FFmpeg subprocesses,
    storing live progress states, and handling instant cancellation across all Studio rendering tasks.
    """
    _lock = threading.Lock()
    _active_processes = {}      # (project_type, pk) -> set of subprocess.Popen
    _cancelled_projects = set()  # (project_type, pk)
    _progress_data = {}         # (project_type, pk) -> {'pct': int, 'step': str, 'started_at': float}

    @classmethod
    def _make_key(cls, project_type, pk):
        return (str(project_type).lower().strip(), int(pk))

    @classmethod
    def register(cls, project_type, pk, proc):
        """Register an active subprocess Popen instance."""
        with cls._lock:
            key = cls._make_key(project_type, pk)
            if key not in cls._active_processes:
                cls._active_processes[key] = set()
            cls._active_processes[key].add(proc)
            logger.info(f"[RenderProcessTracker] Registered active process for {key}")

    @classmethod
    def unregister(cls, project_type, pk, proc=None):
        """Unregister a completed or terminated process."""
        with cls._lock:
            key = cls._make_key(project_type, pk)
            if key in cls._active_processes:
                if proc:
                    cls._active_processes[key].discard(proc)
                    if not cls._active_processes[key]:
                        cls._active_processes.pop(key, None)
                else:
                    cls._active_processes.pop(key, None)

    @classmethod
    def cancel(cls, project_type, pk):
        """
        Flag project as cancelled and immediately terminate active subprocess if running.
        """
        with cls._lock:
            key = cls._make_key(project_type, pk)
            cls._cancelled_projects.add(key)
            procs = cls._active_processes.pop(key, set())
            if isinstance(procs, (set, list)):
                for proc in list(procs):
                    try:
                        logger.info(f"[RenderProcessTracker] Terminating active process for {key}")
                        proc.kill()
                    except Exception as e:
                        logger.warning(f"[RenderProcessTracker] Error terminating process for {key}: {e}")
            elif procs:
                try:
                    logger.info(f"[RenderProcessTracker] Terminating active process for {key}")
                    procs.kill()
                except Exception as e:
                    logger.warning(f"[RenderProcessTracker] Error terminating process for {key}: {e}")
            
            # Update progress status
            if key in cls._progress_data:
                cls._progress_data[key]['step'] = 'Rendering cancelled by user.'

    @classmethod
    def is_cancelled(cls, project_type, pk):
        """Check whether a project has been cancelled."""
        with cls._lock:
            key = cls._make_key(project_type, pk)
            return key in cls._cancelled_projects

    @classmethod
    def clear_cancelled(cls, project_type, pk):
        """Clear cancellation state for a new render run."""
        with cls._lock:
            key = cls._make_key(project_type, pk)
            cls._cancelled_projects.discard(key)

    @classmethod
    def set_progress(cls, project_type, pk, pct, step, started_at=None):
        """
        Update the current percentage (0-100) and step description for a rendering job.
        """
        with cls._lock:
            key = cls._make_key(project_type, pk)
            current = cls._progress_data.get(key, {})
            start_time = started_at or current.get('started_at', time.time())
            cls._progress_data[key] = {
                'pct': max(0, min(100, int(pct))),
                'step': str(step),
                'started_at': start_time,
                'updated_at': time.time()
            }

    @classmethod
    def get_progress(cls, project_type, pk):
        """
        Retrieve current progress data for a rendering project.
        """
        with cls._lock:
            key = cls._make_key(project_type, pk)
            return cls._progress_data.get(key, {
                'pct': 0,
                'step': 'Preparing render pipeline...',
                'started_at': time.time(),
                'updated_at': time.time()
            })

    @classmethod
    def cleanup(cls, project_type, pk):
        """Full cleanup of state for a project upon completion or cancellation."""
        with cls._lock:
            key = cls._make_key(project_type, pk)
            cls._active_processes.pop(key, None)
            cls._progress_data.pop(key, None)
            cls._cancelled_projects.discard(key)
