/* ============================================
   GP Practice Growth Dashboard — Application
   ============================================ */

// Live customer ODS sets are loaded from data/live_customers*.json.
// Two tiers:
//   - LIVE_FULL_PLANNER_ODS  → all-planner-functionality customers (subset)
//   - LIVE_PLANNER_ODS       → planner-only customers (live minus full planner)
let LIVE_PLANNER_ODS = new Set();
let LIVE_FULL_PLANNER_ODS = new Set();

const ANNUAL_TARGET = 1500;
const QUARTERLY_TARGETS = [
    { q: "Q1", target: 300, deadline: "2026-03-31" },
    { q: "Q2", target: 600, deadline: "2026-06-30" },
    { q: "Q3", target: 1000, deadline: "2026-09-30" },
    { q: "Q4", target: 1500, deadline: "2026-12-31" }
];
// Show "stale" warning if the data refresh timestamp is older than this.
const STALE_THRESHOLD_MS = 15 * 60 * 1000; // 15 minutes

// ============================================
// MAP SETUP
// ============================================

const map = L.map('map', { center: [52.8, -1.5], zoom: 6, zoomControl: true, attributionControl: true });

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO', subdomains: 'abcd', maxZoom: 19
}).addTo(map);

// ICB boundaries sit below practice markers
map.createPane('icbPane');
map.getPane('icbPane').style.zIndex = 350;

const ICB_STYLES = {
    default: { color: '#1e2a4a', weight: 1.2, fillColor: 'rgba(30,42,74,0.04)', fillOpacity: 1 },
    hover:   { color: '#1e2a4a', weight: 2, fillColor: 'rgba(30,42,74,0.1)', fillOpacity: 1 },
    active:  { color: '#1e2a4a', weight: 2.5, fillColor: 'rgba(30,42,74,0.18)', fillOpacity: 1 },
};

let selectedIcb = null;

fetch('data/icb_boundaries.geojson', { cache: 'no-cache' })
    .then(r => r.json())
    .then(geojson => {
        L.geoJSON(geojson, {
            pane: 'icbPane', bubblingMouseEvents: true,
            style: ICB_STYLES.default,
            onEachFeature(feature, layer) {
                layer.on('mouseover', function () {
                    if (selectedIcb !== this) { this.setStyle(ICB_STYLES.hover); this.bringToFront(); }
                    this.bindTooltip(feature.properties.name, {
                        className: 'icb-tooltip', sticky: true, direction: 'top', offset: [0, -10], opacity: 0.95
                    }).openTooltip();
                });
                layer.on('mouseout', function () {
                    if (selectedIcb !== this) this.setStyle(ICB_STYLES.default);
                    this.closeTooltip();
                });
                layer.on('click', function (e) {
                    L.DomEvent.stopPropagation(e);
                    if (selectedIcb && selectedIcb !== this) selectedIcb.setStyle(ICB_STYLES.default);
                    if (selectedIcb === this) { this.setStyle(ICB_STYLES.default); selectedIcb = null; }
                    else { this.setStyle(ICB_STYLES.active); this.bringToFront(); selectedIcb = this; }
                });
            }
        }).addTo(map);
    })
    .catch(e => console.warn('ICB boundaries not loaded:', e));

map.on('click', () => { if (selectedIcb) { selectedIcb.setStyle(ICB_STYLES.default); selectedIcb = null; } });

// Practice layer groups (ordered: unsigned bottom → fullPlanner top)
const layers = {
    notSigned: L.layerGroup().addTo(map),
    waitlist: L.layerGroup().addTo(map),
    planner: L.layerGroup().addTo(map),
    fullPlanner: L.layerGroup().addTo(map)
};

// ============================================
// MARKER STYLES
// ============================================

const MARKER_STYLES = {
    fullPlanner: { color: '#15803d', fillColor: '#22c55e', radius: 7, fillOpacity: 1.0, weight: 2.5, opacity: 1.0 },
    planner:     { color: '#22c55e', fillColor: '#22c55e', radius: 5, fillOpacity: 0.9, weight: 1.5, opacity: 0.8 },
    waitlist:    { color: '#f59e0b', fillColor: '#f59e0b', radius: 4, fillOpacity: 0.8, weight: 1.5, opacity: 0.8 },
    // Reduced from fillOpacity 0.5 / opacity 0.8 to make blue dots slightly less opaque.
    notSigned:   { color: '#818cf8', fillColor: '#6366f1', radius: 3, fillOpacity: 0.32, weight: 0.5, opacity: 0.55 },
};

