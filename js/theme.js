/* ============================================================
 * Axiom 超频协议（Overclock Protocol）— 第二形态主题引擎 v2
 * 本次重做（对应用户 7 条验收意见）：
 *   1) 点击瞬间底层即纯黑（cmdOverlay 立即全黑实底，不再透明露底）
 *   2) 切换按钮缩小、低调、fixed 底部居中，转场期间隐藏
 *   3) 删除粒子烟花 → 改为「闪屏错乱」序列（黑白脉冲 + 青绿 glitch 撕裂条）
 *   4) CMD 以红色 [ERR] 报错收尾（超频=危险，呼应鸣潮世界观）
 *   5) 第二形态整体重设计：终端 HUD 状态栏 / LED 灯带 / 噪点 /
 *      切角面板 + L 角标 + 坐标噪声 / CRT 代码区 / 顶部警示条
 * 规则：纯前端、零外部库、只动 transform/opacity/background
 * ============================================================ */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- CMD 引导脚本：前半段正常 → 红色警示条 → 错乱闪屏 → 报错收尾 ---------- */
  var CMD_SCRIPT = [
    { t: 'title', text: 'AXIOM//OVERCLOCK PROTOCOL v2.7.1',            ms: 60 },
    { t: 'copy',  text: '(c) Echo Overclock Terminal — local build',   ms: 40 },
    { t: 'cmd',   text: '> system init',                               ms: 45 },
    { t: 'out',   text: '[ OK ] core bootstrapped 0.42ms',             ms: 38 },
    { t: 'cmd',   text: '> mount modules',                             ms: 45 },
    { t: 'out',   text: '[ OK ] 48/48 modules staged',                 ms: 38 },
    { t: 'cmd',   text: '> load neon-renderer',                        ms: 45 },
    { t: 'out',   text: '[ OK ] shader pipeline ready',                ms: 38 },
    { t: 'cmd',   text: '> calibrate resonance',                       ms: 45 },
    { t: 'out',   text: '[ OK ] resonance locked 2.4GHz',              ms: 38 },
    { t: 'cmd',   text: '> overclock frequency cores',                 ms: 45 },
    { t: 'out',   text: '[ OK ] cores unlocked 8/8',                   ms: 38 },
    { t: 'alert', text: '⚠ OVERCLOCK ALERT — FREQUENCY LIMIT EXCEEDED', ms: 40 },
    { t: 'cmd',   text: '> bypass safety limiter',                     ms: 45 },
    { t: 'err',   text: '[ ERR ] FREQUENCY INSTABILITY DETECTED',      ms: 40 },
    { t: 'err',   text: '[ ERR ] core temp critical — overclock fail', ms: 40 },
    { t: 'sys',   text: '[ SYS ] degraded mode · UI 82% · 6.1GB',      ms: 38 }
  ];

  /* ---------- 状态 ---------- */
  var state = {
    active: false,
    entering: false,
    exiting: false,
    tier: 0,
    lowMem: false,
    warnedOnce: !!sessionStorage.getItem('axiom_neon_warned')
  };

  /* ---------- 内存探测 ---------- */
  function probeMemory() {
    var dm = navigator.deviceMemory;
    state.lowMem = (typeof dm === 'number' && dm < 8);
    var q = new URLSearchParams(location.search);
    if (q.get('lowmem') === '1') state.lowMem = true;
    return state.lowMem;
  }

  /* ---------- 性能分层 T0–T3：ema 采样、降 3s / 升 5s 迟滞 ---------- */
  var perf = { ema: 0, bad: 0, good: 0, lastT: 0, fps: 60, load: 8 };
  function perfSample() {
    var now = performance.now();
    if (!perf.lastT) { perf.lastT = now; return; }
    var dt = now - perf.lastT;
    perf.lastT = now;
    perf.ema = perf.ema ? perf.ema * 0.92 + dt * 0.08 : dt;
    if (perf.ema > 2) { perf.fps = Math.round(1000 / perf.ema); }
    perf.load = Math.min(100, Math.max(3, Math.round(perf.ema / 16.7 * 100)));
    if (perf.ema > 33) { perf.bad += dt; perf.good = 0; }
    else { perf.good += dt; perf.bad = 0; }
    if (perf.bad >= 3000 && state.tier < 3) { state.tier++; perf.bad = 0; applyTier(); }
    else if (perf.good >= 5000 && state.tier > 0) { state.tier--; perf.good = 0; applyTier(); }
    if (state.active) updateHud();
  }
  function applyTier() {
    if (!rain.running) return;
    rain.cfg.density = [1, 0.7, 0.4, 0.25][state.tier];
    rain.cfg.dpr = state.tier >= 2 ? 1 : rain.baseDpr;
    rain.cfg.speed = [1, 1, 0.8, 0.6][state.tier];
    rain.resize(true);
  }

  /* ---------- HUD 读数（第二形态顶栏） ---------- */
  function updateHud() {
    var f = $('hudFps'), l = $('hudLoad');
    if (f) f.textContent = perf.fps;
    if (l) l.textContent = perf.load + '%';
  }

  /* ---------- 矩阵雨：二进制 0/1，按 tier 降级 ---------- */
  var rain = {
    canvas: null, ctx: null, W: 0, H: 0,
    drops: [], cols: 0, fontSize: 16,
    running: false, paused: false, rafId: 0, lastT: 0, acc: 0,
    baseDpr: Math.min(window.devicePixelRatio || 1, 2),
    cfg: { density: 1, dpr: 2, speed: 1 },
    init: function () {
      this.canvas = $('cyberRain');
      if (!this.canvas) return;
      this.ctx = this.canvas.getContext('2d');
      var self = this;
      window.addEventListener('resize', function () { if (self.running) self.resize(true); });
    },
    resize: function (force) {
      if (!force && this.W === window.innerWidth && this.H === window.innerHeight) return;
      this.W = window.innerWidth; this.H = window.innerHeight;
      var dpr = this.cfg.dpr || this.baseDpr;
      this.canvas.width = Math.round(this.W * dpr);
      this.canvas.height = Math.round(this.H * dpr);
      this.canvas.style.width = this.W + 'px';
      this.canvas.style.height = this.H + 'px';
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.fontSize = Math.max(13, Math.min(18, Math.round(this.H / 56)));
      this.cols = Math.max(8, Math.ceil(this.W / (this.fontSize * 0.85) * this.cfg.density));
      this.drops = [];
      for (var i = 0; i < this.cols; i++) this.drops.push(Math.random() * -60);
    },
    frame: function (t) {
      if (!rain.paused) {
        rain.acc += t - rain.lastT;
        rain.lastT = t;
        if (rain.acc >= 16.7) { rain.acc = 0; rain.draw(); perfSample(); }
      }
      if (rain.running) rain.rafId = requestAnimationFrame(rain.frame);
    },
    draw: function () {
      var ctx = this.ctx, W = this.W, H = this.H;
      ctx.fillStyle = this.cfg.speed < 0.7 ? 'rgba(5,7,15,0.6)' : 'rgba(5,7,15,0.18)';
      ctx.fillRect(0, 0, W, H);
      ctx.font = this.fontSize + 'px "Share Tech Mono", "Cascadia Code", monospace';
      for (var i = 0; i < this.cols; i++) {
        var x = i * this.fontSize * 0.85;
        var y = this.drops[i] * this.fontSize;
        var bright = Math.random() < 0.12;
        ctx.fillStyle = bright ? 'rgba(0,255,136,0.9)' : 'rgba(0,212,255,0.34)';
        ctx.fillText(Math.random() > 0.5 ? '1' : '0', x, y);
        if (y > H + 40 && Math.random() > 0.976) this.drops[i] = Math.random() * -40;
        this.drops[i] += this.cfg.speed;
      }
    },
    start: function () {
      if (!this.canvas || this.running) return;
      this.running = true; this.paused = false;
      this.resize(true);
      this.lastT = performance.now();
      this.rafId = requestAnimationFrame(this.frame);
    },
    stop: function () {
      this.running = false; this.paused = false;
      if (this.rafId) cancelAnimationFrame(this.rafId);
      this.rafId = 0;
      if (this.ctx) this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    },
    pause: function () { this.paused = true; if (this.rafId) cancelAnimationFrame(this.rafId); },
    resume: function () { this.paused = false; this.lastT = performance.now(); this.rafId = requestAnimationFrame(this.frame); }
  };
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (rain.running) rain.pause(); }
    else if (state.active && !state.exiting) rain.resume();
  });

  /* ---------- 闪屏错乱：黑白脉冲 + 青绿 glitch 撕裂条（替代粒子烟花） ---------- */
  function glitchBars(n, duration, red) {
    var box = $('glitchBars');
    if (!box) return;
    box.innerHTML = '';
    var colors = red ? ['255,77,94', '0,255,136'] : ['0,212,255', '0,255,136'];
    for (var i = 0; i < n; i++) {
      var bar = document.createElement('div');
      bar.className = 'glitch-bar';
      var h = 3 + Math.random() * 14;
      var top = Math.random() * 100;
      var drift = (Math.random() * 60 - 30).toFixed(0);
      var c = colors[Math.floor(Math.random() * colors.length)];
      bar.style.cssText =
        'top:' + top + '%;height:' + h + 'px;' +
        'background:rgba(' + c + ',0.55);' +
        'transform:translateX(' + drift + 'px);' +
        'animation-duration:' + (0.18 + Math.random() * 0.2).toFixed(2) + 's;' +
        'animation-delay:' + (Math.random() * 0.12).toFixed(2) + 's;';
      box.appendChild(bar);
    }
    box.classList.add('on');
    setTimeout(function () { box.classList.remove('on'); box.innerHTML = ''; }, duration);
  }
  /* 全屏黑白脉冲闪屏 */
  function flash(ms, rgba) {
    var f = document.createElement('div');
    f.className = 'overlay-flash';
    f.style.background = rgba || 'rgba(209,247,255,0.25)';
    document.body.appendChild(f);
    setTimeout(function () { f.parentNode && f.parentNode.removeChild(f); }, ms);
  }

  /* ---------- CMD 引导转场 ---------- */
  var cmd = {
    overlay: null, linesEl: null, caret: null, skipFlag: false,
    init: function () {
      this.overlay = $('cmdOverlay');
      this.linesEl = $('cmdLines');
      this.caret = $('cmdCaret');
      var self = this;
      this.overlay.addEventListener('click', function () { self.skip(); });
    },
    addLine: function (line, ms) {
      var div = document.createElement('div');
      var span = document.createElement('span');
      span.textContent = line.text;
      div.appendChild(span);
      div.className = 'cmd-line';
      if (line.t === 'title') div.classList.add('cmd-title');
      else if (line.t === 'copy') div.classList.add('cmd-copy');
      else if (line.t === 'cmd') span.classList.add('cmd-grad');
      else if (line.t === 'out') div.classList.add('cmd-out');
      else if (line.t === 'alert') { div.classList.add('cmd-alert', 'typed'); this.linesEl.appendChild(div); return Promise.resolve(ms); }
      else if (line.t === 'err') div.classList.add('cmd-err');
      else if (line.t === 'sys') div.classList.add('cmd-sys');
      if (reduceMotion) { div.classList.add('typed'); this.linesEl.appendChild(div); return Promise.resolve(ms); }
      this.linesEl.appendChild(div);
      var self = this;
      return new Promise(function (resolve) {
        var i = 0, txt = line.text, step = (line.ms || 45) * 0.4;
        (function typeChar() {
          i++;
          span.textContent = txt.slice(0, i);
          if (i < txt.length) setTimeout(typeChar, step);
          else { div.classList.add('typed'); resolve(); }
        })();
      });
    },
    run: function () {
      var self = this, chain = Promise.resolve();
      this.skipFlag = false;
      this.linesEl.innerHTML = '';
      this.caret.style.display = 'none';
      this.overlay.classList.remove('glow', 'exiting');
      // 关键修复：立即全黑实底（CSS 用字面色值，不依赖主题变量）
      this.overlay.classList.add('on');
      this.overlay.style.visibility = 'visible';
      // T0 简短通电：一次白闪（瞬间全黑 → 白脉冲）
      chain = chain.then(function () { flash(80); return new Promise(function (r) { setTimeout(r, 120); }); });
      // T1–T6 前半段：正常 CMD 打字流（一切 [ OK ]）
      CMD_SCRIPT.forEach(function (line) {
        chain = chain.then(function () { return self.addLine(line, line.ms); });
        if (line.t === 'cmd' || line.t === 'err') chain = chain.then(function () { return new Promise(function (r) { setTimeout(r, 60); }); });
        // 红色警示条闪出后 → 白屏乱闪 + glitch 错乱（后半段错乱开始）
        if (line.t === 'alert') {
          chain = chain.then(function () { return new Promise(function (r) { setTimeout(r, 680); }); });
          chain = chain.then(function () { flash(90); return new Promise(function (r) { setTimeout(r, 80); }); });
          chain = chain.then(function () { glitchBars(14, 380, true); flash(70, 'rgba(255,77,94,0.3)'); return new Promise(function (r) { setTimeout(r, 380); }); });
          chain = chain.then(function () { flash(90, 'rgba(209,247,255,0.35)'); return new Promise(function (r) { setTimeout(r, 100); }); });
          chain = chain.then(function () { glitchBars(10, 300, false); return new Promise(function (r) { setTimeout(r, 320); }); });
        }
      });
      // 回车模拟：扫描线 + 光标急闪
      chain = chain.then(function () {
        var sl = document.createElement('div');
        sl.className = 'cmd-scanline';
        self.linesEl.appendChild(sl);
        return new Promise(function (r) { setTimeout(r, 480); });
      });
      chain = chain.then(function () {
        self.caret.style.display = 'inline-block';
        self.caret.classList.add('fast');
        return new Promise(function (r) { setTimeout(r, 420); });
      });
      // 收幕：级联进入第二形态
      chain = chain.then(function () { return self.finishEnter(); });
      chain.catch(function () {});
      return chain;
    },
    finishEnter: function () {
      this.overlay.classList.remove('on', 'glow');
      this.caret.classList.remove('fast');
      this.caret.style.display = 'none';
      document.documentElement.setAttribute('data-theme', 'overclock');
      rain.start();
      state.active = true;
      state.entering = false;
      var btn = $('swapBtn');
      if (btn) {
        btn.classList.remove('m-open', 'm-out', 'm-hide');
        btn.classList.add('m-oc');
        var lbl = btn.querySelector('.swap-btn__label');
        if (lbl) lbl.textContent = '返回原版';
      }
      var self = this;
      setTimeout(function () { self.overlay.style.visibility = 'hidden'; }, 320);
    },
    skip: function () {
      if (!state.entering) return;
      this.finishEnter();
    }
  };

  /* ---------- 安全警告弹窗（每次进入超频协议都显示：光敏 + 内存） ---------- */
  var warn = {
    el: null,
    init: function () {
      this.el = $('memWarn');
      if (!this.el) return;
      var self = this;
      $('warnOk').addEventListener('click', function () { self.close(true); });
      $('warnCancel').addEventListener('click', function () { self.close(false); });
      this.el.addEventListener('click', function (e) { if (e.target === self.el) self.close(false); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !self.el.hidden) self.close(false); });
    },
    show: function () {
      // 内存段：仅低内存时显示
      var mr = $('warnMemRow'), mb = $('warnMem');
      if (mr && mb) { mr.hidden = !state.lowMem; mb.hidden = !state.lowMem; }
      if (this.el) this.el.hidden = false;
      var ok = $('warnOk');
      if (ok) ok.focus();
    },
    close: function (ok) {
      if (this.el) this.el.hidden = true;
      if (ok) enterNeon();
    }
  };

  /* ---------- 入场编排：纯黑瞬现 → 机械展开 → CMD 转场 ---------- */
  function enterNeon() {
    if (state.entering || state.active || state.exiting) return;
    state.entering = true;
    var btn = $('swapBtn');
    // 1) 立即把主题切到 overclock，让背景/覆盖层全部生效
    document.documentElement.setAttribute('data-theme', 'overclock');
    // 2) 按钮立刻隐藏（转场期间不挡视线、不干扰）
    btn.classList.add('m-hide');
    // 3) 覆盖层立即全黑（CSS 字面实底），原版内容瞬间被吞掉
    var ov = $('cmdOverlay');
    ov.classList.add('on');
    ov.style.visibility = 'visible';
    // 4) 机械展开动画与闪屏错乱并行
    btn.classList.add('m-open');
    setTimeout(function () { cmd.run(); }, 200);
  }

  /* ---------- 退场 X1–X5（≈1.4s） ---------- */
  function exitNeon() {
    if (!state.active || state.entering || state.exiting) return;
    state.exiting = true;
    var btn = $('swapBtn');
    var overlay = $('cmdOverlay');
    btn.classList.remove('m-oc');
    var lbl = btn.querySelector('.swap-btn__label');
    if (lbl) lbl.textContent = '超频协议';
    btn.classList.add('m-hide');
    rain.cfg.speed = 3;
    setTimeout(function () {
      overlay.classList.add('on', 'exiting');
      overlay.style.visibility = 'visible';
      glitchBars(8, 220, false);
      setTimeout(function () {
        rain.stop();
        document.documentElement.removeAttribute('data-theme');
        state.active = false;
        setTimeout(function () {
          overlay.classList.remove('on', 'exiting');
          overlay.style.visibility = 'hidden';
          rain.cfg.speed = 1;
          btn.classList.remove('m-open', 'm-down', 'm-hide');
          state.exiting = false;
        }, 460);
      }, 560);
    }, 340);
  }

  /* ---------- 入口 ---------- */
  function init() {
    probeMemory();
    rain.init();
    cmd.init();
    warn.init();
    var btn = $('swapBtn');
    var autoOc = new URLSearchParams(location.search).get('oc') === '1';
    if (autoOc) {
      state.active = true;
      document.documentElement.setAttribute('data-theme', 'overclock');
      rain.start();
      var lbl = btn.querySelector('.swap-btn__label');
      if (lbl) lbl.textContent = '返回原版';
      btn.classList.add('m-oc');
    }
    btn.addEventListener('click', function () {
      if (state.entering || state.exiting) return;
      if (state.active) { exitNeon(); return; }
      warn.show();
    });
    document.addEventListener('keydown', function (e) {
      if (e.ctrlKey && e.shiftKey && (e.key === 'T' || e.key === 't')) {
        e.preventDefault();
        if (state.entering || state.exiting) return;
        if (state.active) exitNeon();
        else warn.show();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
