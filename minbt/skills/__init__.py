"""随 minbt 版本发布的用户技能资源与定位接口。"""

from pathlib import Path


__all__ = ["get_skill_path"]


def get_skill_path() -> Path:
    """返回当前包的 minbt-usage 目录；安装缺少资源时明确报错。"""
    skill_path = Path(__file__).resolve().parent / "minbt-usage"
    if not (skill_path / "SKILL.md").is_file():
        raise FileNotFoundError(
            f"当前 minbt 安装缺少 skill：{skill_path / 'SKILL.md'}；请重新安装 minbt。"
        )
    return skill_path