function tierForOds(ods) {
    if (LIVE_FULL_PLANNER_ODS.has(ods)) return 'fullPlanner';
    if (LIVE_PLANNER_ODS.has(ods)) return 'planner';
    if (currentWaitlistOds.has(ods)) return 'waitlist';
    return 'notSigned';
}

// ============================================
// DATA LOADING
// ============================================

const markersByOds = {};
let allPractices = [];
let currentWaitlistOds = new Set();
let dataTimestamp = null;

async function loadData() {
    try {
        const [practicesResp, waitlistResp, liveResp, fullPlannerResp, timelineResp] = await Promise.all([
            fetch('data/practices_geocoded.json', { cache: 'no-cache' }),
            fetch('data/waitlist_ods.json', { cache: 'no-cache' }),
            fetch('data/live_customers.json', { cache: 'no-cache' }),
            fetch('data/live_customers_full_planner.json', { cache: 'no-cache' }),
            fetch('snapshots/timeline.json', { cache: 'no-cache' }),
        ]);

        const practices = await practicesResp.json();
        const waitlistArr = await waitlistResp.json();
        const liveArr = await liveResp.json();
        const fullPlannerArr = await fullPlannerResp.json();
        const timeline = await timelineResp.json();

        const liveAll = new Set(liveArr.map(c => c.toUpperCase()));
        LIVE_FULL_PLANNER_ODS = new Set(fullPlannerArr.map(c => c.toUpperCase()));
        // Planner-only = live minus full-planner.
        LIVE_PLANNER_ODS = new Set([...liveAll].filter(c => !LIVE_FULL_PLANNER_ODS.has(c)));

        const waitlistOds = new Set(waitlistArr.map(c => c.toUpperCase()));

        // Use the data refresh timestamp from timeline.json, NOT the viewer's
        // current clock. Stops the dashboard from claiming data is fresh when
        // it isn't.
        if (timeline && timeline.length) {
            dataTimestamp = timeline[timeline.length - 1].timestamp;
        }

        renderDashboard(practices, waitlistOds);
    } catch (error) {
        console.error('Error loading data:', error);
        document.getElementById('loading').innerHTML =
            `<div style="color:#ef4444;font-size:14px;">Error loading data.<br><small style="color:#94a3b8;">${error.message}</small></div>`;
    }
}

// ============================================
// RENDERING
// ============================================

function renderDashboard(practices, waitlistOds) {
    allPractices = practices;
    currentWaitlistOds = waitlistOds;

    practices.forEach(p => {
        const ods = p.ods.toUpperCase();
        const tier = tierForOds(ods);
        const marker = L.circleMarker([p.lat, p.lng], MARKER_STYLES[tier]);
        marker.bindPopup(() => buildPopup(p, ods));
        layers[tier].addLayer(marker);
        markersByOds[ods] = { marker, layer: tier };
    });

    updateStats(practices);
    document.getElementById('loading').style.display = 'none';
}

function buildPopup(p, ods) {
    const tier = tierForOds(ods);
    const labels = {
        fullPlanner: 'Live - Full Planner',
        planner: 'Live - Planner',
        waitlist: 'On Waitlist',
        notSigned: 'Not Signed Up'
    };
    const cssClass = tier === 'fullPlanner' || tier === 'planner' ? 'live'
                   : tier === 'waitlist' ? 'waitlist' : 'not-signed';
    return `
        <div class="popup-title">${p.name}</div>
        <div class="popup-ods">${p.ods} &bull; ${p.postcode}</div>
        ${p.patients ? `<div class="popup-patients">Patients: ${Number(p.patients).toLocaleString()}</div>` : ''}
        ${p.pcn_name ? `<div class="popup-pcn">PCN: ${p.pcn_name}${p.pcn_code ? ' (' + p.pcn_code + ')' : ''}</div>` : ''}
        ${p.icb ? `<div class="popup-icb">ICB: ${p.icb}</div>` : ''}
        <div class="popup-status ${cssClass}">${labels[tier]}</div>`;
}

