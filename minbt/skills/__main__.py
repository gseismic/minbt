"""输出当前 Python 环境的 minbt 版本和用户 skill 路径。"""

import argparse
from importlib.metadata import PackageNotFoundError, version
from typing import Optional, Sequence

from . import get_skill_path


def main(argv: Optional[Sequence[str]] = None) -> None:
    """默认输出版本与目录，--path 提供便于工具读取的纯路径。"""
    parser = argparse.ArgumentParser(description="查找当前 Python 环境的 minbt 用户 skill。")
    parser.add_argument("--path", action="store_true", help="只输出 minbt-usage 的绝对目录")
    args = parser.parse_args(argv)
    skill_path = get_skill_path()
    if args.path:
        print(skill_path)
        return

    try:
        installed_version = version("minbt")
    except PackageNotFoundError:
        installed_version = "源码（未安装发行元数据）"
    print(f"minbt {installed_version}")
    print(f"skill: {skill_path}")


if __name__ == "__main__":
    main()
