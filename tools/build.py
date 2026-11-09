"""Face-crop, rank, dedupe, convert to webp, and emit js/data.js + credits.html.

usage:
  python3 tools/fetch.py raw 40                     # download candidates from Wikimedia Commons
  swiftc -O tools/facecrop.swift -o tools/facecrop  # macOS Vision face detector
  python3 tools/build.py raw crops .                # crop, pick, write img/, js/data.js, credits.html
"""
import json, os, re, subprocess, sys, html
SCR = os.path.dirname(os.path.abspath(__file__))
RAW, CROPS, REPO = sys.argv[1], sys.argv[2], sys.argv[3]
KEEP = 8
NAMES_RU = {
 "natalie-portman": "Натали Портман", "keira-knightley": "Кира Найтли", "elijah-wood": "Элайджа Вуд",
 "tobey-maguire": "Тоби Магуайр", "amy-adams": "Эми Адамс", "isla-fisher": "Айла Фишер",
 "javier-bardem": "Хавьер Бардем", "jeffrey-dean-morgan": "Джеффри Дин Морган", "margot-robbie": "Марго Робби",
 "samara-weaving": "Самара Уивинг", "jessica-chastain": "Джессика Честейн", "bryce-dallas-howard": "Брайс Даллас Ховард",
 "katy-perry": "Кэти Перри", "zooey-deschanel": "Зоуи Дешанель", "jeremy-renner": "Джереми Реннер",
 "nathan-fillion": "Нейтан Филлион", "kurt-russell": "Курт Рассел", "jeff-bridges": "Джефф Бриджес",
 "salma-hayek": "Сальма Хайек", "penelope-cruz": "Пенелопа Крус", "matt-damon": "Мэтт Дэймон",
 "mark-wahlberg": "Марк Уолберг", "henry-cavill": "Генри Кавилл", "matt-bomer": "Мэтт Бомер",
 "will-ferrell": "Уилл Феррелл", "chad-smith": "Чэд Смит", "zoe-saldana": "Зои Салдана", "thandiwe-newton": "Тэнди Ньютон", "daniel-radcliffe": "Дэниел Рэдклифф",
}
PAIRS = [
 ("natalie-portman", "keira-knightley", "Найтли играла двойника-приманку королевы Амидалы — то есть Портман — в «Звёздных войнах: Эпизод I». Их там не различила даже мама Киры."),
 ("elijah-wood", "tobey-maguire", "Тоби Магуайр признался, что однажды расписался за Элайджу Вуда — не хотел расстраивать фанатку, которая приняла его за Фродо."),
 ("elijah-wood", "daniel-radcliffe", "Рэдклифф уверяет, что вживую они совсем не похожи. Карточки с ним не согласны."),
 ("amy-adams", "isla-fisher", "Айла Фишер как-то вклеила лицо Эми Адамс в семейную рождественскую открытку. А Леди Гага приняла её за Адамс на вечеринке «Оскара»."),
 ("javier-bardem", "jeffrey-dean-morgan", "Когда вышли «Анатомия страсти» и «Старикам тут не место», многие были уверены, что это один и тот же актёр."),
 ("margot-robbie", "samara-weaving", "После трейлера «Я иду искать» половина интернета спрашивала: «Подождите, это не Марго Робби?»"),
 ("jessica-chastain", "bryce-dallas-howard", "Говорят, Честейн иногда просто подыгрывает фанатам, которые принимают её за Ховард."),
 ("katy-perry", "zooey-deschanel", "Их так часто путают, что это стало мемом ещё в эпоху Tumblr."),
 ("jeremy-renner", "nathan-fillion", "В 2014 году Филлион сам оценил своих двойников — и Реннера счёл самым похожим."),
 ("kurt-russell", "jeff-bridges", "В молодости их почти не путали. С возрастом и седой бородой — постоянно."),
 ("salma-hayek", "penelope-cruz", "Они давние подруги и даже сыграли вместе в «Бандитках» (2006)."),
 ("matt-damon", "mark-wahlberg", "Оба снимались в «Отступниках» Скорсезе — и это только добавило путаницы."),
 ("henry-cavill", "matt-bomer", "Бомер должен был сыграть Супермена в фильме, который так и не сняли. Им в итоге стал Кавилл."),
 ("will-ferrell", "chad-smith", "Уилл Феррелл и барабанщик Red Hot Chili Peppers устроили барабанную дуэль у Джимми Фэллона, чтобы выяснить, кто есть кто."),
 ("zoe-saldana", "thandiwe-newton", "Ещё одна пара, которую регулярно путают на красных дорожках."),
]
manifest = {}
for rd in RAW.split(","):
    for slug, meta in json.load(open(os.path.join(rd, "manifest.json"))).items():
        meta["dir"] = os.path.join(rd, slug)
        manifest[slug] = meta

BLACK = set(json.load(open(os.path.join(SCR, "blacklist.json"))))

def stem(r):
    return re.sub(r"\s*\((cropped|crop)\)|[-_ ]?(cropped|crop|edit\d*)", "", r["title"].lower()).rsplit(".", 1)[0]

