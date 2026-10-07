"""Android phone (ADB) se screen padhna aur tap/type karna."""
import os
import re
import subprocess
import sys
import time

ADB = os.path.expanduser("~/platform-tools/adb")
SERIAL = os.environ.get("ADB_SERIAL", "10.250.3.123:40625")
DUMPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_dumps")


def adb(*args, binary=False):
    out = subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode(errors="ignore")


def dump(name="cur"):
    os.makedirs(DUMPS, exist_ok=True)
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    with open(os.path.join(DUMPS, f"{name}.xml"), "w") as f:
        f.write(xml)
    return parse(xml)


def screenshot(name="cur"):
    os.makedirs(DUMPS, exist_ok=True)
    path = os.path.join(DUMPS, f"{name}.png")
    with open(path, "wb") as f:
        f.write(adb("exec-out", "screencap", "-p", binary=True))
    return path


def parse(xml):
    nodes = []
    for m in re.finditer(r"<node [^>]*?/?>", xml):
        n = m.group(0)
        get = lambda k: (re.search(rf'{k}="([^"]*)"', n) or [None, ""])[1]
        b = [int(v) for v in re.findall(r"\d+", get("bounds"))]
        nodes.append({
            "text": get("text"), "desc": get("content-desc"), "id": get("resource-id"),
            "cls": get("class").split(".")[-1], "pkg": get("package"),
            "click": get("clickable") == "true", "bounds": b,
            "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) if len(b) == 4 else None,
        })
    return nodes


def show(nodes):
    for n in nodes:
        if n["text"] or n["desc"] or (n["id"] and n["click"]) or n["cls"] == "EditText":
            print(f'{n["cls"]:<14} {n["text"]!r:<34} {n["desc"]!r:<20} {n["id"]:<55} {n["bounds"]} {"CLICK" if n["click"] else ""}')


def find(nodes, text=None, id=None, desc=None, cls=None):
    for n in nodes:
        if text is not None and n["text"].strip().lower() != text.lower():
            continue
        if id is not None and not n["id"].endswith(id):
            continue
        if desc is not None and n["desc"].strip().lower() != desc.lower():
            continue
        if cls is not None and n["cls"] != cls:
            continue
        return n
    return None


def tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))


def tap_node(n):
    tap(*n["center"])


def type_text(s):
    adb("shell", "input", "text", s.replace(" ", "%s"))


def key(code):
    adb("shell", "input", "keyevent", str(code))


def wait(sec):
    time.sleep(sec)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "cur"
    print(adb("shell", "dumpsys", "window").split("mCurrentFocus")[1].split("\n")[0])
    show(dump(name))
    print("screenshot:", screenshot(name))
