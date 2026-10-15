#!/usr/bin/env python3
"""Build the competition submission zip (stdlib only).

Name format required by the organisers: 组别-参赛编号-队伍名称-队长姓名.zip
Layout inside the zip:
  提交材料.md, 测试样例.md, 运行证据.md, 独立完成声明.md, ...   docs/submission/** at the top level
  视频链接.txt                                                  template: main link, backup link, access code
  evidence/INDEX.md (+ copies of the small evidence files)       evidence index with sizes and SHA-256
  推送到GitHub步骤.txt                                           the one command for the Windows machine
  xiaobai2233/                                                   the publish tree (what goes to GitHub)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

LIMIT = 200 * 1024 * 1024
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TREE_DIR_IN_ZIP = "xiaobai2233"
EVIDENCE_COPY_LIMIT = 25 * 1024 * 1024

VIDEO_TEMPLATE = """演示视频链接（请队长在提交前填写，三项都填后再打包或直接修改本文件）

主链接：
备用链接：
访问码（没有则写 无）：

填写说明：
- 主链接和备用链接请使用不同的网盘或视频站，并在提交前用无痕窗口各打开一次，确认无需登录即可播放。
- 视频内容应与 提交材料.md、运行证据.md 中的说法一致；录屏清单见 录屏清单.md。
"""

DECLARATION_TEMPLATE = """# 独立完成声明（模板，待队长填写）

本文件是模板，不是已签署的声明。内容由队长核对后填写，未填写的方括号不代表任何承诺。

- 参赛组别：[待填]
- 参赛编号：[待填]
- 队伍名称：[待填]
- 队长姓名：[待填]

声明内容（请按实际情况修改后保留）：

1. 本参赛作品 Project Kernel（AGH 插件、内核、面板与文档）由本队独立完成。[待队长确认]
2. 开发中使用了 AI 编程助手和模型接口，使用情况见 运行证据.md；第三方依赖及其许可见仓库中的 pyproject.toml 与 adapters/agh-plugin/package.json。[待队长确认]
3. 提交材料中的测试结果、运行记录均来自可复现的命令与保存的证据文件；未完成或未验证的部分已在材料中标明。[待队长确认]

队长签名：[待填]    日期：[待填]
"""

PUSH_STEPS = """把代码仓库推送到 GitHub（在你自己的 Windows 电脑上做，约 3 分钟）

1. 把本 zip 解压到一个文件夹，例如 D:\\提交包 。
2. 按住 Shift 点右键，选“在此处打开 PowerShell 窗口”，粘贴下面这一整行并回车
   （把引号里的路径改成你实际解压出来的 xiaobai2233 文件夹）：

   powershell -NoProfile -ExecutionPolicy Bypass -File "D:\\提交包\\xiaobai2233\\tools\\publish.ps1"

3. 脚本会：下载你已有的仓库（不会删除里面的 LICENSE），把新内容复制进去，列出改动，
   然后问你是否继续。先看清楚列表，输入 yes 才会提交并推送；输入其他内容就取消，什么都不会改。
4. 想先演练一遍而不真正推送：在命令末尾加一个空格和 -DryRun 。
5. 如果弹出 GitHub 登录窗口，用仓库所有者的账号登录即可。
6. 推送是普通推送，不会强制覆盖；远程已有的第一个提交会保留。
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return str(n)


def clean_part(value: str, label: str) -> str:
    value = value.strip()
    if not value or ILLEGAL.search(value) or value.endswith("."):
        raise SystemExit(f"--{label} {value!r} is empty or has characters not allowed in Windows file names")
    return value


def evidence_index(tree: Path) -> tuple[str, list[Path]]:
    folders = [tree / "evidence"]
    files = []
    for folder in folders:
        if folder.is_dir():
            files += sorted(p for p in folder.rglob("*") if p.is_file())
    assets = sorted((tree / "docs" / "assets").glob("agh-*")) if (tree / "docs" / "assets").is_dir() else []
    lines = ["# 证据索引", "",
             "本索引由打包脚本根据发布树自动生成，列出每个证据文件的位置、大小和 SHA-256，便于核对文件未被改动。",
             "文件的含义和对应的说法见 运行证据.md；这里不做任何结论性描述。", "",
             "| 文件（相对 xiaobai2233/） | 大小 | SHA-256 |", "| --- | ---: | --- |"]
    for path in files + assets:
        rel = path.relative_to(tree).as_posix()
        lines.append(f"| `{rel}` | {human(path.stat().st_size)} | `{sha256_of(path)}` |")
    if not files and not assets:
        lines.append("| （发布树中还没有 evidence/ 或 docs/assets/agh-* 文件） | | |")
    lines += ["", "同一批文件也复制在本 zip 的 evidence/ 目录下（evidence/ 下的文件原样复制）。", ""]
    return "\n".join(lines), files


