/* ============================================================
 * Axiom · sound-effects engine (music removed) v2.8.30
 * ------------------------------------------------------------------
 * User decision: ALL music layers removed. SFX-only.
 * v2.8.30 re-tune: everything sounds like Cyberpunk 2077 UI /
 * a clean industrial terminal, NOT a screechy synth.
 *
 *  Tone philosophy (applies to every voice):
 *   - No raw square waves (harsh harmonics -> "monkey call")
 *   - No large-range siren LFO sweeps (the old 40-55Hz FM wail)
 *   - Sine / triangle + short band-passed noise transients only
 *   - Very short envelopes (8-120ms), low gains
 *   - Low-pass filters tame every high end; highs stay soft
 *   - Alerts are DEEP, industrial hums / pulses, never wailing
 *
 * The pure-math beat grid is KEPT: theme-7's visual storm chain
 * reads gridSecAt() to keep every flash on the same beat table.
 *
 * API (unchanged, theme-7 compatible):
 *   __axiomSfx {click,tick,boop,hover,morph,muteToggle}
 *   __axiomMusic {onFirstGesture,onOverclockEnter,onOverclockExit,
 *   setForm,setMuted,warmup,sting:{enter,exit},sequencer:{setForm},
 *   stormHit,stormDrumsStart,stormDrumsStop,alarmBedStart,alarmBedStop,
 *   noiseWallStart,noiseWallStop,
 *   beginOverclock(t0),overclockSec(beat),gridSecAt(beat),exitOverclock()}
 *   stormDrumsStart/Stop are no-ops (theme-7 no longer calls).
 * ============================================================ */
