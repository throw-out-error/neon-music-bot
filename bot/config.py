import lazyConfig
from pathlib import Path

cfg_path = Path("config").resolve()
cfg = lazyConfig.from_path(
    config=cfg_path,
)
