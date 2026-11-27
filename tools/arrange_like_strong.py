"""Argon arranged like the owner's Strong (owner, 27 Nov 2026: "Argon, the closest thing to it, update it too").

Each Argon group is matched by name to the Strong group it is (beIN SPORTS 4K = beIN SPORTS 4K, FOX = FOX...):
matched groups take the place, the shown/hidden state and the owner's new name of their Strong group; groups Strong
has no match for stay right after the group they followed in Argon's own list. Writes xtream/argon/owner_arrange.json
in the same shape the app reads for Strong. Run by hand after the owner's arrangement changes."""
import json
import re
import unicodedata

SMALL = str.maketrans("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢѕ", "ABCDEFGHIJKLMNOPQRSTUVWYZS")


def norm(n):
    t = unicodedata.normalize("NFKC", n.translate(SMALL)).upper()
    t = re.sub(r"[^A-Z0-9؀-ۿ ]", " ", t)
    t = re.sub(r"\b(HD|FHD|UHD|SD|RAW|60FPS|CHANNELS?)\b", " ", t)
    return " ".join(t.split())


def load(pl):
    vis = [(c["category_id"], c["category_name"]) for c in json.load(open(f"xtream/{pl}/live_categories.json", encoding="utf-8"))]
    try:
        hid = [(c["category_id"], c["category_name"]) for c in json.load(open(f"xtream/{pl}/hidden_live.json", encoding="utf-8"))["cats"]]
    except FileNotFoundError:
        hid = []
    return vis, hid


def main():
    so = json.load(open("xtream/strong/owner_arrange.json", encoding="utf-8"))
    sv, sh = load("strong")
    sname = dict(sv + sh)
    s_default_hidden = {i for i, _ in sh}
    s_hidden = lambda i: i in so["hidden"] or (i in s_default_hidden and i not in so["shown"])  # noqa: E731
    spos = {i: k for k, i in enumerate(so["order"])}
    sidx = {}
    for i, n in sname.items():
        sidx.setdefault(norm(n), i)
    av, ah = load("argon")
    a_default_hidden = {i for i, _ in ah}
    order_keys, hidden, shown, names, matched = [], [], [], {}, 0
    last = -1.0
    for k, (i, n) in enumerate(av + ah):
        s = sidx.get(norm(n))
        if s is None:
            words = set(norm(n).split())
            best = max(((len(words & set(m.split())) / max(1, len(words | set(m.split()))), j) for m, j in sidx.items()), default=(0, None))
            s = best[1] if best[0] >= 0.75 else None
        if s is not None and s in spos:
            matched += 1
            last = spos[s]
            order_keys.append((last, k, i))
            h = s_hidden(s)
            # a group Argon's own list shows stays shown (the owner picked Argon's list); only Argon's hidden ones
            # the owner shows on Strong come out
            if not h and i in a_default_hidden:
                shown.append(i)
            if s in so["names"]:
                names[i] = so["names"][s]
        else:
            order_keys.append((last + 0.001 * (k + 1) / 1000, k, i))
    order = [i for _, _, i in sorted(order_keys)]
    # the owner's own Argon choices stay (the PPV package he showed there)
    try:
        own = json.load(open("xtream/argon/owner_arrange.json", encoding="utf-8"))
        shown += [x for x in own.get("shown", []) if x not in shown]
    except FileNotFoundError:
        pass
    out = {"from": "Strong arrangement, matched by name", "saved": so["saved"], "order": order, "hidden": sorted(hidden),
           "shown": sorted(shown), "hidden_channels": [], "channel_order": {}, "names": names}
    json.dump(out, open("xtream/argon/owner_arrange.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"argon: {matched} of {len(av) + len(ah)} groups matched to Strong; {len(hidden)} hidden, {len(shown)} shown, {len(names)} renamed")


if __name__ == "__main__":
    main()
