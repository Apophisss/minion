"""Stand-ins for OSWorld evaluator dependencies the office tasks never call (OCR, audio, browser, Google Drive)."""

import sys
import types


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return type(name, (Exception,), {})  # a class, usable as a base, a callable or an exception


for _name in [
    "easyocr",
    "librosa",
    "playwright",
    "playwright.sync_api",
    "acoustid",
    "fastdtw",
    "borb",
    "borb.pdf",
    "borb.pdf.canvas",
    "borb.pdf.canvas.layout",
    "pydrive",
    "pydrive.auth",
    "pydrive.drive",
]:
    sys.modules.setdefault(_name, _Stub(_name))
