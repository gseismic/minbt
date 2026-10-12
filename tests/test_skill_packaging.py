"""验证 skill 真正随发行物安装，避免源码路径掩盖漏打包问题。"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

from build import ProjectBuilder
from build.env import DefaultIsolatedEnv
import pytest

from minbt.skills import get_skill_path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(command, cwd, env=None):
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def _build_runner(command, cwd=None, extra_environ=None):
    _run(command, cwd, {**os.environ, **(extra_environ or {})})


@pytest.fixture(scope="module")
def skill_distributions(tmp_path_factory):
    """干净构建不使用工作区的 egg-info、build 缓存或未发布的外部文档。"""
    root = tmp_path_factory.mktemp("skill-distributions")
    source = root / "source"
    source.mkdir()
    for directory in ("minbt", "skills"):
        shutil.copytree(
            REPO_ROOT / directory, source / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(REPO_ROOT / filename, source / filename)

    with DefaultIsolatedEnv() as build_env:
        builder = ProjectBuilder.from_isolated_env(build_env, source, runner=_build_runner)
        build_env.install(builder.build_system_requires)
        build_env.install(
            builder.get_requires_for_build("sdist") | builder.get_requires_for_build("wheel")
        )
        sdist = Path(builder.build("sdist", root / "sdist"))
        wheel = Path(builder.build("wheel", root / "wheel"))
        unpacked = root / "unpacked"
        with tarfile.open(sdist) as archive:
            # 兼容 Python 3.8，并在支持过滤器的版本上显式使用数据解压规则。
            if hasattr(tarfile, "data_filter"):
                archive.extractall(unpacked, filter="data")
            else:
                archive.extractall(unpacked)
        sdist_source = next(unpacked.iterdir())
        rebuilt = ProjectBuilder.from_isolated_env(build_env, sdist_source, runner=_build_runner)
        build_env.install(rebuilt.build_system_requires | rebuilt.get_requires_for_build("wheel"))
        sdist_wheel = Path(rebuilt.build("wheel", root / "sdist-wheel"))

    expected = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in (source / "minbt" / "skills" / "minbt-usage").rglob("*")
        if path.is_file()
    }
    expected_python = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in (source / "minbt").rglob("*.py")
    }
    return {
        "sdist": sdist, "wheel": wheel, "sdist-wheel": sdist_wheel,
        "expected": expected, "expected_python": expected_python,
    }


@pytest.mark.parametrize("kind", ["sdist", "wheel", "sdist-wheel"])
def test_distributions_include_complete_skill_resources(skill_distributions, kind):
    """完整比对资源内容，新增但未声明打包的文件也应使发布检查失败。"""
    if kind == "sdist":
        with tarfile.open(skill_distributions[kind]) as archive:
            files = {
                member.name.split("/", 1)[1]: archive.extractfile(member).read()
                for member in archive.getmembers() if member.isfile()
            }
    else:
        with zipfile.ZipFile(skill_distributions[kind]) as archive:
            files = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}

    resources = {name: content for name, content in files.items() if name.startswith("minbt/skills/minbt-usage/")}
    assert resources == skill_distributions["expected"]
    python_sources = {
        name: content for name, content in files.items()
        if name.startswith("minbt/") and name.endswith(".py")
    }
    assert python_sources == skill_distributions["expected_python"]
    assert not any("library-design-zh" in name for name in files)


@pytest.mark.parametrize("kind", ["wheel", "sdist-wheel"])
def test_installed_skill_works_outside_repository(skill_distributions, kind, tmp_path):
    """真实安装两种 wheel，确保 CLI、相对资料和示例使用安装目录的资源。"""
    target = tmp_path / "installed"
    outside = tmp_path / "outside"
    outside.mkdir()
    _run([
        sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
        "--disable-pip-version-check", "--target", str(target), str(skill_distributions[kind]),
    ], outside)
    env = {**os.environ, "PYTHONPATH": str(target), "PYTHONNOUSERSITE": "1"}
    skill_path = target / "minbt" / "skills" / "minbt-usage"
    version = _run([
        sys.executable, "-c",
        "from importlib.metadata import version; print(version('minbt'))",
    ], outside, env)
    assert _run([sys.executable, "-m", "minbt.skills", "--path"], outside, env) == str(skill_path)
    assert _run([sys.executable, "-m", "minbt.skills"], outside, env).splitlines() == [
        f"minbt {version}", f"skill: {skill_path}",
    ]
    assert _run([
        sys.executable, "-c", "import minbt; print(minbt.__file__)",
    ], outside, env) == str(target / "minbt" / "__init__.py")
    assert "--path" in _run([sys.executable, "-m", "minbt.skills", "--help"], outside, env)
    invalid = subprocess.run(
        [sys.executable, "-m", "minbt.skills", "--unknown"], cwd=outside,
        env=env, text=True, capture_output=True, timeout=30,
    )
    assert invalid.returncode == 2
    assert _run([
        sys.executable, str(skill_path / "scripts" / "quickstart.py"),
    ], outside, env) == "final_equity=1020.00"

    content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
    for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
        assert (skill_path / link).is_file(), link
    example = re.findall(r"^```python\n(.*?)^```", content, re.MULTILINE | re.DOTALL)[0]
    assert _run([sys.executable, "-c", example], outside, env) == "final_equity=1020.00"

    reference = (skill_path / "references" / "data-and-control.md").read_text(encoding="utf-8")
    config_example = next(
        block for block in re.findall(r"^```python\n(.*?)^```", reference, re.MULTILINE | re.DOTALL)
        if "from minbt import Bar, Strategy, run" in block
    )
    protocol_checks = """
from minbt import Broker, OrderSnapshot
import sys
assert Broker.__module__ == "minbt.broker.broker"
assert not any(name == "minbt.plugins" or name.startswith("minbt.plugins.") for name in sys.modules)
from minbt.plugins.storage import CsvBarFeed
from minbt.protocols import DataFeedProtocol, ResultProtocol
from minbt.protocols.result import OrderSnapshot as StandardOrderSnapshot
assert isinstance(MyFeed(), DataFeedProtocol)
assert CsvBarFeed.__module__ == "minbt.plugins.storage.bar_feed"
assert OrderSnapshot is StandardOrderSnapshot
assert isinstance(result, ResultProtocol)
assert result.get_total_pnl().net_pnl == 20
assert result.get_position_sizes() == {"TEST": 1}
"""
    assert _run([
        sys.executable, "-c", config_example + protocol_checks,
    ], outside, env) == "final_equity=1020.00"

    # 安装资源被移除时应报错，不回退到工作区或全局旧 skill。
    (skill_path / "SKILL.md").unlink()
    missing = subprocess.run(
        [sys.executable, "-m", "minbt.skills", "--path"], cwd=outside,
        env=env, text=True, capture_output=True, timeout=30,
    )
    assert missing.returncode != 0
    assert "FileNotFoundError" in missing.stderr
    assert str(skill_path) in missing.stderr


def test_repository_skill_link_uses_packaged_source():
    """仓库发现入口与包资源共用一份内容，不保留根目录副本。"""
    link = REPO_ROOT / ".agents" / "skills" / "minbt-usage"
    assert link.is_symlink()
    assert link.resolve() == get_skill_path()
    assert not (REPO_ROOT / "skills" / "minbt-usage").exists()
