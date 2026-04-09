import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { MAP_CENTER, MAP_ZOOM, MARKER_STYLES, ICB_STYLES } from '../constants'
import MapTopBar from './MapTopBar'

const snapshotCache = {}

async function loadSnapshot(dateStr) {
  if (snapshotCache[dateStr]) return snapshotCache[dateStr]
  try {
    const resp = await fetch(`/snapshots/${dateStr}.json`, { cache: 'no-cache' })
    if (!resp.ok) return null
    const data = await resp.json()
    snapshotCache[dateStr] = data
    return data
  } catch {
    return null
  }
}

function getStatus(ods, liveOds, waitlistOds, fullPlannerOds) {
  if (fullPlannerOds && fullPlannerOds.has(ods)) return 'fullPlanner'
  if (liveOds.has(ods)) return 'planner'
  if (waitlistOds.has(ods)) return 'waitlist'
  return 'notSigned'
}

function escapeHtml(str) {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

function buildPopupContent(p, status) {
  const labels = {
    fullPlanner: 'Live - Full Planner',
    planner: 'Live - Partial Planner',
    waitlist: 'On Waitlist',
    notSigned: 'Not Signed Up',
  }
  const label = labels[status] || 'Not Signed Up'
  const statusClass = (status === 'fullPlanner' || status === 'planner') ? 'live' : status === 'notSigned' ? 'not-signed' : status
  return `
    <div class="popup-title">${escapeHtml(p.name)}</div>
    <div class="popup-ods">${escapeHtml(p.ods)} &bull; ${escapeHtml(p.postcode)}</div>
    ${p.patients ? `<div class="popup-patients">Patients: ${Number(p.patients).toLocaleString()}</div>` : ''}
    ${p.pcn_name ? `<div class="popup-pcn">PCN: ${escapeHtml(p.pcn_name)}${p.pcn_code ? ' (' + escapeHtml(p.pcn_code) + ')' : ''}</div>` : ''}
    ${p.icb ? `<div class="popup-icb">ICB: ${escapeHtml(p.icb)}</div>` : ''}
    <div class="popup-status ${statusClass}">${label}</div>`
}

export default function DashboardMap({ practices, liveOds, fullPlannerOds, waitlistOds, setLiveOds, setFullPlannerOds, setWaitlistOds, timeline }) {
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const layersRef = useRef({})
  const markersRef = useRef({})
  const currentOdsRef = useRef({ live: liveOds, fullPlanner: fullPlannerOds, waitlist: waitlistOds })
  const [liveCounted, setLiveCounted] = useState(0)
  const [waitlistCounted, setWaitlistCounted] = useState(0)

  // Keep ref in sync for popup callbacks
  useEffect(() => {
    currentOdsRef.current = { live: liveOds, fullPlanner: fullPlannerOds, waitlist: waitlistOds }
  }, [liveOds, fullPlannerOds, waitlistOds])

  // Initialize Leaflet map (once)
  useEffect(() => {
    const container = mapRef.current
    if (!container || container._leaflet_id) return

    const map = L.map(container, {
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      zoomControl: true,
      attributionControl: true,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map)

    map.createPane('icbPane')
    map.getPane('icbPane').style.zIndex = 350

    let selectedIcb = null

    fetch('/data/icb_boundaries.geojson', { cache: 'no-cache' })
      .then(r => r.json())
      .then(geojson => {
        if (!mapInstanceRef.current) return
        L.geoJSON(geojson, {
          pane: 'icbPane',
          bubblingMouseEvents: true,
          style: ICB_STYLES.default,
          onEachFeature(feature, layer) {
            layer.on('mouseover', function () {
              if (selectedIcb !== this) { this.setStyle(ICB_STYLES.hover); this.bringToFront() }
              this.bindTooltip(feature.properties.name, {
                className: 'icb-tooltip', sticky: true, direction: 'top', offset: [0, -10], opacity: 0.95,
              }).openTooltip()
            })
            layer.on('mouseout', function () {
              if (selectedIcb !== this) this.setStyle(ICB_STYLES.default)
              this.closeTooltip()
            })
            layer.on('click', function (e) {
              L.DomEvent.stopPropagation(e)
              if (selectedIcb && selectedIcb !== this) selectedIcb.setStyle(ICB_STYLES.default)
              if (selectedIcb === this) { this.setStyle(ICB_STYLES.default); selectedIcb = null }
              else { this.setStyle(ICB_STYLES.active); this.bringToFront(); selectedIcb = this }
            })
          },
        }).addTo(map)
      })
      .catch(e => console.warn('ICB boundaries not loaded:', e))

    map.on('click', () => {
      if (selectedIcb) { selectedIcb.setStyle(ICB_STYLES.default); selectedIcb = null }
    })

    layersRef.current = {
      notSigned: L.layerGroup().addTo(map),
      waitlist: L.layerGroup().addTo(map),
      planner: L.layerGroup().addTo(map),
      fullPlanner: L.layerGroup().addTo(map),
    }

    mapInstanceRef.current = map

    return () => {
      map.remove()
      mapInstanceRef.current = null
    }
  }, [])

  // Create markers once when practices load
  useEffect(() => {
    if (!mapInstanceRef.current || practices.length === 0) return

    const layers = layersRef.current
    Object.values(layers).forEach(l => l.clearLayers())
    markersRef.current = {}

    let live = 0, waitlist = 0
    practices.forEach(p => {
      const ods = p.ods.toUpperCase()
      const status = getStatus(ods, liveOds, waitlistOds, fullPlannerOds)
      if (status === 'fullPlanner' || status === 'planner') live++
      if (status === 'waitlist') waitlist++
      const marker = L.circleMarker([p.lat, p.lng], MARKER_STYLES[status])
      marker.bindPopup(() => {
        const cur = currentOdsRef.current
        const currentStatus = getStatus(ods, cur.live, cur.waitlist, cur.fullPlanner)
        return buildPopupContent(p, currentStatus)
      })
      layers[status].addLayer(marker)
      markersRef.current[ods] = { marker, layer: status, practice: p }
    })
    setLiveCounted(live)
    setWaitlistCounted(waitlist)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [practices])

  // Update marker styles in-place when liveOds/waitlistOds change (from snapshot load)
  useEffect(() => {
    if (Object.keys(markersRef.current).length === 0) return

    const layers = layersRef.current
    let live = 0, waitlist = 0

    for (const [ods, entry] of Object.entries(markersRef.current)) {
      const status = getStatus(ods, liveOds, waitlistOds, fullPlannerOds)
      if (status === 'fullPlanner' || status === 'planner') live++
      if (status === 'waitlist') waitlist++
      entry.marker.setStyle(MARKER_STYLES[status])
      entry.marker.setRadius(MARKER_STYLES[status].radius)
      if (entry.layer !== status) {
        layers[entry.layer].removeLayer(entry.marker)
        layers[status].addLayer(entry.marker)
        entry.layer = status
      }
    }
    setLiveCounted(live)
    setWaitlistCounted(waitlist)
  }, [liveOds, fullPlannerOds, waitlistOds])

  // Handle timeline snapshot changes — try to load full snapshot for map dot updates
  const debounceRef = useRef(null)
  const { sliderIdx, timelineData } = timeline

  useEffect(() => {
    if (!timelineData.length || !practices.length) return
    const entry = timelineData[sliderIdx]
    if (!entry) return

    let cancelled = false
    clearTimeout(debounceRef.current)

    debounceRef.current = setTimeout(async () => {
      const snap = await loadSnapshot(entry.date)
      if (cancelled) return
      if (!snap?.live_ods || !snap?.waitlist_ods) return

      const newLive = new Set(snap.live_ods.map(c => c.toUpperCase()))
      const newWaitlist = new Set(snap.waitlist_ods.map(c => c.toUpperCase()))
      setLiveOds(newLive)
      setWaitlistOds(newWaitlist)
    }, 80)

    return () => {
      cancelled = true
      clearTimeout(debounceRef.current)
    }
  }, [sliderIdx, timelineData, practices, setLiveOds, setWaitlistOds])

  // Use timeline entry counts for the overlay chips when available and not at latest
  const isLatest = timelineData.length === 0 || sliderIdx === timelineData.length - 1
  const currentEntry = timelineData[sliderIdx]
  const liveCount = !isLatest && currentEntry ? currentEntry.practices.live : liveCounted
  const waitlistCount = !isLatest && currentEntry ? currentEntry.practices.waitlist : waitlistCounted

  return (
    <div className="map-container">
      <div id="map" ref={mapRef}></div>
      <MapTopBar
        liveCount={liveCount}
        waitlistCount={waitlistCount}
        timeline={timeline}
      />
    </div>
  )
}
