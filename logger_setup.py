"""
logger_setup.py - Forces all output to pipeline.log file AND stderr.
Import this as the very first line in api.py / app.py.
"""
import logging
import sys
import pathlib

def setup():
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Write to stderr — safe management for Streamlit & Uvicorn
    try:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(fmt)
        root.addHandler(stderr_handler)
    except Exception as e:
        
        stderr_handler = logging.StreamHandler(sys.__stderr__)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(fmt)
        root.addHandler(stderr_handler)

    # Always write to file as backup
    try:
        BASE_DIR = pathlib.Path(__file__).parent  # always the project folder
        file_handler = logging.FileHandler(str(BASE_DIR / "pipeline.log"), mode="a", encoding="utf-8")    
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        
        pass

    # Silence noisy libraries
    for lib in ("httpx", "httpcore", "chromadb", "sentence_transformers",
                "urllib3", "watchfiles", "uvicorn.access"):
        logging.getLogger(lib).setLevel(logging.WARNING)


setup()