function updateStats(practices) {
    let liveFullCount = 0, livePlannerCount = 0, waitlistCount = 0;
    let liveFullPatients = 0, livePlannerPatients = 0, waitlistPatients = 0;

    practices.forEach(p => {
        const ods = p.ods.toUpperCase();
        const pat = p.patients || 0;
        if (LIVE_FULL_PLANNER_ODS.has(ods)) {
            liveFullCount++; liveFullPatients += pat;
        } else if (LIVE_PLANNER_ODS.has(ods)) {
            livePlannerCount++; livePlannerPatients += pat;
        } else if (currentWaitlistOds.has(ods)) {
            waitlistCount++; waitlistPatients += pat;
        }
    });

    const liveTotal = liveFullCount + livePlannerCount;
    const pipeline = liveTotal + waitlistCount;
    const totalLivePatients = liveFullPatients + livePlannerPatients;
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100);
    const coverage = ((pipeline / practices.length) * 100).toFixed(1);

    setText('hero-number', pipeline.toLocaleString());
    setText('live-count', liveTotal);
    setText('live-full-planner-count', liveFullCount);
    setText('live-planner-count', livePlannerCount);
    setText('waitlist-count', waitlistCount);
    setText('patient-lives', (totalLivePatients + waitlistPatients).toLocaleString());
    setText('live-patients', totalLivePatients.toLocaleString());
    setText('waitlist-patients', waitlistPatients.toLocaleString());
    setText('total-practices', practices.length.toLocaleString());
    setText('coverage-pct', coverage + '%');
    setText('map-live-count', liveTotal);
    setText('map-waitlist-count', waitlistCount);
    setText('progress-pct', pct + '%');
    setText('progress-remaining', (ANNUAL_TARGET - pipeline > 0 ? (ANNUAL_TARGET - pipeline).toLocaleString() : '0') + ' remaining');
    document.getElementById('progress-fill').style.width = Math.min(pct, 100) + '%';

    renderLastUpdated();
    renderQuarterly(pipeline);
}

function renderLastUpdated() {
    const el = document.getElementById('last-updated');
    if (!el) return;
    if (!dataTimestamp) {
        el.textContent = 'unknown';
        el.classList.add('stale');
        return;
    }
    const ts = new Date(dataTimestamp);
    const ageMs = Date.now() - ts.getTime();
    const stale = ageMs > STALE_THRESHOLD_MS;
    const opts = { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
    const display = ts.toLocaleString('en-GB', opts);
    const ageMin = Math.floor(ageMs / 60000);
    el.textContent = stale ? `${display} (${ageMin}m ago — STALE)` : `${display} (${ageMin}m ago)`;
    el.classList.toggle('stale', stale);
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function renderQuarterly(total) {
    const today = new Date();
    document.getElementById('quarterly-rows').innerHTML = QUARTERLY_TARGETS.map(qt => {
        const deadline = new Date(qt.deadline);
        const isPast = today > deadline;
        const isCurrent = !isPast && (QUARTERLY_TARGETS.indexOf(qt) === 0 || today > new Date(QUARTERLY_TARGETS[QUARTERLY_TARGETS.indexOf(qt) - 1].deadline));
        const progress = Math.min((total / qt.target) * 100, 100);
        const achieved = total >= qt.target;
        const cls = achieved ? 'achieved' : isCurrent ? 'on-track' : 'behind';
        return `<div class="quarter-row">
            <div class="quarter-label">${qt.q}</div>
            <div class="quarter-bar-container"><div class="quarter-bar-fill ${cls}" style="width:${progress}%"></div></div>
            <div class="quarter-target"><span class="actual ${cls}">${achieved ? qt.target : total}</span> / ${qt.target}</div>
        </div>`;
    }).join('');
}

// ============================================
// TIME TRAVEL
// ============================================

const snapshotCache = {};

function applySnapshot(liveOds, fullPlannerOds, waitlistOds) {
    const liveAll = new Set(liveOds);
    LIVE_FULL_PLANNER_ODS = new Set(fullPlannerOds);
    LIVE_PLANNER_ODS = new Set([...liveAll].filter(c => !LIVE_FULL_PLANNER_ODS.has(c)));
    currentWaitlistOds = waitlistOds;

    for (const [ods, entry] of Object.entries(markersByOds)) {
        const tier = tierForOds(ods);
        entry.marker.setStyle(MARKER_STYLES[tier]);
        entry.marker.setRadius(MARKER_STYLES[tier].radius);
        if (entry.layer !== tier) {
            layers[entry.layer].removeLayer(entry.marker);
            layers[tier].addLayer(entry.marker);
            entry.layer = tier;
        }
    }
    updateStats(allPractices);
}

async function loadSnapshot(dateStr) {
    if (snapshotCache[dateStr]) return snapshotCache[dateStr];
    try {
        const resp = await fetch(`snapshots/${dateStr}.json`, { cache: 'no-cache' });
        const data = await resp.json();
        snapshotCache[dateStr] = data;
        return data;
    } catch { return null; }
}

let sliderDebounce = null;
async function onTimelineSliderChange(idx) {
    const d = timelineData[idx];
    if (!d) return;
    const snap = await loadSnapshot(d.date);
    if (snap && snap.live_ods && snap.waitlist_ods) {
        applySnapshot(
            snap.live_ods.map(c => c.toUpperCase()),
            (snap.live_full_planner_ods || []).map(c => c.toUpperCase()),
            new Set(snap.waitlist_ods.map(c => c.toUpperCase()))
        );
    }
}

// ============================================
// TIMELINE SLIDER + MONTH PICKER
// ============================================

let timelineData = [];
let timelineMonths = [];
let currentMonthIdx = 0;
let currentMetric = 'practices';

function setTimelineMetric(metric) {
    currentMetric = metric;
    document.querySelectorAll('.timeline-btn').forEach(b => b.classList.toggle('active', b.dataset.metric === metric));
    updateTimelineDetail(document.getElementById('timeline-slider').value);
}

function getMonthsFromData(data) {
    const months = [], seen = new Set();
    data.forEach((d, i) => {
        const ym = d.date.substring(0, 7);
        if (!seen.has(ym)) { seen.add(ym); months.push({ ym, firstIdx: i, lastIdx: i }); }
        else months[months.length - 1].lastIdx = i;
    });
    return months;
}

function updateMonthLabel() {
    const m = timelineMonths[currentMonthIdx];
    if (!m) return;
    setText('month-label', new Date(m.ym + '-01T00:00:00').toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }));
    document.getElementById('month-prev').disabled = currentMonthIdx <= 0;
    document.getElementById('month-next').disabled = currentMonthIdx >= timelineMonths.length - 1;
}

