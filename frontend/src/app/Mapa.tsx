"use client";
import { useEffect, useRef } from "react";

// Leaflet carregado do CDN (sem dependência npm). Pinos coloridos; um pode ser arrastável.
export type Pino = { lat: number; lon: number; cor: string; rotulo: string };
type L = any; // eslint-disable-line @typescript-eslint/no-explicit-any

let carregando: Promise<L> | null = null;
function leaflet(): Promise<L> {
  const w = window as unknown as { L?: L };
  if (w.L) return Promise.resolve(w.L);
  if (!carregando) carregando = new Promise((ok, erro) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    js.onload = () => ok(w.L); js.onerror = erro;
    document.head.appendChild(js);
  });
  return carregando;
}

export default function Mapa({ pinos, arrastavel, onMover, linha, className = "h-64" }:
  { pinos: Pino[]; arrastavel?: number; onMover?: (lat: number, lon: number) => void; linha?: [number, number][]; className?: string }) {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<L>(null);
  const camada = useRef<L>(null);
  const moverRef = useRef(onMover); moverRef.current = onMover;
  const enquadrado = useRef("");

  useEffect(() => {
    let vivo = true;
    leaflet().then(Lf => {
      if (!vivo || !div.current) return;
      if (!mapa.current) {
        mapa.current = Lf.map(div.current, { zoomControl: true });
        Lf.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa.current);
        camada.current = Lf.layerGroup().addTo(mapa.current);
      }
      camada.current.clearLayers();
      // trajeto (linha azul) quando houver pontos de GPS
      if (linha && linha.length > 1) Lf.polyline(linha, { color: "#2563eb", weight: 4, opacity: 0.8 }).addTo(camada.current);
      const validos = pinos.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon));
      validos.forEach((p, i) => {
        const icone = Lf.divIcon({ className: "", iconSize: [22, 22], iconAnchor: [11, 11],
          html: `<div style="width:22px;height:22px;border-radius:50%;background:${p.cor};border:3px solid #fff;box-shadow:0 1px 4px #0007"></div>` });
        const m = Lf.marker([p.lat, p.lon], { icon: icone, draggable: i === arrastavel, title: p.rotulo }).bindTooltip(p.rotulo).addTo(camada.current);
        if (i === arrastavel) m.on("dragend", () => { const ll = m.getLatLng(); moverRef.current?.(ll.lat, ll.lng); });
      });
      // só reenquadra quando o conjunto de pinos muda de forma relevante (não a cada arraste/GPS)
      const chave = validos.map(p => p.rotulo).join("|") + (arrastavel != null ? "" : validos.map(p => p.lat.toFixed(2) + p.lon.toFixed(2)).join());
      if (validos.length && chave !== enquadrado.current) {
        enquadrado.current = chave;
        if (validos.length === 1 && !(linha && linha.length > 1)) mapa.current.setView([validos[0].lat, validos[0].lon], 17);
        else mapa.current.fitBounds([...validos.map(p => [p.lat, p.lon]), ...(linha ?? [])], { padding: [40, 40] });
      }
      setTimeout(() => mapa.current?.invalidateSize(), 50);
    }).catch(() => {});
    return () => { vivo = false; };
  }, [pinos, arrastavel, linha]);

  useEffect(() => () => { mapa.current?.remove(); mapa.current = null; }, []);
  return <div ref={div} className={`w-full overflow-hidden rounded-xl border ${className}`} />;
}
