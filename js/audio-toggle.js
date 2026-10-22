/* ============================================================
 * Axiom · music toggle (topbar pill) + audio lifecycle
 * ------------------------------------------------------------------
 * Lazy AudioContext (created/resumed inside a user gesture only),
 * localStorage memory, M key shortcut, neon pill next to #engineBadge.
 * Exposes window.__axiomAudio = { ctx, masterGain, muted } for the
 * music engine (js/music.js). English comments only.
 * ============================================================ */
(function () {
  'use strict';

  var KEY_MUTED = 'axiom.audio.muted';

  /* ---------- safe storage: never throw, degrade silently ---------- */
  function storageAvailable() {
    try {
      var s = window.localStorage;
      s.setItem('__ax_probe__', '1');
      s.removeItem('__ax_probe__');
      return true;
    } catch (e) { return false; }
  }
  var hasStore = storageAvailable();
  function readMuted() {
    if (!hasStore) return false;
    var v = localStorage.getItem(KEY_MUTED);
    return v === '1';
  }
  function writeMuted(m) {
    if (!hasStore) return;
    try { localStorage.setItem(KEY_MUTED, m ? '1' : '0'); } catch (e) {}
  }

  /* ---------- lazy AudioContext: created/resumed inside a gesture ---------- */
  var ctx = null;
  var masterGain = null;
  var wantMuted = readMuted();

  function ensureContext() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { ctx = new AC({ latencyHint: 'interactive' }); }
    catch (e) { ctx = new AC(); }
    masterGain = ctx.createGain();
    masterGain.gain.value = wantMuted ? 0 : 1;
    masterGain.connect(ctx.destination);
    window.__axiomAudio = { ctx: ctx, masterGain: masterGain, muted: wantMuted };
    ctx.addEventListener('statechange', syncButton);
    return ctx;
  }

  /* Some iOS Safari / Android WebView builds refuse to route audio until
   * a real frame has been written to the output; resume() alone is not
   * enough. Feed a 1-sample silent buffer right after resume. */
  function silentUnlock(c) {
    try {
      var buf = c.createBuffer(1, 1, c.sampleRate);
      var src = c.createBufferSource(); src.buffer = buf;
      var g = c.createGain(); g.gain.value = 0;
      src.connect(g); g.connect(c.destination);
      src.start(0);
    } catch (e) {}
  }

  /* ---------- one-time unlock on the very first user gesture ---------- */
  function unlock() {
    var c = ensureContext();
    if (c && c.state === 'suspended') {
      c.resume().then(function () {
        silentUnlock(c);
        if (!wantMuted && window.__axiomMusic) window.__axiomMusic.onFirstGesture();
        syncButton();
      }).catch(function () {});
    } else if (!wantMuted && window.__axiomMusic) {
      window.__axiomMusic.onFirstGesture();
    }
  }
  function armUnlock() {
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });
  }

  /* ---------- button UI ---------- */
  var btn = document.getElementById('audioToggle');
  function syncButton() {
    if (!btn) return;
    btn.classList.toggle('is-muted', wantMuted);
    btn.setAttribute('aria-pressed', wantMuted ? 'false' : 'true');
    btn.setAttribute('aria-label', wantMuted ? '取消静音（背景音乐已关）' : '静音背景音乐');
  }

  function toggle() {
    wantMuted = !wantMuted;
    writeMuted(wantMuted);
    var c = ensureContext();
    if (c && c.state === 'suspended') c.resume().catch(function () {});
    if (masterGain) {
      var t = c ? c.currentTime : 0;
      masterGain.gain.setTargetAtTime(wantMuted ? 0 : 1, t, 0.05);
    }
    if (window.__axiomAudio) window.__axiomAudio.muted = wantMuted;
    if (window.__axiomMusic) window.__axiomMusic.setMuted(wantMuted);
    if (window.__axiomSfx) window.__axiomSfx.muteToggle(wantMuted);
    syncButton();
  }

  function init() {
    syncButton();
    if (!btn) return;
    btn.addEventListener('click', toggle);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'm' || e.key === 'M') {
        if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;   // never steal real shortcuts
        toggle();
      }
    });
    /* Re-arm audio after backgrounding (iOS 17.5+ / mini-program
     * webviews drop the output route on tab hide). */
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible' && ctx && ctx.state === 'suspended') {
        ctx.resume().then(function () {
          if (!wantMuted && window.__axiomMusic) window.__axiomMusic.onFirstGesture();
          syncButton();
        }).catch(function () {});
      }
    });
    armUnlock();
    prewarm();
  }

  /* Pre-create the (suspended) AudioContext and pre-build every music
   * node (IR, noise buffer, buses) right after load — no gesture needed
   * to create, only to resume. The first tap then starts sound instantly
   * instead of building the whole engine on the spot (mobile latency fix). */
  function prewarm() {
    try {
      var c = ensureContext();
      if (c && window.__axiomMusic && window.__axiomMusic.warmup) window.__axiomMusic.warmup();
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