function changeMonth(dir) {
    const idx = currentMonthIdx + dir;
    if (idx < 0 || idx >= timelineMonths.length) return;
    currentMonthIdx = idx;
    updateMonthLabel();
    const slider = document.getElementById('timeline-slider');
    slider.value = timelineMonths[idx].lastIdx;
    updateTimelineDetail(slider.value);
    onTimelineSliderChange(slider.value);
}

function updateTimelineDetail(idx) {
    const d = timelineData[idx];
    if (!d) return;
    setText('timeline-date', new Date(d.date + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }));
    const ym = d.date.substring(0, 7);
    const mIdx = timelineMonths.findIndex(m => m.ym === ym);
    if (mIdx >= 0 && mIdx !== currentMonthIdx) { currentMonthIdx = mIdx; updateMonthLabel(); }

    const detail = document.getElementById('timeline-detail');
    if (currentMetric === 'practices') {
        const live = d.practices.live ?? ((d.practices.live_planner || 0) + (d.practices.live_full_planner || 0));
        detail.innerHTML = `<span style="color:#16a34a">${live} live</span> &bull; <span style="color:#d97706">${d.practices.waitlist} waitlist</span> &bull; <strong>${d.practices.pipeline} total</strong>`;
    } else {
        const live = d.patients.live ?? ((d.patients.live_planner || 0) + (d.patients.live_full_planner || 0));
        detail.innerHTML = `<span style="color:#16a34a">${live.toLocaleString()}</span> &bull; <span style="color:#d97706">${d.patients.waitlist.toLocaleString()}</span> &bull; <strong>${d.patients.pipeline.toLocaleString()}</strong>`;
    }
}

// Load timeline data
fetch('snapshots/timeline.json', { cache: 'no-cache' })
    .then(r => r.json())
    .then(data => {
        timelineData = data;
        timelineMonths = getMonthsFromData(data);
        currentMonthIdx = timelineMonths.length - 1;
        updateMonthLabel();
        const slider = document.getElementById('timeline-slider');
        slider.max = data.length - 1;
        slider.value = data.length - 1;
        slider.oninput = function () {
            updateTimelineDetail(this.value);
            clearTimeout(sliderDebounce);
            sliderDebounce = setTimeout(() => onTimelineSliderChange(this.value), 200);
        };
        updateTimelineDetail(data.length - 1);
    })
    .catch(e => console.warn('Timeline not loaded:', e));

// Re-check staleness every minute so the badge updates without a page reload.
setInterval(renderLastUpdated, 60 * 1000);

// ============================================
// INIT
// ============================================
loadData();
