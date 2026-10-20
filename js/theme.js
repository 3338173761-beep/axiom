/* ============================================================
 * Axiom 超频协议（Overclock Protocol）— 第二形态主题引擎
 * 实现：性能分层 T0–T3 / 内存探测 / M0–M3 机械展开
 *       / T0–T7 CMD 引导转场 / enableNeon / 退场 X1–X5
 * 规则：纯前端、零外部库、只动 transform/opacity/background
 * ============================================================ */
(function () {
  'use strict';

  /* ---------- 工具 ---------- */
  function $(id) { return document.getElementById(id); }
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 常量：CMD 引导脚本（12 行 + 欢迎语） ---------- */
  var CMD_SCRIPT = [
    { t: 'title',   text: 'AXIOM//OVERCLOCK PROTOCOL v2.7.1', ms: 50 },
    { t: 'cmd',     text: '> system init',                     ms: 45 },
    { t: 'out',     text: '[ OK ] core bootstrapped',          ms: 38 },
    { t: 'cmd',     text: '> mount modules',                   ms: 45 },
    { t: 'out',     text: '[ OK ] module tree mounted 48/48',  ms: 38 },
    { t: 'cmd',     text: '> load neon-renderer',              ms: 45 },
    { t: 'out',     text: '[ OK ] shader pipeline ready',      ms: 38 },
    { t: 'cmd',     text: '> calibrate resonance',             ms: 45 },
    { t: 'out',     text: '[ OK ] resonance locked 2.4GHz',    ms: 38 },
    { t: 'cmd',     text: '> decrypt data stream',             ms: 45 },
    { t: 'out',     text: '[ OK ] entropy verified, 0 corrupt',ms: 38 },
    { t: 'cmd',     text: '> access granted',                  ms: 45 },
    { t: 'out',     text: '[ OK ] identity: netrunner_',       ms: 38 },
    { t: 'welcome', text: 'welcome, netrunner_',               ms: 60 }
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

  /* ---------- 内存探测（2.7）：typeof==='number' && <8，禁 truthiness ---------- */
  function probeMemory() {
    var dm = navigator.deviceMemory;
    state.lowMem = (typeof dm === 'number' && dm < 8);
    var q = new URLSearchParams(location.search);
    if (q.get('lowmem') === '1') state.lowMem = true;
    return state.lowMem;
  }

  /* ---------- 性能分层 T0–T3（2.8）：ema 采样、降 3s / 升 5s 迟滞 ---------- */
  var perf = { ema: 0, bad: 0, good: 0, lastT: 0 };
  function perfSample() {
    var now = performance.now();
    if (!perf.lastT) { perf.lastT = now; return; }
    var dt = now - perf.lastT;
    perf.lastT = now;
    perf.ema = perf.ema ? perf.ema * 0.92 + dt * 0.08 : dt;
    if (perf.ema > 33) { perf.bad += dt; perf.good = 0; }   // <30fps → 坏帧
    else { perf.good += dt; perf.bad = 0; }
    if (perf.bad >= 3000 && state.tier < 3) { state.tier++; perf.bad = 0; applyTier(); }
    else if (perf.good >= 5000 && state.tier > 0) { state.tier--; perf.good = 0; applyTier(); }
  }
  function applyTier() {
    if (!rain.running) return;
    rain.cfg.density = [1, 0.7, 0.4, 0.25][state.tier];
    rain.cfg.dpr = state.tier >= 2 ? 1 : rain.baseDpr;
    rain.cfg.speed = [1, 1, 0.8, 0.6][state.tier];
    rain.resize(true);
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
      // T3 用实底清屏（无拖影），其余用半透明叠影制造拖尾
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

  /* ---------- CMD 引导转场（T0–T7） ---------- */
  var cmd = {
    overlay: null, linesEl: null, caret: null, canvas: null, pctx: null,
    particles: [], skipFlag: false,
    init: function () {
      this.overlay = $('cmdOverlay');
      this.linesEl = $('cmdLines');
      this.caret = $('cmdCaret');
      this.canvas = $('cmdParticles');
      this.pctx = this.canvas ? this.canvas.getContext('2d') : null;
      var self = this;
      this.overlay.addEventListener('click', function () { self.skip(); });
    },
    resizeCanvas: function () {
      if (!this.canvas || !this.pctx) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.round(window.innerWidth * dpr);
      this.canvas.height = Math.round(window.innerHeight * dpr);
      this.canvas.style.width = window.innerWidth + 'px';
      this.canvas.style.height = window.innerHeight + 'px';
      this.pctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    },
    burstParticles: function () {
      var self = this;
      if (!this.canvas || !this.pctx) return;
      this.resizeCanvas();
      var ctx = this.pctx;
      var cx = window.innerWidth / 2, cy = window.innerHeight / 2;
      var colors = ['0,255,136', '0,212,255', '0,128,255', '57,255,106'];
      for (var i = 0; i < 80; i++) {
        var a = Math.random() * Math.PI * 2;
        var v = 0.6 + Math.random() * 2.2;
        this.particles.push({
          x: cx, y: cy,
          vx: Math.cos(a) * v, vy: Math.sin(a) * v,
          life: 1, decay: 0.012 + Math.random() * 0.018,
          r: 1 + Math.random() * 2.4,
          c: colors[i % colors.length]
        });
      }
      var t0 = performance.now();
      function loop(now) {
        if (self.skipFlag) { ctx.clearRect(0, 0, window.innerWidth, window.innerHeight); self.particles = []; return; }
        var dt = Math.min(0.05, (now - t0) / 1000);
        ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
        var alive = false;
        for (var i = 0; i < self.particles.length; i++) {
          var p = self.particles[i];
          if (p.life <= 0) continue;
          alive = true;
          p.x += p.vx * dt * 60;
          p.y += p.vy * dt * 60;
          p.life -= p.decay;
          ctx.globalAlpha = Math.max(0, p.life);
          ctx.fillStyle = 'rgba(' + p.c + ',1)';
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r * p.life + 0.2, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
        if (alive) requestAnimationFrame(loop);
        else { ctx.clearRect(0, 0, window.innerWidth, window.innerHeight); self.particles = []; }
      }
      requestAnimationFrame(loop);
    },
    addLine: function (line, ms) {
      var div = document.createElement('div');
      var span = document.createElement('span');
      span.className = line.t === 'out' ? '' : 'cmd-grad';
      span.textContent = line.text;
      div.appendChild(span);
      div.className = 'cmd-line' + (line.t === 'title' ? ' cmd-title' : '');
      if (reduceMotion) { div.classList.add('typed'); this.linesEl.appendChild(div); return Promise.resolve(ms); }
      this.linesEl.appendChild(div);
      var self = this;
      return new Promise(function (resolve) {
        var i = 0, txt = line.text, step = (line.ms || 45) * 0.35;
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
      this.overlay.style.visibility = 'visible';
      this.overlay.classList.add('on');
      window.addEventListener('resize', function () { self.resizeCanvas(); });
      // T0 白闪段
      chain = chain.then(function () { return new Promise(function (r) { setTimeout(r, 180); }); });
      CMD_SCRIPT.forEach(function (line) {
        chain = chain.then(function () { return self.addLine(line, line.ms); });
        if (line.t === 'cmd') chain = chain.then(function () { return new Promise(function (r) { setTimeout(r, 60); }); });
      });
      // T3 回车扫描线
      chain = chain.then(function () {
        var sl = document.createElement('div');
        sl.className = 'cmd-scanline';
        self.linesEl.appendChild(sl);
        return new Promise(function (r) { setTimeout(r, 520); });
      });
      // T4 光标急闪（2.5Hz）
      chain = chain.then(function () {
        self.caret.style.display = 'inline-block';
        self.caret.classList.add('fast');
        return new Promise(function (r) { setTimeout(r, 420); });
      });
      // T5 径向光晕（蓝→青→绿）
      chain = chain.then(function () {
        self.overlay.classList.add('glow');
        return new Promise(function (r) { setTimeout(r, 480); });
      });
      // T6 粒子爆散
      chain = chain.then(function () {
        self.burstParticles();
        return new Promise(function (r) { setTimeout(r, 1100); });
      });
      // T7 收幕：主题激活 + overlay 淡出
      chain = chain.then(function () { return self.finishEnter(); });
      chain.catch(function () {});
      return chain;
    },
    finishEnter: function () {
      this.overlay.classList.remove('glow');
      this.overlay.classList.remove('on');
      this.caret.classList.remove('fast');
      this.caret.style.display = 'none';
      document.documentElement.setAttribute('data-theme', 'overclock');
      rain.start();
      state.active = true;
      state.entering = false;
      // 按钮转为「返回原版」形态（常驻可见，可随时切回）
      var btn = $('swapBtn');
      if (btn) {
        btn.classList.remove('m-open', 'm-out');
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

  /* ---------- 警告弹窗（2.7.3） ---------- */
  var warn = {
    el: null,
    init: function () {
      this.el = $('memWarn');
      if (!this.el) return;
      var self = this;
      $('warnOk').addEventListener('click', function () { self.close(true); });
      $('warnCancel').addEventListener('click', function () { self.close(false); });
      this.el.addEventListener('click', function (e) { if (e.target === self.el) self.close(false); });
    },
    show: function () { if (this.el) this.el.hidden = false; },
    close: function (ok) {
      if (this.el) this.el.hidden = true;
      if (ok) {
        sessionStorage.setItem('axiom_neon_warned', '1');
        state.warnedOnce = true;
        enterNeon();
      }
    }
  };

  /* ---------- 入场编排：M0 触底 → M1–M3 机械展开 → CMD 转场 ---------- */
  function enterNeon() {
    if (state.entering || state.active || state.exiting) return;
    state.entering = true;
    var btn = $('swapBtn');
    btn.classList.add('m-down');                       // M0 触底
    setTimeout(function () {
      btn.classList.remove('m-down');
      btn.classList.add('m-open');                     // M1–M3 合页+齿轮+旋入
      cmd.run();                                       // T0–T7
    }, 90);
  }

  /* ---------- 退场 X1–X5（≈1.5s） ---------- */
  function exitNeon() {
    if (!state.active || state.entering || state.exiting) return;
    state.exiting = true;
    var btn = $('swapBtn');
    var overlay = $('cmdOverlay');
    // X1 按钮归位（返回原版形态 → 机械态）+ 数据回卷（矩阵雨加速上卷 0.34s）
    btn.classList.remove('m-oc');
    var lbl = btn.querySelector('.swap-btn__label');
    if (lbl) lbl.textContent = '超频协议';
    btn.classList.add('m-open');
    rain.cfg.speed = 3;
    setTimeout(function () {
      // X2 收幕黑场
      overlay.style.visibility = 'visible';
      overlay.classList.add('on');
      overlay.classList.add('exiting');
      setTimeout(function () {
        // X3 数据回卷完成 → X4 收幕 → X5 切回原版
        rain.stop();
        document.documentElement.removeAttribute('data-theme');
        state.active = false;
        setTimeout(function () {
          overlay.classList.remove('on', 'exiting');
          overlay.style.visibility = 'hidden';
          rain.cfg.speed = 1;
          btn.classList.remove('m-open', 'm-down');
          state.exiting = false;
        }, 420);
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
    btn.addEventListener('click', function () {
      if (state.entering || state.exiting) return;
      if (state.active) { exitNeon(); return; }
      if (state.lowMem && !state.warnedOnce) warn.show();
      else enterNeon();
    });
    document.addEventListener('keydown', function (e) {
      if (e.ctrlKey && e.shiftKey && (e.key === 'T' || e.key === 't')) {
        e.preventDefault();
        if (state.entering || state.exiting) return;
        if (state.active) exitNeon();
        else if (state.lowMem && !state.warnedOnce) warn.show();
        else enterNeon();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
