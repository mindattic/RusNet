/* RusNet viewer - renders a RusNet scan JSON into the full interactive report.

   Single entry point for every host (plain browser, the Python pywebview app, the .NET WebView2
   app): window.rusnet.load(data), where data is a parsed RusNet report object (schema v1). Native
   hosts open a file with their own dialog and call load() with the parsed object; in a plain browser
   the toolbar's Open button and drag-drop read the file in-page as a fallback.

   Everything is drawn from the data with no external libraries, so the page stays self-contained and
   works offline. */
(function (root) {
  'use strict';

  // ---- device taxonomy: stable colour + glyph per type -----------------------------------------
  var TYPES = {
    'Router / gateway':                 { c: '#e5484d', g: '🛡️' }, // shield
    'Printer':                          { c: '#8957e5', g: '🖨️' },
    'IP camera / NVR':                  { c: '#d29922', g: '📹' },
    'NAS / file server':                { c: '#1f6feb', g: '💾' },
    'Media server':                     { c: '#db61a2', g: '🎬' },
    'TV / streaming device':            { c: '#3fb950', g: '📺' },
    'Smart speaker / audio':            { c: '#58a6ff', g: '🔊' },
    'Smart lighting':                   { c: '#f2cc60', g: '💡' },
    'IoT / smart-home device':          { c: '#56d4dd', g: '🏠' },
    'Phone / tablet':                   { c: '#7ee787', g: '📱' },
    'Windows PC':                       { c: '#2f81f7', g: '💻' },
    'Linux host / server':             { c: '#f0883e', g: '🐧' },
    'Apple device':                     { c: '#a5a5a5', g: '' },
    'Single-board computer (Raspberry Pi)': { c: '#c93c6e', g: '🍓' },
    'Virtual machine':                  { c: '#a371f7', g: '🧱' },
    'Host with network services':       { c: '#6e7681', g: '🔌' },
    'Unknown device':                   { c: '#484f58', g: '❓' }
  };
  function typeInfo(t) { return TYPES[t] || TYPES['Unknown device']; }

  // Palette for charts that aren't keyed by device type (vendors, OS...).
  var PALETTE = ['#1f6feb', '#3fb950', '#d29922', '#8957e5', '#db61a2', '#56d4dd', '#f0883e',
                 '#7ee787', '#e5484d', '#a371f7', '#58a6ff', '#f2cc60', '#6e7681'];

  // ---- small DOM helpers -----------------------------------------------------------------------
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function chevron() {
    var ns = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(ns, 'svg');
    s.setAttribute('class', 'rn-section__chev'); s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2.5');
    var p = document.createElementNS(ns, 'path'); p.setAttribute('d', 'M6 9l6 6 6-6');
    p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
    s.appendChild(p); return s;
  }

  var state = { data: null, filter: '', typeFilter: null };
  var dom = {};

  // ---- public API ------------------------------------------------------------------------------
  var api = {
    version: 1,
    load: function (data) {
      if (typeof data === 'string') { try { data = JSON.parse(data); } catch (e) { toast('Not valid JSON'); return; } }
      if (!data || !Array.isArray(data.hosts)) { toast('Not a RusNet report'); return; }
      state.data = data; state.filter = ''; state.typeFilter = null;
      if (dom.search) dom.search.value = '';
      render();
      toast('Loaded ' + data.hosts.length + ' hosts' + (data.scanner_host ? ' from ' + data.scanner_host : ''));
    },
    // A native host sets this to its own file-open routine; the Open button prefers it.
    hostOpen: null,
    setHostOpen: function (fn) { api.hostOpen = fn; },
    // A native host that can run a scan registers it here; doing so reveals the Scan buttons (a
    // plain sandboxed browser can't scan, so without a host they stay hidden).
    hostScan: null,
    setHostScan: function (fn) { api.hostScan = fn; showScanUi(!!fn); },
    // A host toggles the scanning overlay around its scan.
    setScanning: function (on) {
      if (dom.scanning) dom.scanning.classList.toggle('is-active', !!on);
    },
    reset: function () { state.data = null; render(); }
  };
  root.rusnet = api;

  // ---- open / drag-drop ------------------------------------------------------------------------
  function requestOpen() {
    if (typeof api.hostOpen === 'function') { api.hostOpen(); return; }
    dom.fileInput.click();
  }
  function requestScan() {
    if (typeof api.hostScan === 'function') { api.hostScan(); }
  }
  // Reveal or hide every Scan trigger (toolbar + empty state); hosts that can scan call this.
  function showScanUi(on) {
    document.querySelectorAll('[data-rn-scan]').forEach(function (b) {
      b.classList.toggle('rn-hidden', !on);
    });
  }
  function readFile(file) {
    var r = new FileReader();
    r.onload = function () { api.load(r.result); };
    r.onerror = function () { toast('Could not read file'); };
    r.readAsText(file);
  }

  // ---- charts ----------------------------------------------------------------------------------
  function donut(entries, total, colorFn, onSlice) {
    // entries: [{label, value}]. Returns an SVG donut element. onSlice(label) is wired to each
    // segment only when given - a donut whose labels aren't a device type must not drive the
    // device-type filter, or it would filter every host out.
    var ns = 'http://www.w3.org/2000/svg';
    var size = 140, r = 52, cx = size / 2, cy = size / 2, circ = 2 * Math.PI * r;
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);
    svg.setAttribute('width', size); svg.setAttribute('height', size);
    var bg = document.createElementNS(ns, 'circle');
    bg.setAttribute('cx', cx); bg.setAttribute('cy', cy); bg.setAttribute('r', r);
    bg.setAttribute('fill', 'none'); bg.setAttribute('stroke', 'var(--bg3)'); bg.setAttribute('stroke-width', '18');
    svg.appendChild(bg);
    var offset = 0;
    entries.forEach(function (ent, i) {
      if (!ent.value) return;
      var frac = ent.value / (total || 1);
      var seg = document.createElementNS(ns, 'circle');
      seg.setAttribute('cx', cx); seg.setAttribute('cy', cy); seg.setAttribute('r', r);
      seg.setAttribute('fill', 'none'); seg.setAttribute('stroke', colorFn(ent, i));
      seg.setAttribute('stroke-width', '18');
      seg.setAttribute('stroke-dasharray', (frac * circ) + ' ' + circ);
      seg.setAttribute('stroke-dashoffset', -offset * circ);
      seg.setAttribute('transform', 'rotate(-90 ' + cx + ' ' + cy + ')');
      if (onSlice) {
        seg.style.cursor = 'pointer';
        seg.addEventListener('click', function () { onSlice(ent.label); });
      }
      var title = document.createElementNS(ns, 'title'); title.textContent = ent.label + ': ' + ent.value;
      seg.appendChild(title);
      svg.appendChild(seg);
      offset += frac;
    });
    var mid = document.createElementNS(ns, 'text');
    mid.setAttribute('x', cx); mid.setAttribute('y', cy + 2); mid.setAttribute('text-anchor', 'middle');
    mid.setAttribute('fill', 'var(--text)'); mid.setAttribute('font-size', '22'); mid.setAttribute('font-weight', '700');
    mid.textContent = total;
    var sub = document.createElementNS(ns, 'text');
    sub.setAttribute('x', cx); sub.setAttribute('y', cy + 18); sub.setAttribute('text-anchor', 'middle');
    sub.setAttribute('fill', 'var(--text3)'); sub.setAttribute('font-size', '9');
    sub.textContent = 'total';
    svg.appendChild(mid); svg.appendChild(sub);
    return svg;
  }

  function donutCard(title, counts, colorFn, onSlice) {
    var entries = Object.keys(counts).map(function (k) { return { label: k, value: counts[k] }; })
                        .sort(function (a, b) { return b.value - a.value; });
    var total = entries.reduce(function (s, e) { return s + e.value; }, 0);
    var card = el('div', 'rn-card'); card.appendChild(el('h3', null, title));
    var row = el('div', 'rn-chart-row');
    row.appendChild(donut(entries, total, colorFn, onSlice));
    var legend = el('ul', 'rn-legend');
    entries.forEach(function (e, i) {
      var li = el('li');
      var sw = el('span', 'sw'); sw.style.background = colorFn(e, i); li.appendChild(sw);
      var lbl = el('span', 'lbl', e.label); li.appendChild(lbl);
      li.appendChild(el('span', 'n', String(e.value)));
      if (onSlice) {
        li.style.cursor = 'pointer';
        li.addEventListener('click', function () { onSlice(e.label); });
      }
      legend.appendChild(li);
    });
    row.appendChild(legend); card.appendChild(row);
    return card;
  }

  function barCard(title, counts, max) {
    var entries = Object.keys(counts).map(function (k) { return { label: k, value: counts[k] }; })
                        .sort(function (a, b) { return b.value - a.value; }).slice(0, max || 10);
    var top = entries.length ? entries[0].value : 1;
    var card = el('div', 'rn-card'); card.appendChild(el('h3', null, title));
    var bars = el('div', 'rn-bars');
    entries.forEach(function (e) {
      var row = el('div', 'rn-bar');
      row.appendChild(el('div', 'rn-bar__lbl', e.label));
      var track = el('div', 'rn-bar__track');
      var fill = el('div', 'rn-bar__fill'); fill.style.width = Math.max(4, (e.value / top) * 100) + '%';
      track.appendChild(fill); row.appendChild(track);
      row.appendChild(el('div', 'rn-bar__n', String(e.value)));
      bars.appendChild(row);
    });
    if (!entries.length) bars.appendChild(el('div', 'rn-host__row', 'Nothing to show.'));
    card.appendChild(bars);
    return card;
  }

  // ---- network map -----------------------------------------------------------------------------
  function networkMap(hosts) {
    var ns = 'http://www.w3.org/2000/svg';
    var W = 1200, H = 560, cx = W / 2, cy = H / 2;
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'rn-map'); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);

    var center = hosts.filter(function (h) { return h.is_gateway; })[0] ||
                 hosts.filter(function (h) { return h.is_self; })[0];
    var others = hosts.filter(function (h) { return h !== center; });
    var ring = others.length;
    var radius = Math.min(cx, cy) - 70;

    // edges first so nodes sit on top. Positions are kept in a parallel array, never written onto
    // the host objects (they're the same references the detail view and "Copy as JSON" use).
    var edges = [];
    var pts = [];
    others.forEach(function (h, i) {
      var ang = (i / ring) * 2 * Math.PI - Math.PI / 2;
      var x = cx + radius * Math.cos(ang), y = cy + radius * Math.sin(ang);
      pts.push({ x: x, y: y });
      var line = document.createElementNS(ns, 'line');
      line.setAttribute('class', 'rn-edge');
      line.setAttribute('x1', cx); line.setAttribute('y1', cy);
      line.setAttribute('x2', x); line.setAttribute('y2', y);
      line.dataset.ip = h.ip; edges.push(line); svg.appendChild(line);
    });

    function node(h, x, y, big) {
      var info = typeInfo(h.device_type);
      var g = document.createElementNS(ns, 'g'); g.setAttribute('class', 'rn-node');
      g.setAttribute('transform', 'translate(' + x + ',' + y + ')');
      var c = document.createElementNS(ns, 'circle');
      c.setAttribute('r', big ? 26 : 13); c.setAttribute('fill', info.c);
      if (!h.is_up) c.setAttribute('opacity', '0.4');
      g.appendChild(c);
      var t = document.createElementNS(ns, 'text');
      t.setAttribute('text-anchor', 'middle'); t.setAttribute('y', (big ? 26 : 13) + 12);
      t.textContent = h.hostname || h.ip;
      g.appendChild(t);
      var glyph = document.createElementNS(ns, 'text');
      glyph.setAttribute('text-anchor', 'middle'); glyph.setAttribute('y', big ? 6 : 4);
      glyph.setAttribute('font-size', big ? '20' : '11'); glyph.textContent = info.g;
      g.appendChild(glyph);
      var title = document.createElementNS(ns, 'title');
      title.textContent = (h.hostname ? h.hostname + ' - ' : '') + h.ip + '\n' + h.device_type +
                          (h.vendor ? '\n' + h.vendor : '');
      g.appendChild(title);
      g.addEventListener('click', function () { showDetail(h); });
      g.addEventListener('mouseenter', function () {
        edges.forEach(function (ed) { if (ed.dataset.ip === h.ip) ed.classList.add('is-hot'); }); });
      g.addEventListener('mouseleave', function () {
        edges.forEach(function (ed) { ed.classList.remove('is-hot'); }); });
      g.addEventListener('contextmenu', function (ev) { openCtx(ev, h); });
      return g;
    }

    others.forEach(function (h, i) { svg.appendChild(node(h, pts[i].x, pts[i].y, false)); });
    if (center) svg.appendChild(node(center, cx, cy, true));
    return svg;
  }

  // ---- host card -------------------------------------------------------------------------------
  function hostCard(h) {
    var info = typeInfo(h.device_type);
    var card = el('div', 'rn-host'); card.dataset.ip = h.ip;
    var top = el('div', 'rn-host__top');
    var icon = el('div', 'rn-host__icon', info.g); icon.style.borderColor = info.c; top.appendChild(icon);
    var names = el('div'); names.style.minWidth = '0'; names.style.flex = '1';
    names.appendChild(el('div', 'rn-host__name', h.hostname || h.ip));
    names.appendChild(el('div', 'rn-host__ip', h.ip + (h.mac ? '  ·  ' + h.mac : '')));
    top.appendChild(names);
    var up = el('div', 'rn-host__up' + (h.is_up ? '' : ' is-down')); top.appendChild(up);
    card.appendChild(top);

    if (h.vendor) card.appendChild(kvRow('Vendor', h.vendor));
    card.appendChild(kvRow('Type', h.device_type));
    if (h.os_guess) card.appendChild(kvRow('OS (guess)', h.os_guess));
    if (h.ports && h.ports.length) card.appendChild(kvRow('Open ports', h.ports.length + ''));

    if (h.ports && h.ports.length) {
      var tags = el('div', 'rn-host__tags');
      h.ports.slice(0, 8).forEach(function (p) {
        var t = el('span', 'ma-tag', p.number + (p.service ? ' ' + p.service.split(' ')[0] : ''));
        tags.appendChild(t);
      });
      if (h.ports.length > 8) tags.appendChild(el('span', 'ma-tag', '+' + (h.ports.length - 8)));
      card.appendChild(tags);
    }
    card.addEventListener('click', function () { showDetail(h); });
    card.addEventListener('contextmenu', function (ev) { openCtx(ev, h); });
    return card;
  }
  function kvRow(k, v) {
    var row = el('div', 'rn-host__row');
    row.appendChild(el('b', null, k + ': ')); row.appendChild(document.createTextNode(v));
    return row;
  }

  // ---- detail modal ----------------------------------------------------------------------------
  function sub(title, bodyEl, collapsed) {
    var s = el('div', 'rn-sub' + (collapsed ? ' is-collapsed' : ''));
    var head = el('div', 'rn-sub__head'); head.appendChild(chevron());
    head.appendChild(el('span', null, title)); s.appendChild(head);
    var body = el('div', 'rn-sub__body'); body.appendChild(bodyEl); s.appendChild(body);
    head.addEventListener('click', function () { s.classList.toggle('is-collapsed'); });
    return s;
  }

  function showDetail(h) {
    var info = typeInfo(h.device_type);
    dom.detailTitle.textContent = (h.hostname || h.ip);
    var body = dom.detailBody; clear(body);

    var kv = el('dl', 'rn-kv');
    function add(k, v) { if (v == null || v === '') return; kv.appendChild(el('dt', null, k)); kv.appendChild(el('dd', null, v)); }
    add('IP address', h.ip);
    add('Hostname', h.hostname);
    add('MAC address', h.mac);
    add('Vendor', h.vendor);
    add('Device type', h.device_type);
    add('OS (guess)', h.os_guess);
    add('Model', h.model);
    add('Status', h.is_up ? 'Up' : 'Down');
    if (h.rtt_ms != null) add('Round-trip', h.rtt_ms + ' ms');
    if (h.ttl != null) add('Reply TTL', String(h.ttl));
    if (h.sources && h.sources.length) add('Seen via', h.sources.join(', '));
    if (h.is_gateway) add('Role', 'Default gateway');
    if (h.is_self) add('Role', 'This machine');
    body.appendChild(kv);

    if (h.ports && h.ports.length) {
      var table = el('table', 'rn-portlist');
      var thead = el('tr'); ['Port', 'Service', 'Banner'].forEach(function (t) { thead.appendChild(el('th', null, t)); });
      table.appendChild(thead);
      h.ports.forEach(function (p) {
        var tr = el('tr');
        var td0 = el('td'); var code = el('code', null, String(p.number)); td0.appendChild(code); tr.appendChild(td0);
        tr.appendChild(el('td', null, p.service || '-'));
        tr.appendChild(el('td', null, p.banner || '-'));
        table.appendChild(tr);
      });
      body.appendChild(sub('Open ports (' + h.ports.length + ')', table, false));
    }

    if (h.details && Object.keys(h.details).length) {
      var dkv = el('dl', 'rn-kv');
      Object.keys(h.details).forEach(function (k) {
        var v = h.details[k];
        dkv.appendChild(el('dt', null, k));
        dkv.appendChild(el('dd', null, Array.isArray(v) ? v.join(', ') : String(v)));
      });
      body.appendChild(sub('Protocol details', dkv, true));
    }

    var actions = el('div'); actions.style.marginTop = '14px';
    actions.appendChild(linkBtn('Copy IP', function () { copy(h.ip); }));
    if (h.mac) actions.appendChild(linkBtn('Copy MAC', function () { copy(h.mac); }));
    if (hasHttp(h)) actions.appendChild(linkBtn('Open web UI', function () { openHttp(h); }));
    body.appendChild(actions);

    dom.detail.style.display = 'flex';
  }
  function linkBtn(label, fn) {
    var b = el('button', 'ma-tool-btn', label);
    b.style.cssText = 'margin-right:8px;background:var(--bg3);border:2px solid var(--border);color:var(--text);' +
                      'border-radius:8px;padding:6px 12px;font:inherit;font-size:12px;cursor:pointer;';
    b.addEventListener('click', fn); return b;
  }

  // ---- context menu ----------------------------------------------------------------------------
  function openCtx(ev, h) {
    ev.preventDefault();
    var menu = dom.ctx; clear(menu);
    menu.appendChild(ctxLabel(h.hostname || h.ip));
    menu.appendChild(ctxItem('View details', function () { showDetail(h); }));
    menu.appendChild(ctxItem('Copy IP address', function () { copy(h.ip); }));
    if (h.mac) menu.appendChild(ctxItem('Copy MAC address', function () { copy(h.mac); }));
    menu.appendChild(ctxItem('Copy as JSON', function () { copy(JSON.stringify(h, null, 2)); }));
    if (hasHttp(h)) { menu.appendChild(ctxSep()); menu.appendChild(ctxItem('Open web interface', function () { openHttp(h); })); }
    menu.appendChild(ctxSep());
    menu.appendChild(ctxItem('Filter to ' + h.device_type, function () { toggleTypeFilter(h.device_type); }));
    menu.classList.add('is-open');
    var mw = 200, mh = menu.offsetHeight || 260;
    menu.style.left = Math.min(ev.clientX, window.innerWidth - mw - 8) + 'px';
    menu.style.top = Math.min(ev.clientY, window.innerHeight - mh - 8) + 'px';
  }
  function ctxItem(label, fn) { var i = el('div', 'rn-ctx__item', label);
    i.addEventListener('click', function () { closeCtx(); fn(); }); return i; }
  function ctxLabel(t) { return el('div', 'rn-ctx__item rn-ctx__item--muted', t); }
  function ctxSep() { return el('div', 'rn-ctx__sep'); }
  function closeCtx() { dom.ctx.classList.remove('is-open'); }

  // ---- helpers for actions ---------------------------------------------------------------------
  function hasHttp(h) { return (h.ports || []).some(function (p) {
    return [80, 443, 8080, 8443, 8008, 3000, 5000, 9000].indexOf(p.number) >= 0; }); }
  function openHttp(h) {
    var ps = (h.ports || []).map(function (p) { return p.number; });
    var scheme = (ps.indexOf(443) >= 0 || ps.indexOf(8443) >= 0) ? 'https' : 'http';
    var port = scheme === 'https' ? (ps.indexOf(443) >= 0 ? '' : ':8443')
                                   : (ps.indexOf(80) >= 0 ? '' : ':' + ps.filter(function (p) {
                                       return [8080, 8008, 3000, 5000, 9000].indexOf(p) >= 0; })[0]);
    try { window.open(scheme + '://' + h.ip + port, '_blank'); } catch (e) { toast('Host blocked opening a window'); }
  }
  function copy(text) {
    try {
      if (navigator.clipboard) { navigator.clipboard.writeText(text); }
      else { var ta = el('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
             document.execCommand('copy'); document.body.removeChild(ta); }
      toast('Copied');
    } catch (e) { toast('Copy failed'); }
  }
  var toastTimer;
  function toast(msg) {
    dom.toast.textContent = msg; dom.toast.classList.add('is-show');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { dom.toast.classList.remove('is-show'); }, 1900);
  }

  // ---- filters ---------------------------------------------------------------------------------
  function toggleTypeFilter(t) { state.typeFilter = (state.typeFilter === t) ? null : t; render(); }
  function matches(h) {
    if (state.typeFilter && h.device_type !== state.typeFilter) return false;
    if (!state.filter) return true;
    var q = state.filter.toLowerCase();
    var blob = [h.ip, h.hostname, h.mac, h.vendor, h.device_type, h.os_guess, h.model]
      .concat((h.ports || []).map(function (p) { return p.number + ' ' + p.service + ' ' + p.banner; }))
      .join(' ').toLowerCase();
    return blob.indexOf(q) >= 0;
  }

  // ---- master render ---------------------------------------------------------------------------
  function render() {
    var d = state.data;
    if (!d) { dom.empty.classList.remove('rn-hidden'); dom.content.classList.add('rn-hidden'); dom.meta.textContent = ''; return; }
    dom.empty.classList.add('rn-hidden'); dom.content.classList.remove('rn-hidden');

    var when = (d.finished_at || d.started_at || '').replace('T', ' ').slice(0, 19);
    dom.meta.innerHTML = esc(d.scanner_host || '') + '<br>' + esc(when) +
      (d.networks && d.networks.length ? '<br>' + esc(d.networks.join(', ')) : '');

    var hosts = d.hosts.filter(matches);
    var all = d.hosts;
    var up = all.filter(function (h) { return h.is_up; });

    // stats
    clear(dom.stats);
    [['Hosts up', up.length], ['Hosts total', all.length],
     ['Open ports', all.reduce(function (s, h) { return s + (h.ports ? h.ports.length : 0); }, 0)],
     ['Vendors', uniq(all.map(function (h) { return h.vendor; })).length],
     ['Device types', uniq(all.map(function (h) { return h.device_type; })).length],
     ['Networks', (d.networks || []).length]
    ].forEach(function (s) {
      var tile = el('div', 'rn-stat');
      tile.appendChild(el('div', 'rn-stat__val', String(s[1])));
      tile.appendChild(el('div', 'rn-stat__cap', s[0]));
      dom.stats.appendChild(tile);
    });

    // charts
    clear(dom.charts);
    var typeCounts = countBy(all, function (h) { return h.device_type; });
    // Only the device-type donut drives the (device-type) filter; others are display-only.
    dom.charts.appendChild(donutCard('Device types', typeCounts, function (e) { return typeInfo(e.label).c; }, toggleTypeFilter));
    var osCounts = countBy(all.filter(function (h) { return h.os_guess; }), function (h) { return h.os_guess; });
    dom.charts.appendChild(donutCard('Operating systems', osCounts, function (e, i) { return PALETTE[i % PALETTE.length]; }));
    var vendorCounts = countBy(all.filter(function (h) { return h.vendor; }), function (h) { return h.vendor; });
    dom.charts.appendChild(barCard('Top vendors', vendorCounts, 8));
    var portCounts = {};
    all.forEach(function (h) { (h.ports || []).forEach(function (p) {
      var key = p.number + (p.service ? ' ' + p.service.split(' ')[0] : '');
      portCounts[key] = (portCounts[key] || 0) + 1; }); });
    dom.charts.appendChild(barCard('Most common open ports', portCounts, 10));

    // map (uses the filtered set so a type filter focuses it)
    clear(dom.map);
    if (hosts.length) dom.map.appendChild(networkMap(hosts.slice()));
    else dom.map.appendChild(el('div', 'rn-empty', 'No hosts match the current filter.'));

    // devices grouped by type
    clear(dom.devices);
    dom.filterNote.textContent = state.typeFilter ? ('Filtered to: ' + state.typeFilter + '  (click again to clear)') : '';
    var groups = {};
    hosts.forEach(function (h) { (groups[h.device_type] = groups[h.device_type] || []).push(h); });
    Object.keys(groups).sort(function (a, b) { return groups[b].length - groups[a].length; }).forEach(function (type) {
      var info = typeInfo(type);
      var g = el('div', 'rn-group');
      var head = el('div', 'rn-group__head');
      head.appendChild(chevron());
      var dot = el('span', 'rn-group__dot'); dot.style.background = info.c; head.appendChild(dot);
      head.appendChild(el('h3', null, type));
      head.appendChild(el('span', 'rn-section__count', String(groups[type].length)));
      g.appendChild(head);
      var grid = el('div', 'rn-grid');
      groups[type].forEach(function (h) { grid.appendChild(hostCard(h)); });
      g.appendChild(grid);
      head.addEventListener('click', function () { g.classList.toggle('is-collapsed'); });
      dom.devices.appendChild(g);
    });
    if (!hosts.length) dom.devices.appendChild(el('div', 'rn-empty', 'No hosts match the current filter.'));
  }

  function uniq(a) { var s = {}; a.forEach(function (x) { if (x) s[x] = 1; }); return Object.keys(s); }
  function countBy(a, fn) { var o = {}; a.forEach(function (x) { var k = fn(x) || 'Unknown'; o[k] = (o[k] || 0) + 1; }); return o; }

  // ---- collapsible top sections ----------------------------------------------------------------
  function wireSection(section) {
    var head = section.querySelector('.rn-section__head');
    if (head) head.addEventListener('click', function () { section.classList.toggle('is-collapsed'); });
  }

  // ---- boot ------------------------------------------------------------------------------------
  function boot() {
    dom.meta = document.getElementById('rn-meta');
    dom.search = document.getElementById('rn-search');
    dom.empty = document.getElementById('rn-empty');
    dom.content = document.getElementById('rn-content');
    dom.stats = document.getElementById('rn-stats');
    dom.charts = document.getElementById('rn-charts');
    dom.map = document.getElementById('rn-map');
    dom.devices = document.getElementById('rn-devices');
    dom.filterNote = document.getElementById('rn-filter-note');
    dom.detail = document.getElementById('rn-detail');
    dom.detailTitle = document.getElementById('rn-detail-title');
    dom.detailBody = document.getElementById('rn-detail-body');
    dom.ctx = document.getElementById('rn-ctx');
    dom.toast = document.getElementById('rn-toast');
    dom.fileInput = document.getElementById('rn-file');
    dom.drop = document.getElementById('rn-drop');
    dom.scanning = document.getElementById('rn-scanning');

    document.querySelectorAll('.rn-section').forEach(wireSection);
    document.querySelectorAll('[data-rn-open]').forEach(function (b) { b.addEventListener('click', requestOpen); });
    document.querySelectorAll('[data-rn-scan]').forEach(function (b) { b.addEventListener('click', requestScan); });
    dom.fileInput.addEventListener('change', function () { if (this.files[0]) readFile(this.files[0]); this.value = ''; });
    dom.search.addEventListener('input', function () { state.filter = this.value; render(); });

    document.querySelectorAll('[data-rn-close]').forEach(function (b) {
      b.addEventListener('click', function () { dom.detail.style.display = 'none'; }); });
    dom.detail.addEventListener('click', function (e) { if (e.target === dom.detail) dom.detail.style.display = 'none'; });

    document.addEventListener('click', closeCtx);
    document.addEventListener('scroll', closeCtx, true);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeCtx(); dom.detail.style.display = 'none'; } });

    // drag-drop (plain-browser fallback)
    var dragDepth = 0;
    window.addEventListener('dragenter', function (e) { e.preventDefault(); dragDepth++; dom.drop.classList.add('is-active'); });
    window.addEventListener('dragover', function (e) { e.preventDefault(); });
    window.addEventListener('dragleave', function (e) { e.preventDefault(); if (--dragDepth <= 0) dom.drop.classList.remove('is-active'); });
    window.addEventListener('drop', function (e) {
      e.preventDefault(); dragDepth = 0; dom.drop.classList.remove('is-active');
      if (e.dataTransfer.files && e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]);
    });

    // Data may be embedded by the report generator, or injected later by a native host.
    if (root.__RUSNET_DATA__) { api.load(root.__RUSNET_DATA__); }
    else render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})(typeof window !== 'undefined' ? window : this);
