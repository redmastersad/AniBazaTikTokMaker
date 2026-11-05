"""Windows: run every child process (ffmpeg, ffprobe, nvidia-smi...) without a console window.

The app runs under pythonw.exe, so each console program it starts would otherwise pop up its own
black window for a moment. Import this module before anything that spawns processes.
"""
import os
import subprocess

if os.name == "nt" and not getattr(subprocess.Popen, "_anibaza_hidden", False):
    _Popen = subprocess.Popen

    class _HiddenPopen(_Popen):
        _anibaza_hidden = True

        def __init__(self, *args, **kwargs):
            if not kwargs.get("creationflags"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    subprocess.Popen = _HiddenPopen