def cdist(a, b):
    return (sum((x - y) ** 2 for x, y in zip(a["col"], b["col"])) / 48) ** 0.5

def ham(a, b): return bin(int(a, 16) ^ int(b, 16)).count("1")

stars, credits, report = {}, [], []
for slug, meta in manifest.items():
    out = subprocess.run([os.path.join(SCR, "facecrop"), meta["dir"], os.path.join(CROPS, slug)],
                         capture_output=True, text=True).stdout
    bysrc = {f["file"]: f for f in meta["files"]}
    rows = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    for r in rows: r["title"] = bysrc[r["src"]]["title"]
    rows = [r for r in rows if r["quality"] >= 0.25 and bysrc[r["src"]]["title"] not in BLACK]
    rows.sort(key=lambda r: -r["quality"])
    # greedy: best quality first, but keep shots from the same event (similar colours) apart
    chosen = []
    for thr, cap in [(45, KEEP), (38, 6), (32, 6)]:
        for r in rows:
            if len(chosen) >= cap:
                break
            if r in chosen or any(stem(r) == stem(c) or ham(r["hash"], c["hash"]) < 16 or cdist(r, c) < thr for c in chosen):
                continue
            chosen.append(r)
    dst = os.path.join(REPO, "img", slug)
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(dst): os.remove(os.path.join(dst, f))
    photos = []
    for n, r in enumerate(chosen, 1):
        rel = f"img/{slug}/{n:02d}.webp"
        subprocess.run(["cwebp", "-quiet", "-q", "72", "-m", "6", "-resize", "360", "360",
                        os.path.join(CROPS, slug, r["file"]), "-o", os.path.join(REPO, rel)], check=True)
        photos.append(rel)
        src = bysrc[r["src"]]
        credits.append({"img": rel, "star": slug, "title": src["title"], "page": src["page"],
                        "author": src["artist"] or "неизвестен", "license": src["license"] or "см. страницу файла"})
    stars[slug] = {"name": NAMES_RU[slug], "photos": photos}
    report.append(f"{slug}: candidates={len(meta['files'])} faces_ok={len(rows)} kept={len(photos)}")

MIN = 4
pairs = [{"id": f"{a}--{b}", "a": a, "b": b, "fact": fact} for a, b, fact in PAIRS
         if len(stars.get(a, {}).get("photos", [])) >= MIN and len(stars.get(b, {}).get("photos", [])) >= MIN]
used = {p["a"] for p in pairs} | {p["b"] for p in pairs}
stars = {k: v for k, v in stars.items() if k in used}
credits = [c for c in credits if c["star"] in used]
import shutil
for d in os.listdir(os.path.join(REPO, "img")):
    if os.path.isdir(os.path.join(REPO, "img", d)) and d not in used:
        shutil.rmtree(os.path.join(REPO, "img", d))

with open(os.path.join(REPO, "js", "data.js"), "w") as f:
    f.write("// Сгенерировано tools/build.py — фото с Wikimedia Commons, см. credits.html\n")
    f.write("window.STARS = " + json.dumps(stars, ensure_ascii=False, indent=1) + ";\n")
    f.write("window.PAIRS = " + json.dumps(pairs, ensure_ascii=False, indent=1) + ";\n")
json.dump(credits, open(os.path.join(REPO, "img", "credits.json"), "w"), ensure_ascii=False, indent=1)

rows = []
for c in credits:
    e = {k: html.escape(str(v)) for k, v in c.items()}
    rows.append(f'<tr><td><img src="{e["img"]}" alt="" loading="lazy"></td><td>{html.escape(stars[c["star"]]["name"])}</td>'
                f'<td><a href="{e["page"]}" target="_blank" rel="noopener">{e["title"][5:]}</a></td><td>{e["author"]}</td><td>{e["license"]}</td></tr>')
page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Двойники — авторы фото</title><link rel="stylesheet" href="css/style.css"><style>
table{{width:100%;border-collapse:collapse;font-size:13px}}td{{border-bottom:1px solid var(--line);padding:6px;vertical-align:middle;word-break:break-word}}
td img{{width:56px;height:56px;object-fit:cover;border-radius:8px;display:block}}</style></head><body>
<header class="topbar"><a class="logo" href="index.html" style="text-decoration:none;color:inherit">🎭 Двойники</a></header>
<main><h1>Авторы и лицензии</h1><p class="lead" style="text-align:left;margin-left:0">Все фото взяты с Wikimedia Commons и распространяются по указанным лицензиям.
Изображения обрезаны по лицу и пережаты в WebP; обработанные версии распространяются на тех же условиях, что и оригиналы. Нажмите на название файла, чтобы открыть его страницу с полной информацией.</p>
<table><tbody>{''.join(rows)}</tbody></table></main></body></html>"""
open(os.path.join(REPO, "credits.html"), "w").write(page)
print("\n".join(report))
print("pairs:", [p["id"] for p in pairs])
