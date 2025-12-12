from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# 프로젝트 루트: .../khms_trader
ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Dict[str, Any]:
    """
    일반 설정 (setting.yaml) 로드.
    """
    path = CONFIG_DIR / "setting.yaml"
    return _load_yaml(path)


def load_secrets() -> Dict[str, Any]:
    """
    민감 정보 (secrets.yaml) 로드.

    - secrets.yaml 이 없으면 예시 파일(secrets.example.yaml)을 참고하라는 에러를 띄움.
    """
    path = CONFIG_DIR / "secrets.yaml"
    if not path.exists():
        example = CONFIG_DIR / "secrets.example.yaml"
        raise FileNotFoundError(
            f"secrets.yaml not found in {CONFIG_DIR}. "
            f"Copy {example.name} to secrets.yaml and fill your keys."
        )
    return _load_yaml(path)
