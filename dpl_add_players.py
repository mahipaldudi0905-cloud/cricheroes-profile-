"""dpl_add_list.json ke players ko CricHeroes app me 'Add via phone number' se team me add karta hai.

Usage: python3 dpl_add_players.py [kitne_players]
App ek baar me max 16 players add karne deta hai, isliye har 16 par commit hota hai.
Har player ka result dpl_add_log.json me likha jata hai; jo already log me hai wo skip hota hai.
Kuch bhi unexpected dikhe to script ruk jati hai (commit nahi karti).
"""
import json
import os
import sys

import phone_ui as p

HERE = os.path.dirname(os.path.abspath(__file__))
LIST = os.path.join(HERE, "dpl_add_list.json")
LOG = os.path.join(HERE, "dpl_add_log.json")
FORM_TITLE = "Add multiple players via phone number"
TEAM_ID = 14725807
BATCH = 16


def load_log():
    return json.load(open(LOG)) if os.path.exists(LOG) else {}


def save_log(log):
    json.dump(log, open(LOG, "w"), indent=1, ensure_ascii=False)


def on_form(nodes):
    return p.find(nodes, text=FORM_TITLE) is not None


def empty_box(nodes):
    return next((n for n in nodes if n["id"].endswith("etPhoneNumber") and not n["text"].isdigit()), None)


def open_form():
    for _ in range(4):
        nodes = p.dump()
        if on_form(nodes):
            return nodes
        n = p.find(nodes, id="lnrAddViaPhoneNumber") or p.find(nodes, id="btnAddPlayer")
        if not n:
            raise SystemExit("STOP: na form mila na Add player button. Screen check karo.")
        p.tap_node(n)
        p.wait(2)
    raise SystemExit("STOP: phone number form nahi khula.")


def rows(nodes):
    names = [n for n in nodes if n["id"].endswith("tvPlayerName")]
    cities = [n for n in nodes if n["id"].endswith("tvCity")]
    out = set()
    for nm in names:
        city = next((c["text"] for c in cities if abs(c["bounds"][1] - nm["bounds"][3]) < 30), "")
        out.add((nm["text"], city))
    return out


def stage(item, nodes):
    """Ek number daal kar Done. Returns (result, naya screen nodes)."""
    if p.find(nodes, id="etPlayerName"):
        p.tap_node(p.find(nodes, id="btnClose"))
        p.wait(1)
        nodes = p.dump()
    box = empty_box(nodes)
    if not box:
        p.tap_node(p.find(nodes, id="btnDone"))  # list ke neeche naya khaali box aata hai
        p.wait(1.5)
        nodes = p.dump()
        box = empty_box(nodes)
        if not box:
            raise SystemExit("STOP: khaali phone number box nahi mila.")
    before = rows(nodes)
    p.tap_node(box)
    p.wait(0.4)
    p.type_text(item["mobile"])
    p.wait(0.3)
    p.tap(540, 1434)  # keyboard khula ho to Done hamesha yahin hota hai
    p.wait(2)
    nodes = p.dump()
    if p.find(nodes, id="etPlayerName"):
        p.tap_node(p.find(nodes, id="btnClose"))
        p.wait(1)
        return {"status": "Not on CricHeroes", "ch_name": "", "ch_city": ""}, p.dump()
    new = list(rows(nodes) - before)
    still = any(n["id"].endswith("etPhoneNumber") and n["text"] == item["mobile"] for n in nodes)
    if not on_form(nodes) or still or len(new) != 1:
        p.screenshot(f"stop_P{item['pno']}")
        texts = sorted({n["text"] for n in nodes if n["text"]})
        return {"status": "STOP", "screen_texts": texts, "new_rows": new}, nodes
    return {"status": "Staged", "ch_name": new[0][0], "ch_city": new[0][1]}, nodes


def commit(nodes):
    """Khaali box ke saath Done = list ke saare players team me add."""
    for _ in range(3):
        if not on_form(nodes):
            return
        p.tap_node(p.find(nodes, id="btnDone"))
        p.wait(4)
        nodes = p.dump()
    p.screenshot("stop_commit")
    raise SystemExit("STOP: commit nahi hua. Screenshot: ui_dumps/stop_commit.png")


def verify(log):
    from cricheroes_scraper import api
    members = api(f"team/get-team-member/{TEAM_ID}")["members"]
    names = {m["name"] for m in members}
    for v in log.values():
        if v["status"] == "Staged":
            v["status"] = "Added" if v["ch_name"] in names else "NOT IN TEAM"
    return len(members)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10 ** 6
    items = [i for i in json.load(open(LIST))]
    log = load_log()
    todo = [i for i in items if str(i["pno"]) not in log][:limit]
    nodes = None
    staged = 0
    for item in todo:
        if nodes is None:
            nodes = open_form()
        res, nodes = stage(item, nodes)
        res.update(pno=item["pno"], name=item["name"], mobile=item["mobile"])
        print(res, flush=True)
        if res["status"] == "STOP":
            print("Unexpected screen - ruk gaya, commit NAHI kiya. Screenshot: ui_dumps/stop_P%s.png" % item["pno"])
            save_log(log)
            return
        log[str(item["pno"])] = res
        save_log(log)
        if res["status"] == "Staged":
            staged += 1
        if staged == BATCH:
            commit(nodes)
            print("Team size:", verify(log), flush=True)
            save_log(log)
            staged, nodes = 0, None
    if staged:
        commit(nodes)
    size = verify(log)
    save_log(log)
    from collections import Counter
    print("Team size:", size, "|", dict(Counter(v["status"] for v in log.values())))
    print("Not in team:", [(k, v["ch_name"]) for k, v in log.items() if v["status"] == "NOT IN TEAM"])


if __name__ == "__main__":
    main()