(function () {
  'use strict';

  var H = window.__axiomAudio || null;
  var ctx = null, masterGain = null;
  var sfxBus = null, sfxGain = null;
  var glue = null, noiseBuf = null;
  var sirenBed = null, wallNode = null;

  var muted = false;
  var gridOriginSec = 0;
  /* Wall-clock (performance.now ms) counterpart of gridOriginSec, captured in
   * the SAME statement as the audio origin. The visual storm used to take its
   * own performance.now() later, inside enterNeon(), so the whole transition
   * ran a constant amount behind the audio grid -- the "对不上点" complaint.
   * Both clocks now come from one sampling instant, so the gap is zero by
   * construction instead of being estimated after the fact. */
  var gridOriginWallMs = null;
  var inTransition = false;
  var form = 1;

  /* ---------- tempo map (visual grid only) ---------- */
  var FORM1_BPM = 100, FORM2_BPM = 128;
  var SEG_BPM = [100, 110, 125, 140, 155, 165, 155, 150];
  var timeAtBeat = [];

  /* ---------- helpers ---------- */
  function gauss(ms) {
    var u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return (Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)) * ms;
  }
  function cents(c) { return Math.pow(2, c / 1200); }
  function getNoise() {
    if (noiseBuf) return noiseBuf;
    noiseBuf = ctx.createBuffer(1, Math.max(1, Math.floor(ctx.sampleRate)), ctx.sampleRate);
    var d = noiseBuf.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return noiseBuf;
  }
  function stopAt(n, t) {
    try { n.onended = function () { try { n.disconnect(); } catch (e) {} }; n.stop(t); }
    catch (e) { try { n.disconnect(); } catch (e2) {} }
  }
  function bpmAtBar(bar) {
    if (inTransition) {
      if (bar < 0) return FORM1_BPM;
      if (bar >= SEG_BPM.length) return FORM2_BPM;
      return SEG_BPM[bar];
    }
    return form === 1 ? FORM1_BPM : FORM2_BPM;
  }
  function buildTimeMap(totalBars) {
    var t = 0, beat = 0;
    timeAtBeat = [];
    for (var b = 0; b < totalBars; b++) {
      for (var k = 0; k < 4; k++) {
        timeAtBeat[beat] = t;
        t += 60 / bpmAtBar(b) / 4;
        beat++;
      }
    }
    timeAtBeat[beat] = t;
  }
  function secOfBeat(beat) {
    if (beat < timeAtBeat.length) return timeAtBeat[beat];
    var tail = 60 / (inTransition ? FORM2_BPM : (form === 1 ? FORM1_BPM : FORM2_BPM)) / 4;
    return timeAtBeat[timeAtBeat.length - 1] + (beat - (timeAtBeat.length - 1)) * tail;
  }

  /* ---------- core buses ----------
   * Clean, mostly-dry signal path: a gentle limiter only, no heavy
   * compression that would smear short clicks. */
  function buildCore() {
    if (sfxBus) return;
    if (!H || !H.ctx) return;
    ctx = H.ctx;
    masterGain = H.masterGain;
    sfxBus = ctx.createGain();
    sfxGain = ctx.createGain(); sfxGain.gain.value = 0.9;
    /* Safety limiter, not a tone-shaping compressor.
     * The previous -18dB / 3:1 / 2ms settings contradicted this block's own
     * comment: they grabbed the 5-15ms UI transients and smeared them, which is
     * a large part of why clicks sounded dull. Threshold now sits above normal
     * peak level, so quiet UI sounds pass through untouched and only true peaks
     * are clamped. */
    glue = ctx.createDynamicsCompressor();
    glue.threshold.value = -6; glue.knee.value = 6; glue.ratio.value = 12;
    glue.attack.value = 0.0005; glue.release.value = 0.06;
    sfxBus.connect(sfxGain); sfxGain.connect(glue); glue.connect(masterGain);
  }
  function duckSfx(t, amount, atk, rel) {
    /* Deep ducking on every storm hit flattened the whole transition.
     * Clamp the depth so the UI layer keeps its edge. */
    amount = Math.min(amount || 0, 0.15);
    var g = sfxBus.gain;
    g.cancelScheduledValues(t);
    g.setValueAtTime(1 - amount, t);
    g.setTargetAtTime(1.0, t + (atk || 0.002), (rel || 0.15) / 3);
  }

  /* ---------- shared voice helpers (soft, tamed) ---------- */
  /* Soft sine blip: tiny pitch bend, quick decay. The workhorse for
   * all UI feedback. type may be 'sine' (soft) or 'triangle' (firmer). */
  function softBlip(t, fromHz, toHz, dur, vol, type) {
    var o = ctx.createOscillator(); o.type = type || 'sine';
    o.frequency.setValueAtTime(fromHz * cents(gauss(4)), t);
    o.frequency.exponentialRampToValueAtTime(toHz, t + dur);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.02);
    o.connect(g); g.connect(sfxBus);
    o.start(t); stopAt(o, t + dur + 0.04);
  }
  /* Filtered noise tick: short, band-limited, quiet. */
  function noiseTick(t, f, q, vol, dur) {
    var n = ctx.createBufferSource(); n.buffer = getNoise();
    var bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q;
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.001);
    g.gain.exponentialRampToValueAtTime(0.0001, t + (dur || 0.02));
    n.connect(bp); bp.connect(g); g.connect(sfxBus);
    n.start(t); stopAt(n, t + (dur || 0.02) + 0.02);
  }
  /* Non-harmonic metal ring: two square partials a 1.51 ratio apart, low-passed
   * and only 25-40ms long. This is what gives a click a machined edge instead of
   * a pure-tone "beep"; 1.51 is deliberately non-integer so the partials beat
   * rather than blend into a musical interval. */
  function metalRing(t, hz, dur, vol) {
    var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 5200; lp.Q.value = 0.7;
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.001);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    lp.connect(g); g.connect(sfxBus);
    [1, 1.51].forEach(function (k, i) {
      var o = ctx.createOscillator(); o.type = 'square'; o.frequency.value = hz * k;
      var og = ctx.createGain(); og.gain.value = i ? 0.45 : 1;
      o.connect(og); og.connect(lp);
      o.start(t); stopAt(o, t + dur + 0.02);
    });
  }
  /* Shared soft-clip curve for the error voice (tanh keeps it from buzzing). */
  var _softCurve = null;
  function softClipCurve() {
    if (_softCurve) return _softCurve;
    var n = 1024; _softCurve = new Float32Array(n);
    for (var i = 0; i < n; i++) { var x = (i / (n - 1)) * 2 - 1; _softCurve[i] = Math.tanh(x * 2.2); }
    return _softCurve;
  }

  /* ---------- FX voices (error / transition) ---------- */
  /* Low sub drop: 55->32Hz sine swell. Heavy but clean (no distortion). */
  function subDrop(t, level) {
    var o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(55, t);
    o.frequency.exponentialRampToValueAtTime(32, t + 0.8);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(level || 0.45, t + 0.004);
    g.gain.setTargetAtTime(0.0001, t + 0.7, 0.22);
    o.connect(g); g.connect(sfxBus);
    o.start(t); stopAt(o, t + 1.4);
  }
  function noiseBurst(t, level) {
    var n = ctx.createBufferSource(); n.buffer = getNoise();
    var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2400;
    var hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 400;
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(level || 0.22, t + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    n.connect(hp); hp.connect(lp); lp.connect(g); g.connect(sfxBus);
    n.start(t); stopAt(n, t + 0.2);
  }
  /* Impact: sub thump + soft noise transient. No harsh top end. */
  function impact(t, hot) {
    var o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(60, t);
    o.frequency.exponentialRampToValueAtTime(34, t + 0.4);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(hot ? 0.62 : 0.5, t + 0.003);
    g.gain.setTargetAtTime(0.0001, t + 0.6, 0.18);
    o.connect(g); g.connect(sfxBus);
    o.start(t); stopAt(o, t + 1.0);
    var n = ctx.createBufferSource(); n.buffer = getNoise();
    var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 3200;
    var ng = ctx.createGain();
    ng.gain.setValueAtTime(0.0001, t);
    ng.gain.linearRampToValueAtTime(hot ? 0.18 : 0.12, t + 0.003);
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
    n.connect(lp); lp.connect(ng); ng.connect(sfxBus);
    n.start(t); stopAt(n, t + 0.55);
  }
  /* Riser up: noise sweep 200Hz -> 8kHz. Keep gain low. */
  var riserNodes = null;
  function riserStart(t, dur) {
    if (riserNodes || !ctx) return;
    var n = ctx.createBufferSource(); n.buffer = getNoise(); n.loop = true;
    var f = ctx.createBiquadFilter(); f.type = 'highpass'; f.Q.value = 1.5;
    f.frequency.setValueAtTime(200, t);
    f.frequency.exponentialRampToValueAtTime(8000, t + dur * 0.95);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.06, t + dur * 0.3);
    g.gain.linearRampToValueAtTime(0.30, t + dur * 0.9);
    g.gain.setTargetAtTime(0.0001, t + dur, 0.03);
    n.connect(f); f.connect(g); g.connect(sfxBus);
    n.start(t); stopAt(n, t + dur + 0.1);
    riserNodes = { n: n };
  }
  function riserCut(t) {
    if (!riserNodes) return;
    try { riserNodes.n.stop(t + 0.05); } catch (e) {}
    riserNodes = null;
  }
  function playRiserDown(t, dur) {
    var n = ctx.createBufferSource(); n.buffer = getNoise(); n.loop = true;
    var f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.Q.value = 1.5;
    f.frequency.setValueAtTime(5000, t);
    f.frequency.exponentialRampToValueAtTime(300, t + dur);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.07, t + dur * 0.5);
    g.gain.setTargetAtTime(0.0001, t + dur, 0.08);
    n.connect(f); f.connect(g); g.connect(sfxBus);
    n.start(t); stopAt(n, t + dur + 0.1);
  }
  /* Deep industrial alert hum (NOT a siren): detuned low sines with a
   * tiny LFO depth (±3Hz) — the "server-room" alarm texture. */
  function siren(t, dur, hot) {
    var f = hot ? 82 : 65;
    [0, 3, 7].forEach(function (off, i) {
      var o = ctx.createOscillator(); o.type = 'sine';
      o.frequency.value = f * Math.pow(2, off / 12);
      var lfo = ctx.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 0.6 + i * 0.13;
      var lg = ctx.createGain(); lg.gain.value = hot ? 2.5 : 1.8;
      lfo.connect(lg); lg.connect(o.frequency);
      var g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime((hot ? 0.05 : 0.035) / (i + 1), t + 0.1);
      g.gain.setTargetAtTime(0.0001, t + dur, 0.5);
      o.connect(g); g.connect(sfxBus);
      o.start(t); lfo.start(t);
      stopAt(o, t + dur + 0.3); stopAt(lfo, t + dur + 0.3);
    });
  }
  /* Noise wall (snow static): low-passed hiss, gentle volume. */
  function noiseWallStart(t) {
    if (wallNode || !ctx) return;
    var n = ctx.createBufferSource(); n.buffer = getNoise(); n.loop = true;
    var lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 1500;
    var lfo = ctx.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 0.12;
    var lg = ctx.createGain(); lg.gain.value = 350;
    lfo.connect(lg); lg.connect(lp.frequency);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.04, t + 0.8);
    n.connect(lp); lp.connect(g); g.connect(sfxBus);
    n.start(t); lfo.start(t);
    wallNode = { n: n, lfo: lfo, g: g };
  }
  function noiseWallStop(t) {
    if (!wallNode) return;
    var g = wallNode.g;
    if (g) g.gain.setTargetAtTime(0.0001, t, 0.2);
    stopAt(wallNode.n, t + 1.0);
    stopAt(wallNode.lfo, t + 1.0);
    wallNode = null;
  }
  /* Alarm bed: two low hums with slow AM — like distant mains hum. */
  function sirenBedStart(t) {
    if (sirenBed || !ctx) return;
    [55, 55 * 1.003].forEach(function (f, i) {
      var o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = f;
      var g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(i === 0 ? 0.05 : 0.035, t + 0.3);
      g.gain.setTargetAtTime(0.0001, t + 6, 1.8);
      o.connect(g); g.connect(sfxBus);
      o.start(t);
      sirenBed = sirenBed || {};
      sirenBed['o' + i] = o;
    });
    var am = ctx.createOscillator(); am.type = 'sine'; am.frequency.value = 0.5;
    var amg = ctx.createGain(); amg.gain.value = 0.012;
    am.connect(amg); amg.connect(sfxBus.gain);
    am.start(t);
    sirenBed = sirenBed || {};
    sirenBed.am = am; sirenBed.amg = amg;
  }
  function sirenBedStop(t) {
    if (!sirenBed) return;
    if (sirenBed.o0) stopAt(sirenBed.o0, t + 0.3);
    if (sirenBed.o1) stopAt(sirenBed.o1, t + 0.3);
    if (sirenBed.am) stopAt(sirenBed.am, t + 0.3);
    sirenBed = null;
  }

  /* ---------- storm hits (error SFX, on the visual grid) ---------- */
  function stormHit(kind, t) {
    if (!ctx || muted) return;
    var now = (t != null) ? t : ctx.currentTime;
    switch (kind) {
      case 'stab': subDrop(now, 0.35); noiseBurst(now, 0.14); break;
      case 'boom1': impact(now, true); riserStart(now, 1.2); duckSfx(now, 0.3, 0.001, 0.1); break;
      case 'boom2': impact(now, true); subDrop(now, 0.4); duckSfx(now, 0.35, 0.001, 0.1); break;
      case 'hit3': impact(now, true); subDrop(now, 0.35); duckSfx(now, 0.3, 0.001, 0.1); break;
      /* flash 是风暴里出现次数最多的命中（每个闪屏一声）。旧值 Q=6 / 0.07：
       * 谐振出界且太轻，即使卡在拍上也听不见，等于白做对齐。
       * 现按 3-6kHz 清脆区、Q=3（2-5 区间内）、峰值 0.17 重做。 */
      case 'flash': noiseTick(now, 3400, 3, 0.17, 0.012); break;
      case 'snow': impact(now, true); subDrop(now, 0.4); noiseWallStart(now); siren(now, 1.2, true); break;
      case 'err': subDrop(now, 0.45); siren(now, 2.5, true); break;
      case 'drop': impact(now, true); subDrop(now, 0.5); noiseBurst(now, 0.3); duckSfx(now, 0.4, 0.001, 0.1); break;
    }
  }


  /* ---- CRITICAL protocol drum bed (fixes "storm middle is silent") ----
   * v2.8.29 removed procedural music AND the storm drums with it, leaving only
   * ~20 discrete hits across ~13s of storm: the middle went quiet. This is NOT
   * music (no melody, no instruments) -- it is a rhythmic noise-tick bed locked
   * to the SAME tempo map the visuals use, so every flash cell has a sound.
   * Lookahead scheduler: 60ms timer, schedule 250ms ahead. */
  var drumTimer = null, drumBeat = 0;
  function stormDrumsStart() {
    if (!ensureEngine() || muted || drumTimer) return;
    buildTimeMap(16);
    var step = 0.117;                       // 16th at ~128 BPM (form-2 grid)
    drumBeat = Math.max(0, Math.ceil((ctx.currentTime - gridOriginSec) / step));
    drumTimer = setInterval(function () {
      if (muted || !ctx) return;
      var horizon = ctx.currentTime + 0.25;
      while (gridOriginSec + drumBeat * step < horizon) {
        var t = gridOriginSec + drumBeat * step;
        if (t >= ctx.currentTime - 0.02) {
          var accent = drumBeat % 4 === 0;
          noiseTick(t, accent ? 7200 : 5600, 4, accent ? 0.09 : 0.05, 0.005);
          if (drumBeat % 16 === 0) noiseTick(t, 3400, 3, 0.08, 0.01);
        }
        drumBeat++;
      }
    }, 60);
  }
  function stormDrumsStop() {
    if (drumTimer) { clearInterval(drumTimer); drumTimer = null; }
  }

  /* ---------- API ---------- */
  function ensureEngine() {
    if (!H) H = window.__axiomAudio || null;
    if (!H || !H.ctx) return false;
    buildCore();
    muted = H.muted;
    return true;
  }
  var startedOnce = false;
  function start() {
    if (!ensureEngine()) return;
    /* A rejected resume used to be swallowed by .catch(()=>{}), which is why
     * "sometimes there is no sound at all" was undiagnosable. Retry once and
     * leave a visible flag the UI can surface. */
    if (ctx.state === 'suspended') {
      ctx.resume().catch(function () {
        return ctx.resume().catch(function () { if (H) H.resumeFailed = true; });
      });
    }
    buildTimeMap(40);
    gridOriginSec = ctx.currentTime + 0.05;
    gridOriginWallMs = ((typeof performance !== 'undefined') ? performance.now() : Date.now())
      + (gridOriginSec - ctx.currentTime) * 1000;
  }
  function setForm(f) { form = (f === 2) ? 2 : 1; }
  function beginOverclock(t0, wallMs) {
    if (!ensureEngine()) return;
    /* A rejected resume used to be swallowed by .catch(()=>{}), which is why
     * "sometimes there is no sound at all" was undiagnosable. Retry once and
     * leave a visible flag the UI can surface. */
    if (ctx.state === 'suspended') {
      ctx.resume().catch(function () {
        return ctx.resume().catch(function () { if (H) H.resumeFailed = true; });
      });
    }
    if (!startedOnce) { startedOnce = true; start(); }
    /* wallMs must be captured by the caller in the same statement that reads
     * ctx.currentTime, otherwise the visual grid inherits whatever time the
     * caller spends between the two (DOM work, state flags) and every flash
     * lands late against the kick. When it is not supplied we derive it from
     * the two clocks read back-to-back here. */
    gridOriginSec = (t0 != null) ? t0 : ctx.currentTime + 0.05;
    gridOriginWallMs = (wallMs != null && isFinite(wallMs))
      ? wallMs
      : (((typeof performance !== 'undefined') ? performance.now() : Date.now())
         + (gridOriginSec - ctx.currentTime) * 1000);
    inTransition = true;
    buildTimeMap(16);
  }
  function overclockSec(beat) { return gridOriginSec + secOfBeat(beat); }
  function gridSecAt(beat) { return secOfBeat(beat); }
  function exitOverclock() {
    if (!ensureEngine() || muted) return;
    var t = ctx.currentTime;
    playRiserDown(t, 1.4);
    inTransition = false;
    stormDrumsStop();
    /* The transition grid is over: drop the paired origin so a later enterNeon()
     * that is not preceded by beginOverclock() cannot anchor on a stale time and
     * collapse the whole storm into zero-wait frames. */
    gridOriginWallMs = null;
    setTimeout(function () { setForm(1); }, 900);
  }

  /* Overclock sting — UI morph sound (enter: build up + hit). */
  function stingEnterAt(t) {
    if (!ensureEngine() || muted) return;
    if (ctx.state === 'suspended') ctx.resume().catch(function () {});
    if (!startedOnce) { startedOnce = true; start(); }
    var t0 = t + 0.02;
    riserStart(t0, 0.9);
    var o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(110, t0);
    o.frequency.exponentialRampToValueAtTime(330, t0 + 0.8);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.linearRampToValueAtTime(0.16, t0 + 0.3);
    g.gain.setTargetAtTime(0.0001, t0 + 0.9, 0.1);
    o.connect(g); g.connect(sfxBus);
    o.start(t0); stopAt(o, t0 + 1.0);
    impact(t0 + 0.85, true);
    subDrop(t0 + 0.85, 0.4);
    noiseWallStart(t0 + 0.85);
  }
  function stingExitAt(t) {
    if (!ensureEngine() || muted || !startedOnce) return;
    var t0 = t + 0.03;
    playRiserDown(t0, 0.9);
    noiseWallStop(t0);
    sirenBedStop(t0);
    var o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(330, t0 + 0.3);
    o.frequency.exponentialRampToValueAtTime(80, t0 + 0.7);
    var g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t0 + 0.3);
    g.gain.linearRampToValueAtTime(0.14, t0 + 0.32);
    g.gain.setTargetAtTime(0.0001, t0 + 0.8, 0.1);
    o.connect(g); g.connect(sfxBus);
    o.start(t0 + 0.3); stopAt(o, t0 + 0.9);
    setForm(1);
  }

  var api = {
    onFirstGesture: function () { start(); },
    onOverclockEnter: function () { if (ctx) stingEnterAt(ctx.currentTime); },
    onOverclockExit: function () { if (ctx) stingExitAt(ctx.currentTime); },
    setForm: setForm,
    warmup: function () { ensureEngine(); },
    setMuted: function (m) {
      muted = m;
      if (!ctx) return;
      if (m) {
        noiseWallStop(ctx.currentTime);
        sirenBedStop(ctx.currentTime);
        riserCut(ctx.currentTime);
      }
    },
    stormHit: function (kind, t) { if (ensureEngine()) stormHit(kind, t); },
    stormDrumsStart: function () { if (ensureEngine()) stormDrumsStart(); },
    stormDrumsStop: function () { stormDrumsStop(); },
    alarmBedStart: function (t) { if (ensureEngine()) sirenBedStart(t || (ctx ? ctx.currentTime : 0)); },
    alarmBedStop: function (t) { if (ensureEngine()) sirenBedStop(t || (ctx ? ctx.currentTime : 0)); },
    noiseWallStart: function (t) { if (ensureEngine()) noiseWallStart(t || (ctx ? ctx.currentTime : 0)); },
    noiseWallStop: function (t) { if (ensureEngine()) noiseWallStop(t || (ctx ? ctx.currentTime : 0)); },
    beginOverclock: beginOverclock,
    /* Paired wall-clock origin of the current beat grid, or null when audio has
     * never started (muted / no AudioContext). The visual side falls back to a
     * plain performance.now() in that case so the storm still runs. */
    gridWallMs: function () { return (ctx && gridOriginWallMs != null) ? gridOriginWallMs : null; },
    overclockSec: overclockSec,
    gridSecAt: gridSecAt,
    exitOverclock: exitOverclock,
    sting: { enter: stingEnterAt, exit: stingExitAt },
    sequencer: { setForm: setForm }
  };

  /* ---------- UI sfx (Cyberpunk 2077 style, v2.8.30) ----------
   * Clean, digital, quiet. Sine-based blips with tiny pitch bends;
   * short noise transients only where a "click" needs texture.
   * No square waves, no siren sweeps, no loud noise. */
  window.__axiomSfx = (function () {
    function cur() { return ctx ? ctx.currentTime : 0; }
    var sfx = {
      /* Click: filtered noise, not an oscillator tone.
       * 8ms sits inside the 5-15ms window for percussive UI feedback;
       * 4kHz bandpass is the 3-6kHz "crisp" range; Q 3 is inside the 2-5
       * focus window (the old Q 5 + 3600Hz rang); peak 0.30 stays under 1.0.
       * The old build led with a 980->760Hz sine at 34ms, which is why it
       * read as an 8-bit beep. The body tone and metal ring are deliberately
       * slower (45ms / 30ms) so the click still reads as "menu", not "static";
       * total perceived length stays far below the 300ms UI ceiling. */
      click: function (when) { sfx.clickAt(when === undefined ? cur() : when); },
      clickAt: function (t) {
        if (!ctx) return;
        noiseTick(t, 4000, 3, 0.30, 0.008);
        softBlip(t + 0.001, 1250, 840, 0.045, 0.10, 'triangle');
        metalRing(t + 0.002, 2080, 0.030, 0.055);
      },
      /* Terminal type tick: was 0.055 peak, effectively inaudible over the
       * bed; raised to 0.12 and Q dropped into spec. Sine layer removed --
       * a per-character tone is what made the CMD stream feel buzzy. */
      tick: function (when) { sfx.tickAt(when === undefined ? cur() : when); },
      tickAt: function (t) {
        if (!ctx) return;
        noiseTick(t, 3600, 3, 0.12, 0.006);
      },
      /* Confirm: gentle down-boop 640->470Hz. */
      boop: function (when) { sfx.boopAt(when === undefined ? cur() : when); },
      boopAt: function (t) {
        if (!ctx) return;
        softBlip(t, 640, 470, 0.09, 0.2, 'sine');
      },
      /* Hover: 6ms noise at 5.2kHz, quiet enough to repeat without fatigue. */
      hover: function (when) { sfx.hoverAt(when === undefined ? cur() : when); },
      hoverAt: function (t) {
        if (!ctx) return;
        noiseTick(t, 5200, 4, 0.15, 0.006);
      },
      /* Error: this voice did not exist -- every CMD line, [ERR] included,
       * played the same tick, and the only "alarm" used a [0,3,7] minor triad,
       * a consonant interval that physically cannot read as a fault.
       * Two saws a semitone apart (233 / 247Hz) beat at ~14Hz, soft-clipped,
       * doubled, then a 440->92Hz fall and a 32Hz sub tail: dissonance,
       * droop, weight. */
      error: function (when) { sfx.errorAt(when === undefined ? cur() : when); },
      errorAt: function (t) {
        if (!ctx) return;
        var ws = ctx.createWaveShaper(); ws.curve = softClipCurve(); ws.oversample = '2x';
        var g = ctx.createGain();
        g.gain.setValueAtTime(0.0001, t);
        g.gain.linearRampToValueAtTime(0.16, t + 0.004);
        g.gain.setTargetAtTime(0.0001, t + 0.15, 0.05);
        ws.connect(g); g.connect(sfxBus);
        [0, 0.25].forEach(function (off) {
          [233, 247].forEach(function (hz) {
            var o = ctx.createOscillator(); o.type = 'sawtooth'; o.frequency.value = hz;
            var og = ctx.createGain(); og.gain.value = 0.5;
            o.connect(og); og.connect(ws);
            o.start(t + off); stopAt(o, t + off + 0.18);
          });
        });
        var fall = ctx.createOscillator(); fall.type = 'square';
        fall.frequency.setValueAtTime(440, t + 0.16);
        fall.frequency.exponentialRampToValueAtTime(92, t + 0.56);
        var hp = ctx.createBiquadFilter(); hp.type = 'highpass';
        hp.frequency.setValueAtTime(2000, t + 0.16);
        hp.frequency.exponentialRampToValueAtTime(300, t + 0.56);
        var fg = ctx.createGain();
        fg.gain.setValueAtTime(0.0001, t + 0.16);
        fg.gain.linearRampToValueAtTime(0.10, t + 0.19);
        fg.gain.setTargetAtTime(0.0001, t + 0.45, 0.06);
        fall.connect(hp); hp.connect(fg); fg.connect(sfxBus);
        fall.start(t + 0.16); stopAt(fall, t + 0.7);
        subDrop(t + 0.16, 0.30);
      },
      /* Morph: UI deformation — short sweep + tail blip. */
      morph: function (direction, when) { sfx.morphAt(direction || 1, when === undefined ? cur() : when); },
      morphAt: function (dir, t) {
        if (!ctx) return;
        if (dir === 1) {
          softBlip(t, 420, 1180, 0.11, 0.16, 'sine');
          softBlip(t + 0.1, 1180, 920, 0.04, 0.08, 'sine');
        } else {
          softBlip(t, 1180, 420, 0.11, 0.14, 'sine');
          softBlip(t + 0.1, 880, 660, 0.04, 0.06, 'sine');
        }
      },
      /* Mute toggle: two soft notes (down = muted, up = unmuted). */
      muteToggle: function (mutedFlag, when) { sfx.muteToggleAt(mutedFlag, when === undefined ? cur() : when); },
      muteToggleAt: function (m, t) {
        if (!ctx) return;
        var a = m ? 520 : 440;
        var b = m ? 400 : 560;
        softBlip(t, a, a * 0.9, 0.05, 0.12, 'sine');
        softBlip(t + 0.06, b, b * 0.92, 0.05, 0.1, 'sine');
      },
      /* Test-only hook: forces bus construction so a headless harness can
       * schedule voices against a fake AudioContext. Not used by the UI. */
      _ensure: ensureEngine
    };
    return sfx;
  })();

  window.__axiomMusic = api;
})();
