# src/khms_trader/config.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# config 디렉터리 위치: 레포 루트/config
# (src/khms_trader/config.py 기준으로 ../../config)
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a dict: {path}")
    return data


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    중첩 dict까지 안전하게 병합.
    override가 base를 덮어씀.
    """
    out: Dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


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


def load_settings() -> Dict[str, Any]:
    """
    일반 설정 (setting.yaml) + 민감 정보 (secrets.yaml) 병합 로드.

    - setting.yaml: GitHub에 올려도 되는 기본 설정
    - secrets.yaml: app_key/app_secret/account_no 등 민감정보 (절대 커밋 금지)
    """
    settings_path = CONFIG_DIR / "setting.yaml"
    settings = _load_yaml(settings_path)

    # 현재 정책 유지: secrets.yaml 없으면 에러 발생
    secrets = load_secrets()

    # secrets가 setting을 덮어쓰도록 병합
    merged = _deep_merge(settings, secrets)
    return merged
