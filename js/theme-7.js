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
    { t: 'title', text: 'AXIOM//OVERCLOCK PROTOCOL v2.8.5',            ms: 60 },
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

  /* ---------- 故障风暴：乱码雨 + 彩色 glitch 块 + 条带撕裂 + 噪点（错乱段主效果） ---------- */
  var storm = {
    cv: null, ctx: null, W: 0, H: 0, rafId: 0, t0: 0, dur: 0, palette: 'red',
    CHARS: '01▓▒░█▄▀■◢◣◥◤┌┐└┘┤├┬┴┼╋═║╔╗╚╝ 異常覚醒崩壊周波数核心臨界AXIOMOVERCLOCK',
    init: function () {
      this.cv = $('glitchStorm');
      if (!this.cv) return;
      this.ctx = this.cv.getContext('2d');
      var self = this;
      window.addEventListener('resize', function () { if (self.rafId) self.resize(); });
    },
    resize: function () {
      this.W = window.innerWidth; this.H = window.innerHeight;
      this.cv.width = this.W; this.cv.height = this.H;
      this.cv.style.width = this.W + 'px'; this.cv.style.height = this.H + 'px';
    },
    start: function (dur, palette) {
      if (!this.ctx) return;
      this.dur = dur || 600; this.palette = palette || 'red';
      this.resize();
      this.t0 = performance.now();
      this.cv.style.opacity = '1';
      var self = this;
      this.rafId = requestAnimationFrame(function (t) { self.frame(t); });
      document.body.classList.add('oc-shake');
      var ov = $('cmdOverlay');
      if (ov) ov.classList.add('glitching');
      setTimeout(function () {
        if (ov) ov.classList.remove('glitching');
      }, dur);
    },
    frame: function (t) {
      var el = t - this.t0;
      if (el > this.dur) { this.stop(); return; }
      // 每帧同步视口尺寸：移动端地址栏收起/展开会改变 innerHeight，画布跟新避免底部黑条
      var W = window.innerWidth, H = window.innerHeight;
      if (W !== this.W || H !== this.H) {
        this.W = W; this.H = H;
        this.cv.width = W; this.cv.height = H;
        this.cv.style.width = W + 'px'; this.cv.style.height = H + 'px';
      }
      var ctx = this.ctx;
      var self = this;
      // 终焉模式：满屏雪花噪点（电视雪花）——崩溃假象
      if (this.palette === 'snow') {
        if (!this.snowImg || this.snowImg.width !== W || this.snowImg.height !== H) {
          this.snowImg = ctx.createImageData(W, H);
          var d0 = this.snowImg.data;
          for (var z = 0; z < d0.length; z += 4) { d0[z] = 20; d0[z + 1] = 20; d0[z + 2] = 24; d0[z + 3] = 255; }
        }
        var d = this.snowImg.data, n = d.length, k = 0, target = Math.floor(W * H * 0.38);
        while (k < target) {
          var i = (Math.random() * n) & ~3;
          var v = Math.random() < 0.45 ? 255 : (Math.random() < 0.35 ? 150 : 15);
          d[i] = v; d[i + 1] = v; d[i + 2] = v; d[i + 3] = 255;
          k++;
        }
        ctx.putImageData(this.snowImg, 0, 0);
        if (Math.random() < 0.4) {
          ctx.fillStyle = 'rgba(' + (Math.random() < 0.5 ? '255,77,94' : '0,212,255') + ',0.28)';
          ctx.fillRect(0, 0, W, H);
        }
        this.rafId = requestAnimationFrame(function (tt) { self.frame(tt); });
        return;
      }
      ctx.fillStyle = 'rgba(2,3,8,0.30)';
      ctx.fillRect(0, 0, W, H);
      var c1, c2, c3;
      if (this.palette === 'red') { c1 = '255,77,94'; c2 = '0,212,255'; c3 = '255,255,255'; }
      else if (this.palette === 'green') { c1 = '0,255,136'; c2 = '255,77,94'; c3 = '209,247,255'; }
      else { c1 = '255,255,255'; c2 = '0,212,255'; c3 = '255,77,94'; }
      // 0) 全屏色相冲屏：随机概率整屏染色（错乱感）
      if (Math.random() < 0.06) {
        ctx.fillStyle = 'rgba(' + (Math.random() < 0.5 ? c1 : c2) + ',0.13)';
        ctx.fillRect(0, 0, W, H);
      }
      // 0b) 白帧闪切：偶尔一帧全屏半透明白
      if (Math.random() < 0.02) {
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.fillRect(0, 0, W, H);
      }
      // 1) 乱码字符风暴：密度按屏幕面积自适应（手机端自动加倍不再稀疏）
      ctx.font = (16 + Math.random() * 26) + 'px "Share Tech Mono", monospace';
      var rows = Math.max(30, Math.round(H / 12));
      for (var i = 0; i < rows; i++) {
        var y = Math.random() * H;
        var x = Math.random() * 60 - 30;
        var str = '';
        var len = 10 + Math.floor(Math.random() * 40);
        for (var j = 0; j < len; j++) str += this.CHARS[Math.floor(Math.random() * this.CHARS.length)];
        var rgba = Math.random() < 0.45 ? c1 : (Math.random() < 0.5 ? c2 : c3);
        ctx.fillStyle = 'rgba(' + rgba + ',' + (0.3 + Math.random() * 0.65) + ')';
        ctx.fillText(str, x, y);
      }
      // 2) 彩色 glitch 块：数量按面积自适应（红/青/绿/白 小方块乱闪）
      var blocks = Math.min(96, Math.max(24, Math.round(W * H / 7500)));
      for (var b = 0; b < blocks; b++) {
        var bw = 4 + Math.random() * 80, bh = 2 + Math.random() * 20;
        var bx = Math.random() * W, by = Math.random() * H;
        var bc = Math.random() < 0.5 ? c1 : (Math.random() < 0.5 ? c2 : (Math.random() < 0.5 ? '0,255,136' : '255,255,255'));
        ctx.fillStyle = 'rgba(' + bc + ',' + (0.15 + Math.random() * 0.5) + ')';
        ctx.fillRect(bx, by, bw, bh);
      }
      // 3) 白色扫描横线：更频繁更亮
      if (Math.random() < 0.7) {
        ctx.fillStyle = 'rgba(209,247,255,' + (0.35 + Math.random() * 0.55) + ')';
        ctx.fillRect(0, Math.random() * H, W, 1 + Math.random() * 3);
      }
      // 4) 噪点像素：密度按屏幕面积（雪花，手机端不再稀疏不可见）
      var noiseN = Math.min(2600, Math.max(700, Math.round(W * H / 260)));
      for (var p = 0; p < noiseN; p++) {
        var pc = Math.random() < 0.5 ? c1 : (Math.random() < 0.3 ? c3 : c2);
        ctx.fillStyle = 'rgba(' + pc + ',' + (0.15 + Math.random() * 0.55) + ')';
        ctx.fillRect(Math.random() * W, Math.random() * H, 1, 1);
      }
      // 5) 大号错误撕裂字（红调时更频繁 + 双层错位）
      if (this.palette === 'red' && Math.random() < 0.55) {
        var tx = Math.random() * W * 0.8, ty = 30 + Math.random() * H * 0.8;
        var fsz = 34 + Math.random() * 50;
        var words = ['ERR', 'FATAL', 'SIGNAL', 'KERNEL', '0xDEAD', 'PANIC', 'CORRUPT'];
        var wd = words[Math.floor(Math.random() * words.length)];
        ctx.font = fsz + 'px Orbitron, "Share Tech Mono", monospace';
        ctx.fillStyle = 'rgba(0,212,255,0.5)';
        ctx.fillText(wd, tx + 4 + Math.random() * 8, ty + 4 + Math.random() * 8);
        ctx.fillStyle = 'rgba(255,77,94,' + (0.5 + Math.random() * 0.45) + ')';
        ctx.fillText(wd, tx, ty);
      }
      // 6) RGB 通道分离叠影（3D 眼镜式红/青错位大字，更强偏移）
      if (Math.random() < 0.7) {
        var gx = Math.random() * W * 0.7, gy = Math.random() * H;
        var gs = 24 + Math.random() * 36;
        var gwd = this.CHARS[Math.floor(Math.random() * this.CHARS.length)] +
                  this.CHARS[Math.floor(Math.random() * this.CHARS.length)] +
                  this.CHARS[Math.floor(Math.random() * this.CHARS.length)];
        ctx.font = gs + 'px "Share Tech Mono", monospace';
        var off = 8 + Math.random() * 10;
        ctx.fillStyle = 'rgba(' + c1 + ',0.55)';
        ctx.fillText(gwd, gx + off, gy);
        ctx.fillStyle = 'rgba(' + c2 + ',0.55)';
        ctx.fillText(gwd, gx - off, gy);
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillText(gwd, gx, gy);
      }
      // 7) 水平撕裂带：更多条、更碎（画面被撕开）
      var bands = 4 + Math.floor(Math.random() * 6);
      for (var bd = 0; bd < bands; bd++) {
        var by0 = Math.random() * H;
        var bh0 = 6 + Math.random() * 34;
        var shift = (Math.random() * 40 - 20) | 0;
        var bdx = (Math.random() * W * 0.6) | 0;
        var img = ctx.getImageData(0, by0, W, bh0);
        ctx.fillStyle = 'rgba(2,3,8,0.85)';
        ctx.fillRect(0, by0, W, bh0);
        ctx.putImageData(img, bdx, by0);
        // 撕裂边缘亮线
        ctx.fillStyle = 'rgba(' + (Math.random() < 0.5 ? c1 : c3) + ',0.9)';
        ctx.fillRect(0, by0 + bh0 - 1, W, 1);
      }
      // 8) 全屏滚动扫描线（正弦上下扫）
      var sy = (Math.sin(t / 60) * 0.5 + 0.5) * H;
      ctx.fillStyle = 'rgba(209,247,255,0.12)';
      ctx.fillRect(0, sy - 26, W, 52);
      ctx.fillStyle = 'rgba(209,247,255,0.5)';
      ctx.fillRect(0, sy, W, 1);
      this.rafId = requestAnimationFrame(function (tt) { self.frame(tt); });
    },
    stop: function () {
      if (this.rafId) cancelAnimationFrame(this.rafId);
      this.rafId = 0;
      if (this.cv) this.cv.style.opacity = '0';
      if (this.ctx) this.ctx.clearRect(0, 0, this.W, this.H);
      document.body.classList.remove('oc-shake');
    }
  };

  /* ---------- 第二形态英文化（进入替换，退出恢复；2077 艺术字由 CSS 类 oc-en 提供） ---------- */
  var i18n = {
    applied: false, saved: [], fmtHi: null, fmtHiOrig: '',
    map: [
      { sel: '.brand-sub', html: 'MULTI-FORMAT AUTO-DECOMPILER' },
      { sel: '#runtimeText', html: 'PYTHON RUNTIME READY' },
      { sel: '.hero-title', html: 'REDUCE COMPILED SCRIPTS<br><em>BACK TO SOURCE</em>' },
      { sel: '.hero-sub', html: 'RPYC · RPA · PYC · APK · DEX · JAR — DROP IT IN · ENGINE RUNS IN YOUR BROWSER · FILES NEVER LEAVE' },
      { sel: '.upload-card h2', html: 'UPLOAD FILE' },
      { sel: '.dz-title', html: 'CLICK TO SELECT OR DRAG & DROP' },
      { sel: '.dz-hint', html: 'SUPPORTED: RPYC / RPYMC / RPA / PYC / DEX / APK / JAR…' },
      { sel: '.privacy-note', html: '100% LOCAL — FILES NEVER LEAVE THIS DEVICE' },
      { sel: '.set-label[for="outputName"]', html: 'OUTPUT FILE NAME' },
      { sel: '.set-label:not([for])', html: 'AI CONTEXT TRANSLATION' },
      { sel: '.set-tip', html: 'DeepSeek · Context-aware · ZH ↔ EN' },
      { sel: '#cardInfo h2', html: 'FORMAT DETECTION' },
      { sel: '#cardActions h2', html: 'DECOMPILE & TRANSLATE' },
      { sel: '#progressWrap h2', html: 'EXECUTION LOG' },
      { sel: '#cardResult h2', html: 'DECOMPILED RESULT' },
      { sel: '#btnDecompile .btn-label', html: 'DECOMPILE' },
      { sel: '#btnTranslate .btn-label', html: 'TRANSLATE' },
      { sel: '#btnReset .btn-label', html: 'RESET' },
      { sel: '.tab[data-tab="src"]', html: 'SOURCE' },
      { sel: '#tabTrans', html: 'TRANSLATED' },
      { sel: '#btnCopy .btn-label', html: 'COPY' },
      { sel: '#btnDownload .btn-label', html: 'DOWNLOAD' },
      { sel: '#footEngine', html: 'ENGINE: PYODIDE · BROWSER-LOCAL · READY' }
    ],
    apply: function () {
      if (this.applied) return;
      this.applied = true; this.saved = [];
      var self = this;
      this.map.forEach(function (m) {
        var el = document.querySelector(m.sel);
        if (!el) return;
        self.saved.push({ el: el, v: el.innerHTML });
        el.innerHTML = m.html;
        el.classList.add('oc-en');
      });
      var hi = document.querySelector('#fmtCloud .fmt-chip-hi');
      if (hi) {
        this.fmtHi = hi; this.fmtHiOrig = hi.textContent;
        var n = parseInt((hi.textContent || '').replace(/[^\d]/g, ''), 10);
        hi.textContent = (n || 620) + ' FORMATS DETECTED';
        hi.classList.add('oc-en');
      }
      var bl = document.querySelector('#swapBtn .swap-btn__label');
      if (bl) { this.saved.push({ el: bl, v: bl.textContent }); bl.textContent = 'RETURN TO BASE'; bl.classList.add('oc-en'); }
    },
    restore: function () {
      if (!this.applied) return;
      this.applied = false;
      this.saved.forEach(function (s) { s.el.innerHTML = s.v; s.el.classList.remove('oc-en'); });
      if (this.fmtHi) { this.fmtHi.textContent = this.fmtHiOrig; this.fmtHi.classList.remove('oc-en'); }
      this.saved = []; this.fmtHi = null;
    }
  };

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
        // 红色警示条闪出后 → 故障风暴：白屏乱闪 + 乱码雨 + 撕裂错位 + 红/绿 glitch（后半段错乱）
        if (line.t === 'alert') {
          chain = chain.then(function () { return new Promise(function (r) { setTimeout(r, 680); }); });
          // 第一波：白屏 + 红色风暴（乱码/彩块/撕裂/抖动/切片 全开）
          chain = chain.then(function () { flash(80); return new Promise(function (r) { setTimeout(r, 80); }); });
          chain = chain.then(function () { storm.start(720, 'red'); return new Promise(function (r) { setTimeout(r, 720); }); });
          // 红闪 + 白闪
          chain = chain.then(function () { flash(120, 'rgba(255,77,94,0.45)'); return new Promise(function (r) { setTimeout(r, 130); }); });
          chain = chain.then(function () { flash(90, 'rgba(209,247,255,0.4)'); return new Promise(function (r) { setTimeout(r, 100); }); });
          // 第二波：青色风暴（第二轮撕裂）
          chain = chain.then(function () { storm.start(600, 'green'); return new Promise(function (r) { setTimeout(r, 620); }); });
          chain = chain.then(function () { flash(100, 'rgba(209,247,255,0.5)'); return new Promise(function (r) { setTimeout(r, 120); }); });
          // 第三波：红色收敛（报错前最后一击）
          chain = chain.then(function () { storm.start(420, 'red'); return new Promise(function (r) { setTimeout(r, 440); }); });
          // 终焉序列：疯狂闪白屏/彩屏 5 连 → 满屏雪花噪点（崩溃假象）→ 红色报错
          var finSeq = [
            ['rgba(255,255,255,0.95)', 150],
            ['rgba(255,77,94,0.9)', 120],
            ['rgba(209,247,255,0.95)', 150],
            ['rgba(0,255,136,0.9)', 120],
            ['rgba(255,255,255,1)', 170]
          ];
          finSeq.forEach(function (f) {
            chain = chain.then(function () {
              flash(f[1], f[0]);
              return new Promise(function (r) { setTimeout(r, f[1] + 20); });
            });
          });
          chain = chain.then(function () {
            storm.start(680, 'snow');
            return new Promise(function (r) { setTimeout(r, 700); });
          });
          // 红色报错收尾：全屏黑 + 红色艺术字（超频危险 → 系统报错）
          chain = chain.then(function () { return self.errFlash(); });
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
      // 第二形态全面英文化（2077 艺术字）
      i18n.apply();
      var self = this;
      setTimeout(function () { self.overlay.style.visibility = 'hidden'; unlockScroll(); }, 320);
    },
    skip: function () {
      if (!state.entering) return;
      unlockScroll();
      this.finishEnter();
    },
    /* 红色报错收尾：全屏黑 + 红色艺术字（超频协议命名由来：超频=危险→系统报错） */
    errFlash: function () {
      var d = document.createElement('div');
      d.className = 'oc-errflash';
      var big = document.createElement('span');
      big.className = 'oc-errflash__big';
      big.textContent = 'CRITICAL OVERCLOCK FAILURE';
      var sub = document.createElement('span');
      sub.className = 'oc-errflash__sub';
      sub.textContent = 'FREQUENCY LIMIT EXCEEDED · SYSTEM DEGRADED';
      var code = document.createElement('span');
      code.className = 'oc-errflash__code';
      code.textContent = 'ERR: 0xDEADBEEF / OC-STACK-OVERFLOW';
      d.appendChild(big); d.appendChild(sub); d.appendChild(code);
      document.body.appendChild(d);
      return new Promise(function (r) {
        setTimeout(function () {
          d.classList.add('off');
          setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); r(); }, 400);
        }, 620);
      });
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
  /* 转场全程锁定滚动：风暴期间页面无法下拉，看不到任何空区（"风暴长到拉不完"） */
  function lockScroll() {
    window.__axScroll = {
      o1: document.documentElement.style.overflow,
      o2: document.body.style.overflow,
      y: window.pageYOffset || 0
    };
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    window.scrollTo(0, 0);
  }
  function unlockScroll() {
    var s = window.__axScroll;
    if (s) {
      document.documentElement.style.overflow = s.o1;
      document.body.style.overflow = s.o2;
      window.scrollTo(0, s.y);
      window.__axScroll = null;
    }
  }
  function enterNeon() {
    if (state.entering || state.active || state.exiting) return;
    state.entering = true;
    lockScroll();
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
    lockScroll();
    // 先恢复中文（原版 UI）
    i18n.restore();
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
          unlockScroll();
        }, 460);
      }, 560);
    }, 340);
  }

  /* ---------- 环境检测：电脑端 / 手机端（跟随浏览器「电脑模式」开关） ----------
   * 判定信号用浏览器自带能力：User-Agent 非移动端（真电脑，或手机浏览器开启
   * 电脑模式/桌面网站后 UA 伪装成桌面）→ 桌面；视口 >= 1024 或精确指针 → 桌面。
   * 结果写到 <html data-env="desktop|mobile">，布局与右侧实时解析终端据此渲染。 */
  function detectEnv() {
    var ua = navigator.userAgent || '';
    var mobileUA = /Mobi|Android|iPhone|iPad|Windows Phone/i.test(ua);
    var wide = window.innerWidth >= 1024;
    var fine = window.matchMedia && window.matchMedia('(pointer: fine)').matches;
    var env = (!mobileUA || wide || fine) ? 'desktop' : 'mobile';
    document.documentElement.setAttribute('data-env', env);
    return env;
  }

  /* ---------- 入口 ---------- */
  function init() {
    detectEnv();
    window.addEventListener('resize', function () { detectEnv(); });
    probeMemory();
    rain.init();
    storm.init();
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
      i18n.apply();
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
