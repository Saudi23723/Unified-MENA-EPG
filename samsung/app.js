/* SAUDI.TV for Samsung TVs (Tizen web app). First version: activation by device code (the same admin site as the
   Android app), playlists, Live TV (groups, channels, full screen, CH+/CH-), Movies and Series (groups, posters,
   seasons / episodes, resume). Plain JavaScript, no libraries. Player: Samsung AVPlay. */
(function () {
  "use strict";
  var SITE = "https://saudi1.1saifsaudi.workers.dev";
  var $ = function (id) { return document.getElementById(id); };
  var LS = window.localStorage;
  var K = { LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, OK: 13, BACK: 10009, CHUP: 427, CHDOWN: 428, PLAY: 415, PAUSE: 19, STOP: 413, PP: 10252, FF: 417, RW: 412 };
  var st = { lists: [], pl: null, groups: [], byCat: {}, chans: [], playing: null, kind: "", vodSeries: false, cats: [], items: [], eps: [] };
  var av = window.webapis && window.webapis.avplay;

  function toast(t) { var e = $("toast"); e.textContent = t; e.style.display = "block"; clearTimeout(e._t); e._t = setTimeout(function () { e.style.display = "none"; }, 3000); }
  function get(u) { return fetch(u, { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function code() {
    var c = LS.getItem("code");
    if (!c || c.length !== 8) { c = String(1 + Math.floor(Math.random() * 9)); for (var i = 0; i < 7; i++) c += Math.floor(Math.random() * 10); LS.setItem("code", c); }
    return c;
  }
  function api(action, extra) { var p = st.pl; return p.server + "/player_api.php?username=" + encodeURIComponent(p.user) + "&password=" + encodeURIComponent(p.pass) + "&action=" + action + (extra || ""); }

  // ---------- a focus list: one column or a grid, moved with the remote ----------
  function List(el, cols) { this.el = el; this.cols = cols || 1; this.data = []; this.i = 0; this.render = null; this.rows = 0; }
  List.prototype.set = function (data, render, keep) {
    this.data = data; this.render = render; if (!keep) this.i = 0; this.i = Math.max(0, Math.min(this.i, data.length - 1)); this.draw();
  };
  List.prototype.draw = function () {
    // only what fits is in the page (lists of thousands stay light)
    var per = this.cols === 1 ? 11 : this.cols * 2;
    var first = Math.floor(this.i / per) * per, h = "";
    for (var k = first; k < Math.min(this.data.length, first + per); k++) h += '<div class="it' + (k === this.i && this.focused ? " f" : "") + '">' + this.render(this.data[k], k) + "</div>";
    this.el.innerHTML = h || '<div class="it" style="color:#8b95a9">Nothing here</div>';
  };
  List.prototype.move = function (d) {
    if (!this.data.length) return false;
    var n = this.i + d;
    if (this.cols === 1) n = (n + this.data.length) % this.data.length;   // the ends go round
    if (n < 0 || n >= this.data.length) return false;
    this.i = n; this.draw(); return true;
  };
  List.prototype.focus = function (on) { this.focused = on; this.draw(); };
  List.prototype.cur = function () { return this.data[this.i]; };

  var L = { home: new List($("home"), 5), groups: new List($("groups")), chans: new List($("chans")), cats: new List($("cats")), posters: new List($("posters"), 5), eps: new List($("eps")) };
  var screen = "", focus = null;
  function show(s, f) {
    screen = s; var all = document.querySelectorAll(".screen"); for (var i = 0; i < all.length; i++) all[i].classList.toggle("on", all[i].id === "s-" + s);
    if (f) setFocus(f);
  }
  function setFocus(l) { if (focus) focus.focus(false); focus = l; l.focus(true); }

  // ---------- activation ----------
  function activate() {
    return get(SITE + "/api/device?code=" + code() + "&model=" + encodeURIComponent("Samsung TV")).then(function (o) {
      if (o.status !== "active") {
        $("code").textContent = code().slice(0, 4) + " " + code().slice(4);
        $("setup-st").textContent = o.status === "stopped" ? "This device is stopped. Contact your provider." : o.status === "expired" ? "Your subscription has ended." : "Waiting for activation…";
        show("setup"); setTimeout(activate, 10000); return;
      }
      st.lists = o.playlists && o.playlists.length ? o.playlists : [{ name: "", server: o.server, user: o.user, pass: o.pass }];
      var want = LS.getItem("pl");
      st.pl = st.lists.filter(function (p) { return p.name === want; })[0] || st.lists[0];
      st.name = o.name || "";
      home();
    }).catch(function () { $("code").textContent = code().slice(0, 4) + " " + code().slice(4); $("setup-st").textContent = "No internet connection"; show("setup"); setTimeout(activate, 10000); });
  }

  function home() {
    var who = (st.name || "").split(" ")[0];
    var h = new Date().getHours();
    $("hello").textContent = (h >= 5 && h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening") + (who ? ", " + who : "");
    $("foot").textContent = "Playlist: " + (st.pl.name || "—") + "   ·   Device " + code().slice(0, 4) + " " + code().slice(4);
    var cards = [["Live TV", "All your channels", "live"], ["Movies", "Latest added first", "movies"], ["Series", "Seasons and episodes", "series"]];
    if (st.lists.length > 1) cards.push(["Playlists", st.pl.name, "pl"]);
    cards.push(["Reload", "Get the newest lists", "reload"]);
    L.home.set(cards, function (c) { return '<div class="card" style="height:100%;border:0;background:none;padding:22px">' + esc(c[0]) + "<small>" + esc(c[1]) + "</small></div>"; }, true);
    $("home").className = "grid"; show("home", L.home);
  }
  function homeOk() {
    var c = L.home.cur()[2];
    if (c === "live") openLive();
    else if (c === "movies") openVod(false);
    else if (c === "series") openVod(true);
    else if (c === "reload") { st.groups = []; st.vod = {}; toast("Reloading…"); activate(); }
    else if (c === "pl") { var i = (st.lists.indexOf(st.pl) + 1) % st.lists.length; st.pl = st.lists[i]; LS.setItem("pl", st.pl.name); st.groups = []; st.vod = {}; toast("Playlist: " + st.pl.name); home(); }
  }

  // ---------- Live TV ----------
  function openLive() {
    if (st.groups.length) { showLive(); return; }
    toast("Loading channels…");
    Promise.all([get(api("get_live_categories")), get(api("get_live_streams"))]).then(function (r) {
      var by = {}, groups = [];
      r[0].forEach(function (c) { by[c.category_id] = { id: String(c.category_id), name: c.category_name, ch: [] }; groups.push(by[c.category_id]); });
      r[1].forEach(function (s, k) {
        var g = by[s.category_id]; if (!g) { g = by[s.category_id] = { id: String(s.category_id), name: s.category_name || "Other", ch: [] }; groups.push(g); }
        g.ch.push({ id: s.stream_id, num: s.num || k + 1, name: s.name, logo: s.stream_icon });
      });
      st.groups = groups.filter(function (g) { return g.ch.length; });
      showLive();
    }).catch(function () { toast("Could not load the channels"); });
  }
  function showLive() {
    var last = LS.getItem("group_" + st.pl.name), gi = 0;
    st.groups.forEach(function (g, k) { if (g.id === last) gi = k; });
    L.groups.set(st.groups, function (g) { return esc(g.name) + '<span class="n" style="float:right">' + g.ch.length + "</span>"; }); L.groups.i = gi; L.groups.draw();
    fillChans(); show("live", L.chans);
  }
  function fillChans() { var g = L.groups.cur(); L.chans.set(g ? g.ch : [], function (c) { return '<span class="n">' + c.num + "</span>" + esc(c.name); }); }
  function playLive(c) {
    st.playing = c; st.kind = "live"; LS.setItem("group_" + st.pl.name, L.groups.cur().id);
    play(st.pl.server + "/live/" + encodeURIComponent(st.pl.user) + "/" + encodeURIComponent(st.pl.pass) + "/" + c.id + ".ts", c.num + "   " + c.name, "", 0);
  }
  function zap(d) { if (st.kind !== "live") return; L.chans.move(d); playLive(L.chans.cur()); }

  // ---------- Movies / Series ----------
  function openVod(series) {
    st.vodSeries = series; toast("Loading…");
    get(api(series ? "get_series_categories" : "get_vod_categories")).then(function (cats) {
      st.cats = cats; L.cats.set(cats, function (c) { return esc(c.category_name); });
      show("vod", L.cats); loadCat();
    }).catch(function () { toast("Could not load the groups"); });
  }
  function loadCat() {
    var c = L.cats.cur(); if (!c) return;
    L.posters.set([], function () { return ""; });
    get(api(st.vodSeries ? "get_series" : "get_vod_streams", "&category_id=" + encodeURIComponent(c.category_id))).then(function (l) {
      if (L.cats.cur() !== c) return;
      l.sort(function (a, b) { return (Number(b.added || b.last_modified) || 0) - (Number(a.added || a.last_modified) || 0); });
      L.posters.set(l, function (x) { return '<img src="' + esc(x.stream_icon || x.cover || "") + '" onerror="this.style.visibility=\'hidden\'"><div>' + esc(x.name) + "</div>"; });
    }).catch(function () { toast("Could not load this group"); });
  }
  function openItem(x) {
    if (!st.vodSeries) {
      var key = "m" + x.stream_id;
      play(st.pl.server + "/movie/" + encodeURIComponent(st.pl.user) + "/" + encodeURIComponent(st.pl.pass) + "/" + x.stream_id + "." + (x.container_extension || "mp4"), x.name, key, Number(LS.getItem("pos_" + key)) || 0);
      return;
    }
    toast("Loading episodes…");
    get(api("get_series_info", "&series_id=" + x.series_id)).then(function (o) {
      var eps = [], e = o.episodes || {};
      Object.keys(e).sort(function (a, b) { return a - b; }).forEach(function (s) { (e[s] || []).forEach(function (p) { eps.push({ id: p.id, ext: p.container_extension || "mp4", t: "S" + s + " · E" + p.episode_num + "   " + (p.title || "") }); }); });
      $("eps-t").textContent = x.name; L.eps.set(eps, function (p) { return esc(p.t); }); show("eps", L.eps);
    }).catch(function () { toast("Could not load the episodes"); });
  }
  function playEp(p) { var key = "e" + p.id; st.kind = "vod"; play(st.pl.server + "/series/" + encodeURIComponent(st.pl.user) + "/" + encodeURIComponent(st.pl.pass) + "/" + p.id + "." + p.ext, p.t, key, Number(LS.getItem("pos_" + key)) || 0); }

  // ---------- the player (Samsung AVPlay) ----------
  var back = "", resumeKey = "", osdT = 0;
  function osd(t, sub) { var e = $("osd"); e.innerHTML = esc(t) + (sub ? "<small>" + esc(sub) + "</small>" : ""); e.style.display = "block"; clearTimeout(osdT); osdT = setTimeout(function () { e.style.display = "none"; }, 4000); }
  function play(url, title, key, from) {
    if (!av) { toast("This screen plays only on a Samsung TV"); return; }
    if (screen !== "play") back = screen;
    if (!key) st.kind = "live"; else st.kind = "vod";
    resumeKey = key || "";
    try { av.stop(); av.close(); } catch (e) { }
    try {
      av.open(url);
      av.setDisplayRect(0, 0, 1920, 1080);
      av.setListener({
        onstreamcompleted: function () { if (resumeKey) LS.removeItem("pos_" + resumeKey); stop(); },
        onerror: function () { toast("This cannot be played right now"); if (st.kind !== "live") stop(); },
        oncurrentplaytime: function (t) { if (resumeKey && t > 60000 && t % 10000 < 600) LS.setItem("pos_" + resumeKey, String(t)); }
      });
      av.prepareAsync(function () { if (from > 0) { try { av.seekTo(from); } catch (e) { } } av.play(); }, function () { toast("This cannot be played right now"); });
    } catch (e) { toast("Player error"); return; }
    document.body.classList.add("playing"); show("play"); osd(title, st.kind === "live" ? "CH + / −  ·  OK: channels  ·  Back" : "◀ ▶ 10 s  ·  OK: pause  ·  Back");
  }
  function stop() {
    try { av.stop(); av.close(); } catch (e) { }
    document.body.classList.remove("playing"); $("osd").style.display = "none";
    show(back || "home", back === "live" ? L.chans : back === "vod" ? L.posters : back === "eps" ? L.eps : L.home);
  }
  function seek(ms) { try { if (ms > 0) av.jumpForward(ms); else av.jumpBackward(-ms); osd(ms > 0 ? "▶▶ " + ms / 1000 + " s" : "◀◀ " + -ms / 1000 + " s"); } catch (e) { } }
  function pause() { try { if (av.getState() === "PLAYING") { av.pause(); osd("Paused"); } else { av.play(); osd("Playing"); } } catch (e) { } }

  // ---------- the remote ----------
  document.addEventListener("keydown", function (e) {
    var k = e.keyCode;
    if (screen === "play") {
      if (k === K.BACK || k === K.STOP) stop();
      else if (st.kind === "live") { if (k === K.CHUP || k === K.UP) zap(1); else if (k === K.CHDOWN || k === K.DOWN) zap(-1); else if (k === K.OK) stop(); }
      else { if (k === K.RIGHT || k === K.FF) seek(10000); else if (k === K.LEFT || k === K.RW) seek(-10000); else if (k === K.OK || k === K.PP || k === K.PLAY || k === K.PAUSE) pause(); }
      e.preventDefault(); return;
    }
    if (k === K.BACK) {
      if (screen === "home" || screen === "setup") { try { tizen.application.getCurrentApplication().exit(); } catch (x) { } }
      else if (screen === "eps") show("vod", L.posters); else home();
      e.preventDefault(); return;
    }
    if (screen === "home") { if (k === K.LEFT) L.home.move(-1); else if (k === K.RIGHT) L.home.move(1); else if (k === K.OK) homeOk(); }
    else if (screen === "live") {
      if (focus === L.groups) { if (k === K.UP) { L.groups.move(-1); fillChans(); } else if (k === K.DOWN) { L.groups.move(1); fillChans(); } else if (k === K.RIGHT || k === K.OK) setFocus(L.chans); }
      else { if (k === K.UP) L.chans.move(-1); else if (k === K.DOWN) L.chans.move(1); else if (k === K.LEFT) setFocus(L.groups); else if (k === K.OK && L.chans.cur()) playLive(L.chans.cur()); }
    } else if (screen === "vod") {
      if (focus === L.cats) { if (k === K.UP) { L.cats.move(-1); loadCat(); } else if (k === K.DOWN) { L.cats.move(1); loadCat(); } else if ((k === K.RIGHT || k === K.OK) && L.posters.data.length) setFocus(L.posters); }
      else { if (k === K.UP) L.posters.move(-5); else if (k === K.DOWN) L.posters.move(5); else if (k === K.RIGHT) L.posters.move(1); else if (k === K.LEFT) { if (L.posters.i % 5 === 0) setFocus(L.cats); else L.posters.move(-1); } else if (k === K.OK && L.posters.cur()) openItem(L.posters.cur()); }
    } else if (screen === "eps") { if (k === K.UP) L.eps.move(-1); else if (k === K.DOWN) L.eps.move(1); else if (k === K.OK && L.eps.cur()) playEp(L.eps.cur()); }
    e.preventDefault();
  });
  try { ["ChannelUp", "ChannelDown", "MediaPlay", "MediaPause", "MediaStop", "MediaPlayPause", "MediaFastForward", "MediaRewind"].forEach(function (n) { tizen.tvinputdevice.registerKey(n); }); } catch (e) { }
  document.addEventListener("visibilitychange", function () { if (document.hidden && screen === "play") stop(); });
  activate();
})();
