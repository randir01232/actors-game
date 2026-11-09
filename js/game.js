(() => {
  "use strict";

  const STARS = window.STARS;
  // Показываем только пары, для которых хватает фото на хардкор
  const PAIRS = window.PAIRS.filter(p => STARS[p.a] && STARS[p.b]);

  const LEVELS = {
    easy: { perStar: 3 },   // 12 карт
    normal: { perStar: 4 }, // 16 карт
    hard: { perStar: 6 },   // 24 карты (меньше, если у звезды мало фото)
  };

  const MISS_JOKES = [
    "Мимо! Хотя похожи же…",
    "Да это же одно лицо! А, нет.",
    "Близко. Но нет.",
    "Голливуд специально так делает.",
    "Кастинг-директор тоже ошибся бы.",
    "Не та. Или не тот. Или та, но другое фото.",
    "Это двойник. Или оригинал. Кто знает.",
    "Почти! Отличаются ровно на одну фотографию.",
  ];
  const HIT_JOKES = ["Есть пара!", "Глаз-алмаз!", "Вот это память!", "Ни капли сомнений!", "Пара найдена!"];
  const QUIZ_RIGHT = ["Точно! Вы бы прошли фейс-контроль.", "Верно! Редкий талант.", "Да! Вы явно смотрели титры."];
  const QUIZ_WRONG = ["Не-а. Классика жанра.", "Ошибка, но вас никто не осудит.", "Мимо. Даже их мамы иногда путают."];

  const $ = id => document.getElementById(id);
  const rand = arr => arr[Math.floor(Math.random() * arr.length)];
  const shuffle = arr => {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  };
  const fmtTime = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* приватный режим */ } },
  };

  const settings = {
    level: store.get("dv:level") || "normal",
    quiz: store.get("dv:quiz") ?? true,
  };

  // ---------- Стартовый экран ----------
  function dailyIndex() {
    const d = new Date();
    const key = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    let h = key;
    h = ((h >>> 16) ^ h) * 0x45d9f3b; h = ((h >>> 16) ^ h) * 0x45d9f3b; h = (h >>> 16) ^ h;
    return Math.abs(h) % PAIRS.length;
  }

  function faces(p) {
    return `<span class="faces"><img src="${STARS[p.a].photos[0]}" alt="" loading="lazy"><img src="${STARS[p.b].photos[0]}" alt="" loading="lazy"></span>`;
  }
  function names(p) {
    return `${STARS[p.a].name} <span class="vs">и</span> ${STARS[p.b].name}`;
  }
  function bestKey(p, level) { return `dv:best:${p.id}:${level}`; }

  function renderStart() {
    document.querySelectorAll("#levelSeg button").forEach(b =>
      b.setAttribute("aria-checked", String(b.dataset.level === settings.level)));
    $("quizToggle").checked = settings.quiz;

    const daily = PAIRS[dailyIndex()];
    $("daily").innerHTML = `
      ${faces(daily)}
      <div>
        <div class="tag">Пара дня</div>
        <div class="names">${names(daily)}</div>
        <button type="button" class="btn primary" data-pair="${daily.id}">Играть</button>
      </div>`;

    $("pairsList").innerHTML = PAIRS.map(p => {
      const best = store.get(bestKey(p, settings.level));
      return `<button type="button" class="pair-tile" data-pair="${p.id}">
        ${faces(p)}
        <span class="names">${names(p)}${best ? `<span class="best">Рекорд: ${best.score} ⭐</span>` : ""}</span>
      </button>`;
    }).join("");
  }

  function show(screen) {
    for (const id of ["startScreen", "gameScreen", "endScreen"]) $(id).hidden = id !== screen;
    $("hud").hidden = screen !== "gameScreen";
    window.scrollTo({ top: 0 });
  }

  // ---------- Игра ----------
  let game = null;

  function startGame(pairId) {
    const pair = PAIRS.find(p => p.id === pairId);
    const lvl = LEVELS[settings.level];
    const perStar = Math.min(lvl.perStar, STARS[pair.a].photos.length, STARS[pair.b].photos.length);
    const pick = slug => shuffle(STARS[slug].photos).slice(0, perStar).map(src => ({ src, star: slug }));
    const photos = [...pick(pair.a), ...pick(pair.b)];
    const deck = shuffle(photos.flatMap((ph, i) => [{ ...ph, key: i }, { ...ph, key: i }]));

    clearInterval(game?.timerId);
    game = {
      pair, deck, photos,
      level: settings.level,
      quiz: settings.quiz,
      open: [], lock: false,
      moves: 0, misses: 0, found: 0, quizRight: 0, quizWrong: 0, score: 0,
      started: null, seconds: 0, timerId: null,
    };

    $("versus").innerHTML = names(pair);
    const board = $("board");
    board.style.setProperty("--cols", { 12: 4, 16: 4, 20: 5, 24: 6 }[deck.length] || 4);
    board.dataset.cards = deck.length;
    board.innerHTML = deck.map((c, i) => `
      <button type="button" class="card" data-i="${i}" aria-label="Карта ${i + 1}">
        <span class="face back"></span>
        <span class="face front"><img src="${c.src}" alt="" draggable="false"></span>
      </button>`).join("");
    updateHud();
    toast("Найди одинаковые фото. Удачи — она понадобится.");
    show("gameScreen");
  }

  function updateHud() {
    $("moves").textContent = game.moves;
    $("timer").textContent = fmtTime(game.seconds);
    $("score").textContent = game.score;
  }

  let toastTimer;
  function toast(msg, bad = false) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.toggle("bad", bad);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
  }

  function onCardClick(el) {
    if (!game || game.lock) return;
    const i = Number(el.dataset.i);
    if (el.classList.contains("flipped") || el.classList.contains("gone")) return;

    if (!game.started) {
      game.started = Date.now();
      game.timerId = setInterval(() => {
        game.seconds = Math.floor((Date.now() - game.started) / 1000);
        updateHud();
      }, 500);
    }

    el.classList.add("flipped");
    game.open.push({ i, el });
    if (game.open.length < 2) return;

    game.moves++;
    game.lock = true;
    const [a, b] = game.open;
    const ca = game.deck[a.i], cb = game.deck[b.i];

    if (ca.key === cb.key) {
      game.found++;
      game.score += 100;
      a.el.classList.add("matched"); b.el.classList.add("matched");
      toast(rand(HIT_JOKES));
      updateHud();
      const finish = () => {
        setTimeout(() => {
          a.el.classList.add("gone"); b.el.classList.add("gone");
          game.open = []; game.lock = false;
          if (game.found === game.photos.length) setTimeout(endGame, 450);
        }, 350);
      };
      if (game.quiz) setTimeout(() => askWho(ca, finish), 450);
      else setTimeout(finish, 400);
    } else {
      game.misses++;
      game.score = Math.max(0, game.score - 10);
      a.el.classList.add("miss"); b.el.classList.add("miss");
      toast(rand(MISS_JOKES), true);
      updateHud();
      setTimeout(() => {
        a.el.classList.remove("flipped", "miss"); b.el.classList.remove("flipped", "miss");
        game.open = []; game.lock = false;
      }, 1100);
    }
  }

  // ---------- «Кто это?» ----------
  function askWho(card, done) {
    const { pair } = game;
    $("quizImg").src = card.src;
    $("quizFeedback").textContent = "";
    const opts = shuffle([pair.a, pair.b]);
    const box = $("quizOptions");
    box.innerHTML = opts.map(s => `<button type="button" data-star="${s}">${STARS[s].name}</button>`).join("");
    $("quiz").hidden = false;
    box.querySelector("button").focus();

    box.onclick = e => {
      const btn = e.target.closest("button");
      if (!btn || btn.disabled) return;
      const right = btn.dataset.star === card.star;
      box.querySelectorAll("button").forEach(b => {
        b.disabled = true;
        if (b.dataset.star === card.star) b.classList.add("right");
        else if (b === btn) b.classList.add("wrong");
      });
      if (right) { game.quizRight++; game.score += 50; }
      else game.quizWrong++;
      $("quizFeedback").textContent = right ? rand(QUIZ_RIGHT) : `${rand(QUIZ_WRONG)} Это ${STARS[card.star].name}.`;
      updateHud();
      setTimeout(() => { $("quiz").hidden = true; box.onclick = null; done(); }, right ? 900 : 1700);
    };
  }

  // ---------- Итоги ----------
  function endGame() {
    clearInterval(game.timerId);
    const g = game;
    const timeBonus = Math.max(0, 300 - g.seconds) * 2;
    g.score += timeBonus;
    const total = g.photos.length;
    const key = bestKey(g.pair, g.level);
    const prev = store.get(key);
    const isBest = !prev || g.score > prev.score;
    if (isBest) store.set(key, { score: g.score, moves: g.moves, seconds: g.seconds });

    const perfect = g.misses === 0;
    const ratio = g.moves / total;
    $("endTitle").textContent = perfect ? "Ни одной ошибки?!" : ratio < 1.8 ? "Отличная память!" : ratio < 2.6 ? "Неплохо!" : "Зато честно";
    let verdict;
    if (!g.quiz) verdict = `Вы ни разу не узнали, кто где. И, возможно, это к лучшему.`;
    else if (g.quizWrong === 0) verdict = `Вы ни разу не перепутали ${STARS[g.pair.a].name} и ${STARS[g.pair.b].name}. Подозрительно.`;
    else if (g.quizWrong >= g.quizRight) verdict = `Вы перепутали их ${g.quizWrong} раз(а) из ${total}. Голливуд вас понимает.`;
    else verdict = `Перепутали ${g.quizWrong} раз(а) из ${total}. Почти эксперт по двойникам.`;
    $("endVerdict").textContent = verdict;

    const stat = (v, l, cls = "") => `<div class="stat ${cls}"><b>${v}</b><span>${l}</span></div>`;
    $("endStats").innerHTML = [
      stat(g.score, isBest ? "очков · рекорд!" : `очков · рекорд ${prev.score}`, isBest ? "best" : ""),
      stat(g.moves, "ходов"),
      stat(fmtTime(g.seconds), "время"),
      stat(g.misses, "промахов"),
      g.quiz ? stat(`${g.quizRight}/${total}`, "угадано лиц") : "",
    ].join("");

    const col = slug => `<div class="col"><h4>${STARS[slug].name}</h4><div class="grid">${
      g.photos.filter(p => p.star === slug).map(p => `<img src="${p.src}" alt="${STARS[slug].name}" loading="lazy">`).join("")
    }</div></div>`;
    $("reveal").innerHTML = col(g.pair.a) + col(g.pair.b) + (g.pair.fact ? `<p class="fact">💡 ${g.pair.fact}</p>` : "");
    show("endScreen");
  }

  // ---------- События ----------
  $("levelSeg").addEventListener("click", e => {
    const b = e.target.closest("button[data-level]");
    if (!b) return;
    settings.level = b.dataset.level;
    store.set("dv:level", settings.level);
    renderStart();
  });
  $("quizToggle").addEventListener("change", e => {
    settings.quiz = e.target.checked;
    store.set("dv:quiz", settings.quiz);
  });
  document.addEventListener("click", e => {
    const p = e.target.closest("[data-pair]");
    if (p) startGame(p.dataset.pair);
  });
  $("board").addEventListener("click", e => {
    const c = e.target.closest(".card");
    if (c) onCardClick(c);
  });
  $("homeBtn").addEventListener("click", () => {
    clearInterval(game?.timerId);
    $("quiz").hidden = true;
    renderStart(); show("startScreen");
  });
  $("againBtn").addEventListener("click", () => startGame(game.pair.id));
  $("otherBtn").addEventListener("click", () => { renderStart(); show("startScreen"); });

  renderStart();
})();