def placeholders(text: str) -> list[str]:
    found = re.findall(r"\{\{[A-Z_]+\}\}|待补|待填|待上传|待确认|\[待[^\]]*\]", text)
    return sorted(set(found))


def build(tree: Path, out_dir: Path, group: str, ident: str, team: str, captain: str) -> dict:
    name = "-".join(clean_part(v, k) for k, v in (("group", group), ("id", ident), ("team", team), ("captain", captain)))
    zip_path = out_dir / f"{name}.zip"
    out_dir.mkdir(parents=True, exist_ok=True)
    submission = tree / "docs" / "submission"
    if not tree.is_dir() or not (tree / "pyproject.toml").is_file():
        raise SystemExit(f"{tree} does not look like the publish tree")

    entries: dict[str, Path | bytes] = {}
    notes = []
    if submission.is_dir():
        for path in sorted(p for p in submission.rglob("*") if p.is_file()):
            entries[path.relative_to(submission).as_posix()] = path
    else:
        notes.append("docs/submission is missing in the tree")
    if not any(k.startswith("独立完成声明") for k in entries):
        entries["独立完成声明.md"] = DECLARATION_TEMPLATE.encode("utf-8")
        notes.append("独立完成声明.md did not exist: a clearly marked template was generated (to be filled by the captain)")
    if "视频链接.txt" not in entries:
        entries["视频链接.txt"] = VIDEO_TEMPLATE.encode("utf-8")
    index_text, evidence_files = evidence_index(tree)
    entries["evidence/INDEX.md"] = index_text.encode("utf-8")
    copy_total = sum(p.stat().st_size for p in evidence_files)
    if copy_total <= EVIDENCE_COPY_LIMIT:
        for path in evidence_files:
            entries["evidence/" + path.relative_to(tree / "evidence").as_posix()] = path
    else:
        notes.append(f"evidence copies skipped ({human(copy_total)} > limit); index only")
    entries["推送到GitHub步骤.txt"] = PUSH_STEPS.encode("utf-8")

    tree_files = sorted(p for p in tree.rglob("*") if p.is_file())
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for arc, source in entries.items():
            if isinstance(source, bytes):
                archive.writestr(arc, source)
            else:
                archive.write(source, arc)
        for path in tree_files:
            archive.write(path, f"{TREE_DIR_IN_ZIP}/{path.relative_to(tree).as_posix()}")

    size = zip_path.stat().st_size
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        names = archive.namelist()
        infos = archive.infolist()
    top = sorted({n.split("/")[0] for n in names})
    open_items = {}
    with zipfile.ZipFile(zip_path) as archive:
        for n in names:
            if "/" not in n and n.endswith((".md", ".txt")):
                found = placeholders(archive.read(n).decode("utf-8", "replace"))
                if found:
                    open_items[n] = found
    report = {
        "zip": str(zip_path), "name": zip_path.name, "bytes": size, "size": human(size), "within_200MB": size <= LIMIT,
        "testzip": "ok" if bad is None else f"bad member {bad}", "entries": len(names),
        "tree_files": len(tree_files), "top_level": top,
        "top_level_files": sorted(n for n in names if "/" not in n),
        "evidence_files_copied": sorted(n for n in names if n.startswith("evidence/")),
        "unfilled_placeholders": open_items, "notes": notes,
        "utf8_flag_names": sum(1 for i in infos if i.flag_bits & 0x800),
    }
    (out_dir / "zip_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if size > LIMIT:
        raise SystemExit(f"zip is {human(size)}, above the 200 MB limit")
    if bad is not None:
        raise SystemExit(f"zip integrity check failed: {bad}")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tree", default="/tmp/publish/tree", help="publish tree built by build_publish_tree.py")
    parser.add_argument("--group", default="本科生组")
    parser.add_argument("--id", default="待填")
    parser.add_argument("--team", default="待填")
    parser.add_argument("--captain", default="待填")
    parser.add_argument("--out", default=os.environ.get("PK_PUBLISH_OUT", "/ses" + "sions/inspiring-dreamy-planck/mnt/outputs/publish"))
    args = parser.parse_args(argv)
    report = build(Path(args.tree), Path(args.out), args.group, args.id, args.team, args.captain)
    print(json.dumps({k: report[k] for k in ("name", "size", "within_200MB", "testzip", "entries", "top_level")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
