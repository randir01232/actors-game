"""Fetch candidate portrait thumbnails from Wikimedia Commons for each celebrity."""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "actors-memory-game/1.0 (https://github.com/randir01232/actors-game; educational hobby project)"
OUT = sys.argv[1]
PER_PERSON = int(sys.argv[2]) if len(sys.argv) > 2 else 30
PEOPLE = [
    "Natalie Portman", "Keira Knightley", "Elijah Wood", "Tobey Maguire", "Amy Adams", "Isla Fisher",
    "Javier Bardem", "Jeffrey Dean Morgan", "Margot Robbie", "Samara Weaving", "Jessica Chastain",
    "Bryce Dallas Howard", "Katy Perry", "Zooey Deschanel", "Jeremy Renner", "Nathan Fillion",
    "Kurt Russell", "Jeff Bridges", "Salma Hayek", "Penélope Cruz", "Matt Damon", "Mark Wahlberg",
    "Henry Cavill", "Matt Bomer", "Will Ferrell", "Chad Smith", "Zoe Saldaña", "Thandiwe Newton",
]

def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 + attempt * 3)

def api(base, **params):
    params.update(format="json", formatversion="2")
    return json.loads(get(base, params))

def commons_category(title):
    d = api("https://www.wikidata.org/w/api.php", action="wbgetentities", sites="enwiki", titles=title, props="claims")
    ent = next(iter(d["entities"].values()))
    claims = ent.get("claims", {}).get("P373", [])
    return ent.get("id"), (claims[0]["mainsnak"]["datavalue"]["value"] if claims else title)

def depicts(qid, limit=150):
    d = api("https://commons.wikimedia.org/w/api.php", action="query", generator="search",
            gsrsearch=f"haswbstatement:P180={qid} filemime:image/jpeg", gsrnamespace="6", gsrlimit=str(limit),
            prop="imageinfo", iiprop="url|mime|extmetadata|size", iiurlwidth="720")
    return [dict(i, via="depicts") for i in (info(p) for p in d.get("query", {}).get("pages", [])) if i]

def by_title(person, limit=200):
    d = api("https://commons.wikimedia.org/w/api.php", action="query", generator="search",
            gsrsearch=f'intitle:"{person}" filemime:image/jpeg', gsrnamespace="6", gsrlimit=str(limit),
            prop="imageinfo", iiprop="url|mime|extmetadata|size", iiurlwidth="720")
    return [dict(i, via="title") for i in (info(p) for p in d.get("query", {}).get("pages", [])) if i]

def info(p):
    ii = (p.get("imageinfo") or [{}])[0]
    if ii.get("mime") not in ("image/jpeg", "image/png") or ii.get("width", 0) < 300:
        return None
    md = ii.get("extmetadata", {})
    return {"title": p["title"], "thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"),
            "license": strip_html(md.get("LicenseShortName", {}).get("value")),
            "artist": strip_html(md.get("Artist", {}).get("value"))[:200]}

def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()

def files_in(cat, depth=2, seen=None):
    seen = seen if seen is not None else set()
    if cat in seen:
        return []
    seen.add(cat)
    out = []
    cont = {}
    while True:
        d = api("https://commons.wikimedia.org/w/api.php", action="query", generator="categorymembers",
                gcmtitle="Category:" + cat, gcmtype="file", gcmlimit="200", prop="imageinfo",
                iiprop="url|mime|extmetadata|size", iiurlwidth="720", **cont)
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png"):
                continue
            if ii.get("width", 0) < 300:
                continue
            md = ii.get("extmetadata", {})
            out.append({
                "title": p["title"], "thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"),
                "license": strip_html(md.get("LicenseShortName", {}).get("value")),
                "artist": strip_html(md.get("Artist", {}).get("value"))[:200], "via": cat,
            })
        if "continue" not in d:
            break
        cont = {k: v for k, v in d["continue"].items()}
    if depth > 0:
        d = api("https://commons.wikimedia.org/w/api.php", action="query", list="categorymembers",
                cmtitle="Category:" + cat, cmtype="subcat", cmlimit="100")
        for sc in d.get("query", {}).get("categorymembers", []):
            name = sc["title"].split(":", 1)[1]
            # skip obviously off-topic subcats (signatures, roles, films, etc.)
            if re.search(r"signature|star on|wax|caricature|statue|graffiti|drawing|painting|character|video|films? (by|starring|with)|in fiction|works|audio|logo|album|song|performances? by", name, re.I):
                continue
            out += files_in(name, depth - 1, seen)
    return out

def bad_name(t):
    return re.search(r"signature|autograph|poster|logo|wax|tussaud|statue|crowd|family|\band\b|&|\bwith\b|star on|walk of fame|drawing|cosplay|impersonat|lookalike|look-alike", t, re.I)

def norm(t):
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()

def main():
    only = [x for x in os.environ.get("ONLY", "").split(",") if x]
    mpath = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(mpath)) if only and os.path.exists(mpath) else {}
    for person in (only or PEOPLE):
        slug = re.sub(r"[^a-z0-9]+", "-", person.lower().replace("é", "e").replace("ñ", "n")).strip("-")
        qid, cat = commons_category(person)
        surname = norm(person.split()[-1])
        cand = [f for f in depicts(qid) if f] + files_in(cat)
        if os.environ.get("TITLE_SEARCH"):
            cand += by_title(person)
        files = [f for f in cand if f["thumb"] and not bad_name(f["title"])
                 and (surname in norm(f["title"]) or f["via"] == "depicts" or surname in norm(f["via"]))]
        # dedupe and spread across the list so we get different years/events
        uniq = list({f["title"]: f for f in files}.values())
        # round-robin across "series" (title without numbers) so one event can't flood the pool
        groups = {}
        for f in uniq:
            groups.setdefault(re.sub(r"[\d\W_]+", " ", norm(f["title"])).strip(), []).append(f)
        buckets = list(groups.values()); picked = []
        while len(picked) < PER_PERSON and any(buckets):
            for b in buckets:
                if b and len(picked) < PER_PERSON:
                    picked.append(b.pop(0))
        if only:
            import shutil; shutil.rmtree(os.path.join(OUT, slug), ignore_errors=True)
        os.makedirs(os.path.join(OUT, slug), exist_ok=True)
        def dl(i_f):
            i, f = i_f
            ext = ".png" if f["thumb"].lower().endswith(".png") else ".jpg"
            path = os.path.join(OUT, slug, f"{i:03d}{ext}")
            if not os.path.exists(path):
                try:
                    data = get(f["thumb"])
                    open(path, "wb").write(data)
                except Exception as e:
                    print("  fail", f["title"], e, file=sys.stderr)
                    return None
            f["file"] = os.path.basename(path)
            return f
        with ThreadPoolExecutor(3) as ex:
            got = [f for f in ex.map(dl, enumerate(picked)) if f]
        manifest[slug] = {"name": person, "category": cat, "files": got}
        print(f"{person}: category={cat!r} total={len(uniq)} downloaded={len(got)}", flush=True)
        json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), ensure_ascii=False, indent=1)

main()
