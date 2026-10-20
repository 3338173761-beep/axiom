/* Axiom Web — 赛博朋克双主题引擎
 * 原版默认 → 点击切换 → 矩阵雨入场动画 → cyber 主题
 * 随时切回 → 反向退场动画 → 原版
 */
"use strict";

(function () {

  let cyberOn = false;
  let switching = false;

  // ==================== 二进制矩阵雨（Canvas） ====================
  const canvas = document.getElementById("cyberRain");
  const ctx = canvas.getContext("2d");
  const GLYPHS = "01";              // 纯二进制流
  let cols = 0, drops = [], rafId = 0, running = false, frame = 0;

  function sizeCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(window.innerWidth * dpr);
    canvas.height = Math.floor(window.innerHeight * dpr);
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const fs = 15;
    cols = Math.ceil(window.innerWidth / fs);
    drops = [];
    for (let i = 0; i < cols; i++) {
      drops.push(Math.floor(Math.random() * -50));  // 随机起始深度（顶部上方）
    }
  }

  function drawRain() {
    if (!running) return;
    frame++;
    // 尾迹：半透明覆盖制造拖影（低透明度融合背景）
    ctx.fillStyle = "rgba(3, 7, 18, 0.16)";
    ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
    ctx.font = "15px 'Cascadia Code', Consolas, monospace";
    for (let i = 0; i < cols; i++) {
      const x = i * 15;
      let y = drops[i] * 15;
      // 头部亮点（青绿、稍亮）
      ctx.fillStyle = "rgba(153, 255, 210, 0.55)";
      ctx.fillText("1", x, y);
      // 中部低对比（暗青，融合背景）
      ctx.fillStyle = "rgba(34, 211, 238, 0.16)";
      for (let k = 1; k < 6; k++) {
        if (y - k * 15 < 0) break;
        ctx.fillText(GLYPHS[(i * 7 + k + frame) % 2], x, y - k * 15);
      }
      // 每 2 帧下落一格（慢速、不突兀）
      if (frame % 2 === 0) {
        drops[i]++;
        if (y > window.innerHeight + 120 && Math.random() > 0.96) {
          drops[i] = Math.floor(Math.random() * -40);
        }
      }
    }
    rafId = requestAnimationFrame(drawRain);
  }

  function startRain() {
    if (running) return;
    running = true;
    frame = 0;
    sizeCanvas();
    ctx.fillStyle = "rgba(3, 7, 18, 1)";
    ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
    rafId = requestAnimationFrame(drawRain);
  }

  function stopRain() {
    running = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  window.addEventListener("resize", () => {
    if (running) {
      sizeCanvas();
      ctx.fillStyle = "rgba(3, 7, 18, 1)";
      ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
    }
  });

  // ==================== 切换转场动画 ====================
  const fx = document.getElementById("themeFX");
  const fxBoot = document.getElementById("fxBoot");

  // 入场：黑幕拉满 → 代码涌流 → 切主题 → 收幕
  function playEnter(cb) {
    fx.classList.remove("fx-exit");
    fx.classList.add("fx-on");                       // 黑幕 + 扫描线
    fxBoot.classList.remove("fx-boot-run");
    void fxBoot.offsetWidth;                         // 强制重排
    fxBoot.classList.add("fx-boot-run");             // 代码涌流动画
    setTimeout(() => { cb(); }, 520);                // 幕中最深处切主题
    setTimeout(() => {
      fx.classList.remove("fx-on");
      fx.classList.add("fx-exit");                   // 收幕（从下往上升）
      setTimeout(() => {
        fx.classList.remove("fx-exit");
        fxBoot.classList.remove("fx-boot-run");
      }, 700);
    }, 860);
  }

  // 退场：黑幕拉满 → 代码回卷 → 切回原版 → 收幕
  function playExit(cb) {
    fx.classList.remove("fx-exit");
    fx.classList.add("fx-on");
    fxBoot.classList.remove("fx-boot-run");
    void fxBoot.offsetWidth;
    fxBoot.classList.add("fx-boot-exit");            // 回卷动画
    setTimeout(() => { cb(); }, 480);
    setTimeout(() => {
      fx.classList.remove("fx-on");
      fx.classList.add("fx-exit");
      setTimeout(() => {
        fx.classList.remove("fx-exit");
        fxBoot.classList.remove("fx-boot-exit");
      }, 700);
    }, 800);
  }

  // ==================== 主题切换 ====================
  function applyTheme(to) {
    document.documentElement.dataset.theme = to;
    if (to === "cyber") { startRain(); }
    else { stopRain(); }
    // 按钮文案同步
    document.querySelectorAll(".btn-theme-txt").forEach(el => {
      el.textContent = to === "cyber" ? "经典模式" : "赛博模式";
    });
    document.querySelectorAll(".btn-theme, .btn-theme-float").forEach(el => {
      el.classList.toggle("cyber-on", to === "cyber");
    });
  }

  function toggleTheme() {
    if (switching) return;
    switching = true;
    const going = !cyberOn;
    if (going) {
      playEnter(() => applyTheme("cyber"));
      setTimeout(() => { cyberOn = true; switching = false; }, 1600);
    } else {
      playExit(() => applyTheme(""));
      setTimeout(() => { cyberOn = false; switching = false; }, 1500);
    }
  }

  document.getElementById("btnTheme").addEventListener("click", toggleTheme);
  document.getElementById("btnThemeFloat").addEventListener("click", toggleTheme);

  // 键盘快捷键（可选）：Ctrl+Shift+T
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.shiftKey && (e.key === "T" || e.key === "t")) {
      e.preventDefault(); toggleTheme();
    }
  });

  // 深色模式偏好一致（默认原版，不主动切 cyber）
  if (document.documentElement.dataset.theme === "cyber") {
    cyberOn = true;
    applyTheme("cyber");
  }
})();
