/* ==========================================================================
   Sofia — frontend
   Plain ES2020, no build step, no framework. This is deliberate: the site is
   a set of server-rendered pages, and a bundler here would buy nothing but a
   class of deployment bug we have already paid for once.
   ========================================================================== */
(function () {
  "use strict";

  var $  = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function csrf() {
    var el = $('input[name="csrf_token"]');
    return el ? el.value : "";
  }

  /* ------------------------------------------------------------ nav ---- */
  function initNav() {
    var openMenu = null;

    function closeAll() {
      $$(".mega").forEach(function (m) { m.setAttribute("data-open", "false"); });
      $$("[data-mega]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
      openMenu = null;
    }

    $$("[data-mega]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var target = document.getElementById(btn.getAttribute("data-mega"));
        if (!target) return;
        var wasOpen = target.getAttribute("data-open") === "true";
        closeAll();
        if (!wasOpen) {
          target.setAttribute("data-open", "true");
          btn.setAttribute("aria-expanded", "true");
          openMenu = target;
        }
      });
    });

    document.addEventListener("click", function (e) {
      if (openMenu && !openMenu.contains(e.target)) closeAll();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAll();
    });

    var burger = $("#burger");
    var nav = $("#nav");
    if (burger && nav) {
      burger.addEventListener("click", function () {
        var open = nav.classList.toggle("is-open");
        burger.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }
  }

  /* -------------------------------------------------------- filtering --- */
  function initFilters() {
    var tabs = $$(".tab[data-filter]");
    if (!tabs.length) return;
    var cards = $$("#toolgrid .card");
    var empty = $("#noresults");

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var want = tab.getAttribute("data-filter");
        tabs.forEach(function (t) { t.setAttribute("aria-selected", t === tab ? "true" : "false"); });

        var shown = 0;
        cards.forEach(function (card) {
          var match = want === "all" || card.getAttribute("data-category") === want;
          card.style.display = match ? "" : "none";
          if (match) shown++;
        });
        if (empty) empty.style.display = shown ? "none" : "block";

        try {
          var url = new URL(window.location);
          if (want === "all") url.searchParams.delete("c");
          else url.searchParams.set("c", want);
          history.replaceState(null, "", url);
        } catch (e) { /* older browsers: not important */ }
      });
    });

    try {
      var preset = new URL(window.location).searchParams.get("c");
      if (preset) {
        var match = tabs.filter(function (t) { return t.getAttribute("data-filter") === preset; })[0];
        if (match) match.click();
      }
    } catch (e) { /* ignore */ }
  }

  /* ----------------------------------------------------- testimonials --- */
  /* The wall holds still while there is still something new in it. Once
     the reader has reached the foot of it, the columns start creeping to
     bring the rest through.

     The motion itself is CSS, paused until this class lands, so there is
     no JS animation loop here to drift out of step with the paint. */
  function initTestimonials() {
    var wall = $("[data-testimonials]");
    if (!wall) return;

    var cue = $(".tm__cue", wall);
    if (!cue) return;

    function start() { wall.classList.add("is-rolling"); }

    /* Someone who has asked for less motion gets a wall that never
       starts. The stylesheet also drops the duplicated half and hands
       back normal scrolling. */
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    if (still && still.matches) return;

    if (!("IntersectionObserver" in window)) { start(); return; }

    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        start();
        seen.disconnect();
      });
    });
    seen.observe(cue);
  }

  /* -------------------------------------------------------- dropzones --- */
  var FILES = {};

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  function renderFiles(key) {
    var list = $('[data-filelist="' + key + '"]');
    if (!list) return;
    var files = FILES[key] || [];
    list.innerHTML = files.map(function (f, i) {
      return '<li><span class="filelist__name">' + esc(f.name) + "</span>" +
             '<span class="filelist__size">' + humanSize(f.size) + "</span>" +
             '<button type="button" class="filelist__x" data-remove="' + key + '" data-index="' + i + '" aria-label="Remove">&times;</button></li>';
    }).join("");
  }

  function initDropzones() {
    $$("[data-drop]").forEach(function (zone) {
      var key = zone.getAttribute("data-key");
      var multiple = zone.hasAttribute("data-multiple");
      var input = $('input[type="file"]', zone);
      if (!input) return;
      FILES[key] = [];

      function accept(fileList) {
        var incoming = Array.prototype.slice.call(fileList);
        FILES[key] = multiple ? (FILES[key] || []).concat(incoming).slice(0, 20) : incoming.slice(0, 1);
        renderFiles(key);
      }

      zone.addEventListener("click", function () { input.click(); });
      zone.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
      });
      input.addEventListener("change", function () { accept(input.files); });

      ["dragenter", "dragover"].forEach(function (evt) {
        zone.addEventListener(evt, function (e) {
          e.preventDefault(); zone.classList.add("is-over");
        });
      });
      ["dragleave", "drop"].forEach(function (evt) {
        zone.addEventListener(evt, function (e) {
          e.preventDefault(); zone.classList.remove("is-over");
        });
      });
      zone.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.files) accept(e.dataTransfer.files);
      });
    });

    document.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest("[data-remove]") : null;
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      var key = btn.getAttribute("data-remove");
      var index = parseInt(btn.getAttribute("data-index"), 10);
      if (FILES[key]) { FILES[key].splice(index, 1); renderFiles(key); }
    });
  }

  /* ------------------------------------------------------- run a tool --- */
  var LAST_RESULT = null;

  function renderScorecard(data) {
    var score = Math.max(0, Math.min(100, Number(data.overallScore) || 0));
    var circumference = 2 * Math.PI * 40;
    var offset = circumference * (1 - score / 100);

    var html =
      '<div class="score">' +
        '<div class="score__ring">' +
          '<svg width="90" height="90" viewBox="0 0 90 90">' +
            '<circle class="score__track" cx="45" cy="45" r="40"></circle>' +
            '<circle class="score__fill" cx="45" cy="45" r="40" ' +
              'stroke-dasharray="' + circumference + '" stroke-dashoffset="' + circumference + '"></circle>' +
          "</svg>" +
          '<div class="score__num">' + score + "</div>" +
        "</div>" +
        '<div class="score__meta">' +
          "<h3>Grade " + esc(data.grade || "—") + "</h3>" +
          "<p>" + esc(data.headline || "") + "</p>" +
        "</div>" +
      "</div>";

    if (Array.isArray(data.killIssues) && data.killIssues.length) {
      html += '<div class="alert alert--err"><div><strong>Fix these first — they get the CV rejected before it is read:</strong><ul style="margin:8px 0 0;padding-left:18px">' +
        data.killIssues.map(function (k) { return "<li>" + esc(k) + "</li>"; }).join("") +
        "</ul></div></div>";
    }

    [["contentQuality", "Content quality"],
     ["strategicFit", "Fit for the role"],
     ["presentationTrust", "Presentation and trust"]].forEach(function (pair) {
      var rows = data[pair[0]];
      if (!Array.isArray(rows) || !rows.length) return;
      html += "<h3>" + pair[1] + "</h3><table><thead><tr><th>Dimension</th><th>Score</th><th>Finding</th><th>Fix</th></tr></thead><tbody>" +
        rows.map(function (r) {
          return "<tr><td><strong>" + esc(r.dimension) + "</strong></td><td>" +
                 esc(r.score) + "/10</td><td>" + esc(r.finding) + "</td><td>" + esc(r.fix) + "</td></tr>";
        }).join("") + "</tbody></table>";
    });

    if (Array.isArray(data.atsNotes) && data.atsNotes.length) {
      html += "<h3>Applicant tracking systems</h3><ul>" +
        data.atsNotes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
    }

    if (Array.isArray(data.missingEvidence) && data.missingEvidence.length) {
      html += "<h3>Numbers worth chasing</h3>" +
        '<p style="color:var(--ink-3);font-size:.9rem">Sofia will not invent these. Find them and the CV gets materially stronger.</p><ul>' +
        data.missingEvidence.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>";
    }

    return html;
  }

  function animateRing() {
    var fill = $(".score__fill");
    if (!fill) return;
    var target = fill.getAttribute("stroke-dasharray");
    var num = $(".score__num");
    var score = num ? parseInt(num.textContent, 10) : 0;
    requestAnimationFrame(function () {
      fill.style.strokeDashoffset = String(Number(target) * (1 - score / 100));
    });
  }

  function initToolForm() {
    var form = $("#toolform");
    if (!form) return;

    var btn = $("#runbtn");
    var label = $("[data-label]", btn);
    var errorBox = $("#formerror");
    var result = $("#result");
    var resultHead = $("#resulthead");
    var resultBody = $("#resultbody");

    form.addEventListener("submit", function (e) {
      e.preventDefault();

      var authed = form.getAttribute("data-authed") === "true";
      var free = form.getAttribute("data-free") === "true";
      if (!authed && !free) {
        window.location.href = "/auth/signup?next=" + encodeURIComponent(window.location.pathname);
        return;
      }

      errorBox.innerHTML = "";
      btn.disabled = true;
      label.innerHTML = '<span class="spinner"></span> Working…';

      var payload = new FormData(form);
      Object.keys(FILES).forEach(function (key) {
        (FILES[key] || []).forEach(function (file) { payload.append(key, file); });
      });

      var slug = form.getAttribute("data-slug");
      var startedAt = Date.now();
      var pollTimer = null;

      function stop() {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
        btn.disabled = false;
        label.textContent = "Run again";
      }

      function showError(message, code) {
        var extra = "";
        if (code === "insufficient_credits") {
          extra = ' <a href="/account/credits">Top up</a>.';
        } else if (code === "auth_required") {
          extra = ' <a href="/auth/signup">Create a free account</a>.';
        }
        errorBox.innerHTML =
          '<div class="alert alert--err"><div>' + esc(message) + extra + "</div></div>";
        stop();
      }

      function showResult(body) {
        LAST_RESULT = body.result;
        resultHead.innerHTML = "";

        if (body.result.kind === "scorecard") {
          resultBody.innerHTML = renderScorecard(body.result.data || {});
          animateRing();
        } else {
          resultBody.innerHTML = body.result.html || "";
        }

        renderDownloads(body.downloads || []);

        if (typeof body.creditsRemaining === "number") {
          var counter = $('.hdr__auth a[href="/account/"]');
          if (counter) counter.textContent = body.creditsRemaining + " credits";
        }

        result.classList.add("is-open");
        result.scrollIntoView({ behavior: "smooth", block: "start" });
        stop();
      }

      /* The model call runs on the server's worker, so this can take a
         couple of minutes on a long document. Poll gently: every second at
         first so short jobs feel instant, easing out to five seconds so a
         business plan does not generate 120 requests while it works. */
      function poll(jobId, attempt) {
        var wait = attempt < 5 ? 1000 : (attempt < 20 ? 2500 : 5000);

        pollTimer = setTimeout(function () {
          fetch("/api/job/" + jobId, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (body) {
              if (body.status === "running") {
                var seconds = Math.round((Date.now() - startedAt) / 1000);
                label.innerHTML =
                  '<span class="spinner"></span> Working… ' + seconds + "s";
                poll(jobId, attempt + 1);
                return;
              }
              if (body.status === "success") { showResult(body); return; }
              showError(body.message || "That run did not complete.", body.code);
            })
            .catch(function () {
              /* A dropped poll is not a failed job — the work continues on
                 the server. Keep trying for a while before giving up, and
                 tell the user where to find the result if we do. */
              if (attempt < 40) { poll(jobId, attempt + 1); return; }
              showError(
                "Lost contact while the document was being prepared. " +
                "It may still have finished — check your account history."
              );
            });
        }, wait);
      }

      fetch("/api/run/" + slug, {
        method: "POST",
        body: payload,
        headers: { "X-CSRF-Token": csrf() },
        credentials: "same-origin"
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (!res.ok || res.body.status === "error") {
            showError(res.body.message || "Something went wrong.", res.body.code);
            return;
          }
          label.innerHTML = '<span class="spinner"></span> Working…';
          poll(res.body.jobId, 0);
        })
        .catch(function () {
          showError("Could not reach the server. Check your connection and try again — nothing was charged.");
        });
    });

    var again = $("[data-again]");
    if (again) {
      again.addEventListener("click", function () {
        result.classList.remove("is-open");
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  /* --------------------------------------------------- copy / download -- */
  function renderDownloads(links) {
    var slot = $("#resultdownloads");
    if (!slot) return;
    if (!links.length) { slot.innerHTML = ""; return; }
    slot.innerHTML = links.map(function (link) {
      return '<a class="btn btn--ghost btn--sm" href="' + esc(link.url) +
             '">' + esc(link.label) + "</a>";
    }).join("");
  }

  function plainText() {
    var body = $("#resultbody");
    if (!body) return "";
    if (LAST_RESULT && LAST_RESULT.markdown) return LAST_RESULT.markdown;
    return body.innerText || "";
  }

  function initActions() {
    var copy = $("[data-copy]");
    if (copy) {
      copy.addEventListener("click", function () {
        navigator.clipboard.writeText(plainText()).then(function () {
          var original = copy.textContent;
          copy.textContent = "Copied";
          setTimeout(function () { copy.textContent = original; }, 1600);
        });
      });
    }

    var download = $("[data-download]");
    if (download) {
      download.addEventListener("click", function () {
        var blob = new Blob([plainText()], { type: "text/markdown;charset=utf-8" });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = (document.title.split("—")[0] || "sofia").trim().replace(/\s+/g, "-").toLowerCase() + ".md";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }
  }

  /* ------------------------------------------------------ stored jobs -- */
  function renderStored() {
    var el = $("#resultbody[data-payload]");
    if (!el) return;
    try {
      var payload = JSON.parse(el.getAttribute("data-payload"));
      LAST_RESULT = payload;
      if (payload.kind === "scorecard") {
        el.innerHTML = renderScorecard(payload.data || {});
        animateRing();
      } else if (payload.html) {
        el.innerHTML = payload.html;
      } else if (payload.markdown) {
        el.textContent = payload.markdown;
      }
    } catch (e) {
      el.innerHTML = '<div class="alert alert--err"><div>This document could not be displayed.</div></div>';
    }
  }

  /* ------------------------------------------------------------ boot --- */
  document.addEventListener("DOMContentLoaded", function () {
    initNav();
    initFilters();
    initTestimonials();
    initDropzones();
    initToolForm();
    initActions();
    renderStored();
  });

  window.Sofia = { renderStored: renderStored };
})();
