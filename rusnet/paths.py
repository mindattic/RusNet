"""Resolve well-known user folders RusNet writes into by default.

Windows note: there is no portable way to ask for "Downloads" here - os.path.expanduser("~")
joined with "Downloads" breaks whenever the user (or OneDrive's Known Folder Move) has
relocated it, which Explorer's own Properties > Location tab lets anyone do, and Downloads
has never had an Environment.SpecialFolder-style constant. The only correct way is to ask
Windows itself via SHGetKnownFolderPath(FOLDERID_Downloads), with the registry key that
Explorer's Properties > Location tab actually writes to as a fallback.
"""

from __future__ import annotations

import os
import sys

_FOLDERID_DOWNLOADS = "374DE290-123F-4565-9164-39C4925E467B"


def get_downloads_dir() -> str:
    """Best-effort path to the current user's real Downloads folder."""
    if sys.platform == "win32":
        path = _windows_downloads_dir()
        if path and os.path.isdir(path):
            return path
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _windows_downloads_dir() -> str | None:
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        folder_id = GUID(
            0x374DE290, 0x123F, 0x4565,
            (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B),
        )

        sh_get_known_folder_path = ctypes.windll.shell32.SHGetKnownFolderPath
        sh_get_known_folder_path.argtypes = [
            ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        sh_get_known_folder_path.restype = ctypes.c_long

        buf = ctypes.c_wchar_p()
        hresult = sh_get_known_folder_path(ctypes.byref(folder_id), 0, 0, ctypes.byref(buf))
        if hresult == 0 and buf.value:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return path
    except Exception:
        pass

    # Fallback: the registry value Explorer's own Properties > Location tab writes to.
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "{%s}" % _FOLDERID_DOWNLOADS)
        return os.path.expandvars(value)
    except Exception:
        return None
