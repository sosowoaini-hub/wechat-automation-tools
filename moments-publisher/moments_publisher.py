# -*- coding: utf-8 -*-
"""发微信朋友圈（Windows 微信 4.x）—— 纯 UI 自动化，无 Hook、无逆向。

把一组图片/视频（最多9个）连同文字发到微信朋友圈。走官方客户端界面，
不注入进程、不读数据库，因此不存在封号风险，也不依赖特定微信版本偏移。

原理：uiautomation 找到微信主窗口 -> 点"朋友圈" -> 点"发表" ->
      在文件对话框填入素材路径 -> 校验编辑器 -> 填文字 -> 发表。
      视频超过 28 秒会先用 ffmpeg 裁剪重编码（朋友圈限制 30 秒）。

用法：
  # 试运行（附加素材+校验编辑器，最后取消，绝不发布）
  python moments_publisher.py --images "a.jpg;b.png" --text "周末快乐"
  # 真发布
  python moments_publisher.py --images "a.jpg" --text "周末快乐" --go
  # 从归档目录挑选最新 N 张（需配 config.json 的 archive_dir）
  python moments_publisher.py --latest 3 --go

安全：不带 --go 永远不发布。最多 9 个素材。

依赖：pip install uiautomation pywin32
可选：ffmpeg（仅当发视频且视频超过 28 秒时需要）
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import uiautomation as auto
except ImportError:
    sys.exit("缺少依赖：pip install uiautomation  （Windows 专用）")

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"


def load_config():
    cfg = {}
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg.setdefault("archive_dir", str(HERE / "archive"))   # 图片归档根目录（可选）
    cfg.setdefault("prep_dir", str(HERE / "_prep"))        # 视频裁剪临时目录
    cfg.setdefault("log_file", str(HERE / "moments.log"))
    cfg.setdefault("ffmpeg", "ffmpeg")                     # ffmpeg 可执行文件
    cfg.setdefault("ffprobe", "ffprobe")
    cfg.setdefault("max_video_sec", 28.0)
    cfg.setdefault("wechat_title", "微信")                 # 微信主窗口标题
    return cfg


CFG = load_config()
MAX_IMAGES = 9


def log(msg):
    line = "%s %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(CFG["log_file"], "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# ---------- uiautomation 小工具 ----------
def find_class(ctrl, class_name, depth=0, max_depth=12):
    found = []
    if depth > max_depth:
        return found
    try:
        children = ctrl.GetChildren()
    except Exception:
        return found
    for c in children:
        try:
            if (c.ClassName or "") == class_name:
                found.append(c)
        except Exception:
            pass
        found.extend(find_class(c, class_name, depth + 1, max_depth))
    return found


def find_name(ctrl, name, depth=0, max_depth=12):
    found = []
    if depth > max_depth:
        return found
    try:
        children = ctrl.GetChildren()
    except Exception:
        return found
    for c in children:
        try:
            if (c.Name or "") == name:
                found.append(c)
        except Exception:
            pass
        found.extend(find_name(c, name, depth + 1, max_depth))
    return found


def close_window(w):
    try:
        w.GetWindowPattern().Close()
        return
    except Exception:
        pass
    try:
        w.SendKeys("{ESC}")
    except Exception:
        pass


def get_sns():
    for w in auto.GetRootControl().GetChildren():
        if w.ClassName == "mmui::SNSWindow":
            return w
    return None


def find_file_dialog():
    for c in find_class(auto.GetRootControl(), "#32770"):
        if "选择文件" in (c.Name or ""):
            return c
    return None


# ---------- 素材准备 ----------
def probe_duration(path):
    try:
        r = subprocess.run(
            [CFG["ffprobe"], "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, timeout=30)
        val = (r.stdout or b"").decode().strip().splitlines()
        return float(val[0]) if val else None
    except Exception:
        return None


def prepare_video(path):
    """超过 28 秒的视频先裁剪重编码，返回可发的 mp4 路径。"""
    limit = float(CFG["max_video_sec"])
    dur = probe_duration(path)
    if dur is not None and dur <= limit:
        log("video %s %.1fs OK (no trim)" % (Path(path).name, dur))
        return str(path)
    prep = Path(CFG["prep_dir"])
    prep.mkdir(parents=True, exist_ok=True)
    out = prep / ("moments_%s.mp4" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    cmd = [CFG["ffmpeg"], "-y", "-i", str(path), "-t", str(limit),
           "-vf", "scale='min(1280,iw)':-2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(out)]
    log("video %s dur=%s -> trim to %s" % (Path(path).name, dur, out.name))
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("ffmpeg 裁剪失败: %s" % (r.stderr or b"").decode("utf-8", "ignore")[-300:])
    return str(out)


def pick_latest_from_archive(n, group=None):
    """从归档目录的 manifest.json 里挑最新 N 张图片。"""
    items = []
    root = Path(CFG["archive_dir"])
    if not root.exists():
        return []
    for mf in root.rglob("manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in data if isinstance(data, list) else []:
            if it.get("type") != "image":
                continue
            if group and it.get("group") != group:
                continue
            p = Path(it.get("file", ""))
            if p.exists():
                items.append((it.get("time", ""), str(p)))
    items.sort(reverse=True)
    return [p for _, p in items[:n]]


# ---------- 发朋友圈主流程 ----------
def close_sns_and_restore():
    """关掉朋友圈窗口，把微信主窗口切回前台。"""
    for _ in range(3):
        found = False
        for w in auto.GetRootControl().GetChildren():
            if (w.ClassName or "") == "mmui::SNSWindow":
                found = True
                close_window(w)
        if not found:
            break
        time.sleep(1)
    try:
        import win32gui, win32con
        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == CFG["wechat_title"]:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass


def attach_images(images):
    """打开朋友圈，点发表，一次填入所有素材路径，返回编辑器窗口。"""
    for w in auto.GetRootControl().GetChildren():
        try:
            cls = w.ClassName or ""
            if cls == "mmui::SNSWindow" or (cls == "#32770" and "选择文件" in (w.Name or "")):
                close_window(w)
        except Exception:
            pass
    time.sleep(2)

    main = next((w for w in auto.GetRootControl().GetChildren()
                 if w.ClassName == "mmui::MainWindow"), None)
    if main is None:
        raise RuntimeError("找不到微信主窗口，请先登录微信")
    nav = next((c for c in find_name(main, "朋友圈")
                if c.ControlTypeName == "ButtonControl"), None)
    if nav is None:
        raise RuntimeError("找不到'朋友圈'入口按钮")
    try:
        main.SetActive(); main.SetFocus()
    except Exception:
        pass
    nav.Click(); time.sleep(5)

    sns = get_sns()
    if sns is None:
        raise RuntimeError("找不到朋友圈窗口")
    dialog = None
    for _ in range(6):
        pub = next((c for c in find_name(sns, "发表")
                    if c.ControlTypeName == "ButtonControl"), None)
        if pub is not None:
            try:
                sns.SetActive(); sns.SetFocus(); pub.Click()
            except Exception:
                pass
        time.sleep(3)
        dialog = find_file_dialog()
        if dialog is not None:
            break
        sns = get_sns()
        if sns is None:
            break
    if dialog is None:
        raise RuntimeError("点了6次'发表'仍未出现文件对话框")

    edit = next((c for c in find_name(dialog, "文件名(N):")
                 if c.ControlTypeName == "EditControl"), None)
    if edit is None:
        raise RuntimeError("找不到文件名输入框")
    edit.GetValuePattern().SetValue(" ".join('"%s"' % p for p in images))
    time.sleep(1)
    opened = next((c for c in find_name(dialog, "打开(O)")
                   if c.ControlTypeName == "ButtonControl"), None)
    if opened is None:
        raise RuntimeError("找不到'打开'按钮")
    opened.Click(); time.sleep(15)
    sns = get_sns()
    if sns is None:
        raise RuntimeError("附加素材后找不到编辑器")
    return sns


def publish(images, text, go):
    if not images:
        raise RuntimeError("没有素材")
    if len(images) > MAX_IMAGES:
        raise RuntimeError("最多 %d 个素材，收到 %d 个" % (MAX_IMAGES, len(images)))
    for p in images:
        if not Path(p).is_file():
            raise RuntimeError("素材不存在: " + p)

    images = [prepare_video(p) if Path(p).suffix.lower() in (".mp4", ".mov", ".avi", ".mkv") else p
              for p in images]
    log("附加 %d 个素材..." % len(images))
    sns = attach_images(images)
    time.sleep(2)

    if find_name(sns, "照片未发送") or find_name(auto.GetRootControl(), "照片未发送"):
        close_window(sns)
        raise RuntimeError("素材上传失败（照片未发送）")

    if text:
        edits = find_class(sns, "mmui::XValidatorTextEdit")
        if not edits:
            raise RuntimeError("找不到文字输入框")
        edits[0].GetValuePattern().SetValue(text)
        log("文字已填入（%d 字）" % len(text))

    if not go:
        # 试运行：点"取消"，不发布
        for c in find_class(sns, "mmui::XOutlineButton"):
            if (c.Name or "") == "取消":
                try:
                    c.Click(); break
                except Exception:
                    pass
        time.sleep(1.5)
        close_sns_and_restore()
        log("DRY-RUN OK：编辑器已校验并取消，未发布任何内容。")
        return {"published": False, "images": images}

    clicked = False
    for c in find_class(sns, "mmui::XOutlineButton"):
        if (c.Name or "") == "发表":
            c.Click(); clicked = True
            break
    if not clicked:
        raise RuntimeError("编辑器里找不到'发表'按钮")
    log("已发布。")
    time.sleep(3)
    close_sns_and_restore()
    return {"published": True, "images": images}


def main():
    ap = argparse.ArgumentParser(description="发微信朋友圈（UIA，无需 Hook）")
    ap.add_argument("--images", default="", help="分号分隔的素材路径")
    ap.add_argument("--text", default="", help="朋友圈文字")
    ap.add_argument("--latest", type=int, default=0, help="从归档挑最新 N 张图片")
    ap.add_argument("--group", default="", help="按归档 manifest 的 group 字段筛选")
    ap.add_argument("--go", action="store_true", help="真发布（默认试运行，不发）")
    a = ap.parse_args()

    images = [p.strip() for p in a.images.split(";") if p.strip()]
    if a.latest:
        images = pick_latest_from_archive(a.latest, a.group or None)
        log("从归档挑了 %d 张: %s" % (len(images), images))
    try:
        result = publish(images, a.text, a.go)
        print("RESULT:", json.dumps(result, ensure_ascii=False))
    except Exception as e:
        log("FAIL: %r" % e)
        print("RESULT:", json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
