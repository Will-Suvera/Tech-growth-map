/* ============================================
   GP Practice Growth Dashboard — Application
   ============================================ */

// Config is loaded dynamically from data/live_customers.json
let LIVE_CUSTOMER_ODS = new Set();
const ANNUAL_TARGET = 1500;
const QUARTERLY_TARGETS = [
    { q: "Q1", target: 300, deadline: "2026-03-31" },
    { q: "Q2", target: 600, deadline: "2026-06-30" },
    { q: "Q3", target: 1000, deadline: "2026-09-30" },
    { q: "Q4", target: 1500, deadline: "2026-12-31" }
];

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

// Practice layer groups (ordered: unsigned < waitlist < live)
const layers = {
    notSigned: L.layerGroup().addTo(map),
    waitlist: L.layerGroup().addTo(map),
    live: L.layerGroup().addTo(map)
};

// ============================================
// MARKER STYLES
// ============================================

const MARKER_STYLES = {
    live:      { color: '#22c55e', fillColor: '#22c55e', radius: 5, fillOpacity: 0.9, weight: 1.5, opacity: 0.8 },
    waitlist:  { color: '#f59e0b', fillColor: '#f59e0b', radius: 4, fillOpacity: 0.8, weight: 1.5, opacity: 0.8 },
    notSigned: { color: '#818cf8', fillColor: '#6366f1', radius: 3, fillOpacity: 0.5, weight: 0.5, opacity: 0.8 },
};

// ============================================
// DATA LOADING
// ============================================

const markersByOds = {};
let allPractices = [];
let currentLiveOds = LIVE_CUSTOMER_ODS;
let currentWaitlistOds = new Set();

async function loadData() {
    try {
        const [practicesResp, waitlistResp, liveResp] = await Promise.all([
            fetch('data/practices_geocoded.json', { cache: 'no-cache' }),
            fetch('data/waitlist_ods.json', { cache: 'no-cache' }),
            fetch('data/live_customers.json', { cache: 'no-cache' }),
        ]);

        const practices = await practicesResp.json();
        const waitlistArr = await waitlistResp.json();
        const liveArr = await liveResp.json();

        LIVE_CUSTOMER_ODS = new Set(liveArr.map(c => c.toUpperCase()));
        currentLiveOds = LIVE_CUSTOMER_ODS;
        const waitlistOds = new Set(waitlistArr.map(c => c.toUpperCase()));

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
        const status = LIVE_CUSTOMER_ODS.has(ods) ? 'live' : waitlistOds.has(ods) ? 'waitlist' : 'notSigned';
        const marker = L.circleMarker([p.lat, p.lng], MARKER_STYLES[status]);
        marker.bindPopup(() => buildPopup(p, ods));
        layers[status].addLayer(marker);
        markersByOds[ods] = { marker, layer: status };
    });

    updateStats(practices, LIVE_CUSTOMER_ODS, waitlistOds);
    document.getElementById('loading').style.display = 'none';
}

function buildPopup(p, ods) {
    const status = currentLiveOds.has(ods) ? 'live' : currentWaitlistOds.has(ods) ? 'waitlist' : 'not-signed';
    const label = status === 'live' ? 'Live Customer' : status === 'waitlist' ? 'On Waitlist' : 'Not Signed Up';
    return `
        <div class="popup-title">${p.name}</div>
        <div class="popup-ods">${p.ods} &bull; ${p.postcode}</div>
        ${p.patients ? `<div class="popup-patients">Patients: ${Number(p.patients).toLocaleString()}</div>` : ''}
        ${p.pcn_name ? `<div class="popup-pcn">PCN: ${p.pcn_name}${p.pcn_code ? ' (' + p.pcn_code + ')' : ''}</div>` : ''}
        ${p.icb ? `<div class="popup-icb">ICB: ${p.icb}</div>` : ''}
        <div class="popup-status ${status}">${label}</div>`;
}

function updateStats(practices, liveOds, waitlistOds) {
    let liveCount = 0, waitlistCount = 0, livePatients = 0, waitlistPatients = 0;
    practices.forEach(p => {
        const ods = p.ods.toUpperCase();
        if (liveOds.has(ods)) { liveCount++; livePatients += (p.patients || 0); }
        else if (waitlistOds.has(ods)) { waitlistCount++; waitlistPatients += (p.patients || 0); }
    });

    const pipeline = liveCount + waitlistCount;
    const pct = Math.round((pipeline / ANNUAL_TARGET) * 100);
    const coverage = ((pipeline / practices.length) * 100).toFixed(1);

    setText('hero-number', pipeline.toLocaleString());
    setText('live-count', liveCount);
    setText('waitlist-count', waitlistCount);
    setText('patient-lives', (livePatients + waitlistPatients).toLocaleString());
    setText('live-patients', livePatients.toLocaleString());
    setText('waitlist-patients', waitlistPatients.toLocaleString());
    setText('total-practices', practices.length.toLocaleString());
    setText('coverage-pct', coverage + '%');
    setText('map-live-count', liveCount);
    setText('map-waitlist-count', waitlistCount);
    setText('progress-pct', pct + '%');
    setText('progress-remaining', (ANNUAL_TARGET - pipeline > 0 ? (ANNUAL_TARGET - pipeline).toLocaleString() : '0') + ' remaining');
    document.getElementById('progress-fill').style.width = Math.min(pct, 100) + '%';
    setText('last-updated', new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }));
    renderQuarterly(pipeline);
}

function setText(id, val) { document.getElementById(id).textContent = val; }

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

function animateNumber(id, target) {
    const el = document.getElementById(id);
    const start = performance.now();
    (function update(now) {
        const p = Math.min((now - start) / 1200, 1);
        el.textContent = Math.round((1 - Math.pow(1 - p, 3)) * target).toLocaleString();
        if (p < 1) requestAnimationFrame(update);
    })(start);
}

// ============================================
// TIME TRAVEL
// ============================================

const snapshotCache = {};

function applySnapshot(liveOds, waitlistOds) {
    currentLiveOds = liveOds;
    currentWaitlistOds = waitlistOds;
    for (const [ods, entry] of Object.entries(markersByOds)) {
        const status = liveOds.has(ods) ? 'live' : waitlistOds.has(ods) ? 'waitlist' : 'notSigned';
        entry.marker.setStyle(MARKER_STYLES[status]);
        entry.marker.setRadius(MARKER_STYLES[status].radius);
        if (entry.layer !== status) {
            layers[entry.layer].removeLayer(entry.marker);
            layers[status].addLayer(entry.marker);
            entry.layer = status;
        }
    }
    updateStats(allPractices, liveOds, waitlistOds);
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
            new Set(snap.live_ods.map(c => c.toUpperCase())),
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
        detail.innerHTML = `<span style="color:#16a34a">${d.practices.live} live</span> &bull; <span style="color:#d97706">${d.practices.waitlist} waitlist</span> &bull; <strong>${d.practices.pipeline} total</strong>`;
    } else {
        detail.innerHTML = `<span style="color:#16a34a">${d.patients.live.toLocaleString()}</span> &bull; <span style="color:#d97706">${d.patients.waitlist.toLocaleString()}</span> &bull; <strong>${d.patients.pipeline.toLocaleString()}</strong>`;
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

// ============================================
// INIT
// ============================================
loadData();
