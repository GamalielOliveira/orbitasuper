"use client";
// Aba "Entregas" do gerente: uma linha por entrega, com filtros, ordenação e detalhe ao clicar.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Mapa from "../Mapa";

const API = "/api";
type Metas = { loja: number; rota: number; porta: number; total: number };
type Entrega = {
  numero: string; status: string; cliente: string; bairro: string | null; entregador: string | null; criado_em: string;
  dia_semana: string; faixa: string; loja: number | null; rota: number | null; porta: number | null; total: number;
  em_rota: boolean; no_prazo: boolean | null; atrasado: boolean;
  clima: { temp: number | null; chuva_mm: number; rotulo: string; icone: string } | null; chuva: boolean | null; estacao: string;
  rota_esperada: number | null; esperado_suspeito: boolean; delta_rota: number | null; delta_pct: number | null;
  dist_km: number | null; vel_media: number | null; vel_max: number | null; parado_min: number | null; paradas: number | null; reta_km: number | null; desvio: number | null;
  sem_sinal_min: number | null; pontos: number | null; esparso: boolean | null;
  motivo: { codigo: string; rotulo: string; explicacao: string; fatores: string[]; mostrar: boolean; informado: boolean };
  ocorrencias: { tipo: string; rotulo: string; texto: string | null; criado_em: string; entregador: string | null }[];
};
type Col = "numero" | "criado_em" | "dia_semana" | "faixa" | "cliente" | "bairro" | "entregador" | "chuva" | "rota" | "rota_esperada" | "delta_rota" | "porta" | "total" | "dist_km" | "vel_media" | "parado_min";

// Formatos
const mmss = (s: number | null) => s == null ? "—" : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const num = (v: number | null, suf = "") => v == null ? "—" : `${v.toLocaleString("pt-BR")}${suf}`;
const media = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
// Cor do texto vs meta: verde até a meta, amarelo até +50%, vermelho além
const corCel = (s: number | null, meta: number) => s == null ? "" : s <= meta ? "text-green-700" : s <= meta * 1.5 ? "text-yellow-700 font-semibold" : "text-red-700 font-bold";
const corBarra = (s: number | null, meta: number) => s == null ? "bg-gray-300" : s <= meta ? "bg-green-500" : s <= meta * 1.5 ? "bg-yellow-400" : "bg-red-500";
const FAIXAS = ["manhã", "almoço", "tarde", "noite"];
const ESTACOES = ["verão", "outono", "inverno", "primavera"];
// Cor do selo de motivo
const corMotivo = (c: string) => c.startsWith("informado_") ? "bg-rose-100 text-rose-800" : c === "ok" ? "bg-green-100 text-green-800" : c === "separacao_lenta" ? "bg-blue-100 text-blue-800"
  : c === "porta" ? "bg-purple-100 text-purple-800" : c === "sem_sinal" ? "bg-gray-200 text-gray-700" : "bg-orange-100 text-orange-800";
// Diferença de rota (real - esperado) com sinal: "+2:10" / "-0:40"
const delta = (s: number | null) => s == null ? "—" : `${s < 0 ? "-" : "+"}${mmss(Math.abs(s))}`;
// Cor da diferença: verde se foi igual/mais rápido, amarelo até +20%, vermelho acima
const corDelta = (pct: number | null) => pct == null ? "" : pct <= 0 ? "text-green-700" : pct <= 20 ? "text-yellow-700" : "text-red-700 font-semibold";
// Texto do clima para a dica (tooltip)
const climaTxt = (e: Entrega) => e.clima ? `${e.clima.rotulo} · ${e.clima.temp ?? "—"}°C · chuva ${e.clima.chuva_mm.toLocaleString("pt-BR")} mm` : "Clima ainda não carregado";
const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

// Filtro que pode vir de fora (ex.: clique num grupo da aba Padrões)
export type FiltroEntregas = { entregador?: string; bairro?: string; faixa?: string; dia?: string; chuva?: string; motivo?: string };

export default function Entregas({ token, consulta, filtro = {} }: { token: string; consulta: string; filtro?: FiltroEntregas }) {
  const [dados, setDados] = useState<{ metas: Metas; entregas: Entrega[] } | null>(null);
  // Filtros (ficam no estado: a atualização automática não apaga)
  const [fEnt, setFEnt] = useState(filtro.entregador ?? ""); const [fBairro, setFBairro] = useState(filtro.bairro ?? ""); const [fFaixa, setFFaixa] = useState(filtro.faixa ?? ""); const [fDia, setFDia] = useState(filtro.dia ?? "");
  const [soAtrasados, setSoAtrasados] = useState(false); const [busca, setBusca] = useState("");
  const [fMotivo, setFMotivo] = useState(filtro.motivo ?? ""); // filtro por motivo provável
  const [fChuva, setFChuva] = useState(filtro.chuva ?? ""); const [fEstacao, setFEstacao] = useState(""); // filtros de clima
  const [ordem, setOrdem] = useState<{ col: Col; asc: boolean }>({ col: "criado_em", asc: false });
  const [aberto, setAberto] = useState<string | null>(null); // pedido com o detalhe aberto

  // Busca as entregas do período a cada 15 s (o GPS das concluídas fica em cache no backend)
  const carregar = useCallback(async () => {
    const r = await fetch(`${API}/gerente/entregas${consulta}`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) setDados(await r.json());
  }, [token, consulta]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 15000); return () => clearInterval(t); }, [carregar]);

  const linhas = useMemo(() => {
    if (!dados) return [];
    const b = busca.trim().toLowerCase();
    const l = dados.entregas.filter(e => (!fEnt || e.entregador === fEnt) && (!fBairro || e.bairro === fBairro) && (!fFaixa || e.faixa === fFaixa) &&
      (!fDia || e.dia_semana === fDia) && (!soAtrasados || e.atrasado) &&
      (!fMotivo || (e.motivo.mostrar && e.motivo.rotulo === fMotivo)) && (!fChuva || (fChuva === "sim" ? e.chuva === true : e.chuva === false)) && (!fEstacao || e.estacao === fEstacao) &&
      (!b || e.numero.toLowerCase().includes(b) || (e.cliente ?? "").toLowerCase().includes(b) || (e.bairro ?? "").toLowerCase().includes(b)));
    return [...l].sort((a, c) => {
      const x = a[ordem.col], y = c[ordem.col];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (x < y ? -1 : x > y ? 1 : 0) * (ordem.asc ? 1 : -1);
    });
  }, [dados, fEnt, fBairro, fFaixa, fDia, soAtrasados, busca, fChuva, fEstacao, fMotivo, ordem]);

  if (!dados) return <p className="text-gray-500">Carregando…</p>;
  const M = dados.metas;
  const unicos = (k: "entregador" | "bairro") => [...new Set(dados.entregas.map(e => e[k]).filter(Boolean))] as string[];
  const sel = "rounded-lg bg-gray-100 px-2 py-2";
  const cab: [Col, string][] = [["numero", "Pedido"], ["criado_em", "Data / hora"], ["dia_semana", "Dia"], ["faixa", "Faixa"], ["cliente", "Cliente"], ["bairro", "Bairro"],
    ["entregador", "Entregador"], ["chuva", "Clima"], ["rota", "Rota"], ["rota_esperada", "Esperado"], ["delta_rota", "Δ rota"], ["porta", "Porta"], ["total", "Total"], ["dist_km", "Dist. km"], ["vel_media", "Vel. média"], ["parado_min", "Parado"]];

  return (<>
    {/* Barra de filtros */}
    <div className="mb-2 flex flex-wrap items-center gap-3 rounded-xl bg-white p-3 text-sm shadow">
      <select value={fEnt} onChange={e => setFEnt(e.target.value)} className={sel}><option value="">Todos os entregadores</option>{unicos("entregador").map(n => <option key={n}>{n}</option>)}</select>
      <select value={fBairro} onChange={e => setFBairro(e.target.value)} className={sel}><option value="">Todos os bairros</option>{unicos("bairro").map(n => <option key={n}>{n}</option>)}</select>
      <select value={fFaixa} onChange={e => setFFaixa(e.target.value)} className={sel}><option value="">Todas as faixas</option>{FAIXAS.map(n => <option key={n}>{n}</option>)}</select>
      <select value={fDia} onChange={e => setFDia(e.target.value)} className={sel}><option value="">Todos os dias</option>{DIAS.map(n => <option key={n}>{n}</option>)}</select>
      <select value={fMotivo} onChange={e => setFMotivo(e.target.value)} className={sel}><option value="">Todos os motivos</option>
        {[...new Set(dados.entregas.filter(e => e.motivo.mostrar).map(e => e.motivo.rotulo))].map(n => <option key={n}>{n}</option>)}</select>
      <select value={fChuva} onChange={e => setFChuva(e.target.value)} className={sel}><option value="">Chuva: todas</option><option value="sim">Com chuva</option><option value="nao">Sem chuva</option></select>
      <select value={fEstacao} onChange={e => setFEstacao(e.target.value)} className={sel}><option value="">Todas as estações</option>{ESTACOES.map(n => <option key={n}>{n}</option>)}</select>
      <label className="flex items-center gap-1"><input type="checkbox" checked={soAtrasados} onChange={e => setSoAtrasados(e.target.checked)} /> Só atrasados</label>
      <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="Buscar pedido, cliente ou bairro" className="w-60 rounded-lg bg-gray-100 px-3 py-2 outline-none" />
      {(fEnt || fBairro || fFaixa || fDia || soAtrasados || busca || fChuva || fEstacao || fMotivo) && <button onClick={() => { setFEnt(""); setFBairro(""); setFFaixa(""); setFDia(""); setSoAtrasados(false); setBusca(""); setFChuva(""); setFEstacao(""); setFMotivo(""); }} className="text-blue-600 underline">Limpar</button>}
      <span className="ml-auto text-gray-500">{linhas.length} de {dados.entregas.length} entregas · clique numa linha para detalhes</span>
    </div>

    {/* Tabela compacta: uma linha por entrega */}
    <div className="overflow-x-auto rounded-xl bg-white shadow">
      <table className="w-full whitespace-nowrap text-sm">
        <thead className="bg-gray-50 text-left text-gray-500">
          <tr>
            {cab.map(([c, nome]) => (
              <th key={c} onClick={() => setOrdem(o => ({ col: c, asc: o.col === c ? !o.asc : true }))} className="cursor-pointer select-none px-2 py-2 hover:text-gray-900">
                {nome}{ordem.col === c ? (ordem.asc ? " ▲" : " ▼") : ""}
              </th>))}
            <th className="px-2 py-2">Prazo</th>
            <th className="px-2 py-2">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map(e => (
            <Fragment key={e.numero}>
              <tr onClick={() => setAberto(a => a === e.numero ? null : e.numero)}
                className={`cursor-pointer border-t hover:bg-blue-50 ${aberto === e.numero ? "bg-blue-50" : e.atrasado ? "bg-red-50/50" : ""}`}>
                <td className="px-2 py-1.5 font-semibold">{aberto === e.numero ? "▾" : "▸"} {e.numero}</td>
                <td className="px-2">{new Date(e.criado_em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })}</td>
                <td className="px-2">{e.dia_semana}</td>
                <td className="px-2">{e.faixa}</td>
                <td className="max-w-[140px] truncate px-2">{e.cliente}</td>
                <td className="max-w-[140px] truncate px-2">{e.bairro ?? "—"}</td>
                <td className="px-2">{e.entregador ?? "—"}</td>
                <td className="px-2 text-center" title={climaTxt(e)}>{e.clima ? e.clima.icone : "—"}</td>
                <td className={`px-2 font-mono ${corCel(e.rota, M.rota)}`}>{mmss(e.rota)}</td>
                <td className="px-2 font-mono text-gray-600" title={e.esperado_suspeito ? "endereço muito perto da loja" : ""}>{mmss(e.rota_esperada)}</td>
                <td className={`px-2 font-mono ${corDelta(e.delta_pct)}`} title={e.esperado_suspeito ? "endereço muito perto da loja" : e.delta_pct == null ? "" : `${e.delta_pct > 0 ? "+" : ""}${e.delta_pct}% vs esperado`}>{delta(e.delta_rota)}</td>
                <td className={`px-2 font-mono ${corCel(e.porta, M.porta)}`}>{mmss(e.porta)}</td>
                <td className={`px-2 font-mono ${corCel(e.total, M.total)}`}>{mmss(e.total)}{e.em_rota && <span className="text-gray-400">…</span>}</td>
                <td className="px-2 text-right">{num(e.dist_km)}</td>
                <td className="px-2 text-right">{num(e.vel_media, " km/h")}</td>
                <td className="px-2 text-right" title={e.sem_sinal_min ? `inclui ${num(e.sem_sinal_min)} min sem sinal/parado` : ""}>{num(e.parado_min, " min")}{e.sem_sinal_min ? <span className="text-gray-400"> ⚠</span> : null}</td>
                <td className="px-2 text-center">{e.em_rota ? "🛵" : e.no_prazo ? "✅" : "⏰"}</td>
                {/* selo só quando atrasou ou a rota passou 20% do esperado; senão fica em branco */}
                <td className="px-2">{e.motivo.mostrar && <span title={e.motivo.explicacao} className={`rounded-full px-2 py-0.5 text-xs font-semibold ${corMotivo(e.motivo.codigo)}`}>{e.motivo.informado && "🗣 "}{e.motivo.rotulo}</span>}</td>
              </tr>
              {aberto === e.numero && <tr><td colSpan={18} className="bg-gray-50 p-0"><Detalhe e={e} metas={M} token={token} /></td></tr>}
            </Fragment>))}
          {!linhas.length && <tr><td colSpan={18} className="p-4 text-center text-gray-400">Nenhuma entrega com esses filtros.</td></tr>}
        </tbody>
        {/* Rodapé: médias do que está filtrado */}
        {linhas.length > 0 && (
          <tfoot className="border-t-2 bg-gray-50 font-semibold">
            <tr>
              <td className="px-2 py-2" colSpan={8}>Média ({linhas.length})</td>
              {(() => { const v = media(linhas.map(e => e.rota)); return <td className={`px-2 font-mono ${corCel(v == null ? null : Math.round(v), M.rota)}`}>{mmss(v == null ? null : Math.round(v))}</td>; })()}
              {(() => { const v = media(linhas.map(e => e.rota_esperada)); return <td className="px-2 font-mono text-gray-600">{mmss(v == null ? null : Math.round(v))}</td>; })()}
              {(() => { // Δ do conjunto: (soma real - soma esperado) / soma esperado, só entregas com previsão válida
                const ok = linhas.filter(e => e.rota != null && e.rota_esperada != null); const esp = ok.reduce((a, e) => a + e.rota_esperada!, 0);
                const dif = ok.reduce((a, e) => a + e.rota! - e.rota_esperada!, 0); const p = esp ? Math.round(100 * dif / esp) : null;
                return <td className={`px-2 font-mono ${corDelta(p)}`} title={p == null ? "" : `${p > 0 ? "+" : ""}${p}% vs esperado`}>{delta(ok.length ? Math.round(dif / ok.length) : null)}</td>; })()}
              {(["porta", "total"] as const).map(k => { const v = media(linhas.map(e => e[k])); return <td key={k} className={`px-2 font-mono ${corCel(v == null ? null : Math.round(v), M[k])}`}>{mmss(v == null ? null : Math.round(v))}</td>; })}
              <td className="px-2 text-right">{num(media(linhas.map(e => e.dist_km)) == null ? null : +media(linhas.map(e => e.dist_km))!.toFixed(2))}</td>
              <td className="px-2 text-right">{num(media(linhas.map(e => e.vel_media)) == null ? null : +media(linhas.map(e => e.vel_media))!.toFixed(1), " km/h")}</td>
              <td className="px-2 text-right">{num(media(linhas.map(e => e.parado_min)) == null ? null : +media(linhas.map(e => e.parado_min))!.toFixed(1), " min")}</td>
              <td className="px-2 text-center">{(() => { const f = linhas.filter(e => e.no_prazo != null); return f.length ? `${Math.round(100 * f.filter(e => e.no_prazo).length / f.length)}%` : "—"; })()}</td>
              <td />
            </tr>
          </tfoot>)}
      </table>
    </div>
  </>);
}

// Painel que abre embaixo da linha: linha do tempo, mapa do trajeto e números do GPS
function Detalhe({ e, metas, token }: { e: Entrega; metas: Metas; token: string }) {
  const [rota, setRota] = useState<{ cliente: { lat: number; lon: number } | null; loja: { lat: number; lon: number } | null; pontos: { lat: number; lon: number }[] } | null>(null);
  useEffect(() => {
    fetch(`${API}/gerente/entregas/${e.numero}/rota`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.ok ? r.json() : null).then(setRota);
  }, [e.numero, token]);
  const linha = useMemo(() => (rota?.pontos ?? []).map(p => [p.lat, p.lon] as [number, number]), [rota]);
  const pinos = useMemo(() => {
    const l = [];
    if (rota?.loja) l.push({ lat: rota.loja.lat, lon: rota.loja.lon, cor: "#1e3a8a", rotulo: "Loja" });
    else if (linha.length) l.push({ lat: linha[0][0], lon: linha[0][1], cor: "#1e3a8a", rotulo: "Saída" });
    if (rota?.cliente) l.push({ lat: rota.cliente.lat, lon: rota.cliente.lon, cor: "#dc2626", rotulo: "Cliente" });
    return l;
  }, [linha, rota]);

  // Linha do tempo: largura de cada etapa proporcional ao tempo gasto
  const etapas = [["Loja", e.loja, metas.loja], ["Rota", e.rota, metas.rota], ["Porta", e.porta, metas.porta]] as const;
  const soma = etapas.reduce((a, [, s]) => a + (s ?? 0), 0) || 1;
  const Info = ({ t, v }: { t: string; v: string }) => <div className="rounded-lg bg-white p-2 shadow-sm"><p className="text-xs text-gray-500">{t}</p><p className="font-semibold">{v}</p></div>;

  return (
    <div className="grid grid-cols-[1fr_420px] gap-4 p-4">
      <div>
        <p className="mb-1 text-xs font-semibold text-gray-500">LINHA DO TEMPO · total {mmss(e.total)} (meta {mmss(metas.total)})</p>
        <div className="mb-1 flex h-7 overflow-hidden rounded-lg text-xs font-semibold text-white">
          {etapas.map(([nome, s, meta]) => s != null && s > 0 && (
            <div key={nome} className={`flex items-center justify-center ${corBarra(s, meta)}`} style={{ width: `${Math.max(100 * s / soma, 8)}%` }} title={`${nome}: ${mmss(s)} (meta ${mmss(meta)})`}>{nome} {mmss(s)}</div>))}
        </div>
        <p className="mb-4 text-xs text-gray-500">{etapas.map(([n, , m]) => `${n} meta ${mmss(m)}`).join(" · ")}</p>

        <p className="mb-1 text-xs font-semibold text-gray-500">GPS{e.pontos != null && <span className={`ml-2 font-normal ${e.esparso ? "text-orange-600" : ""}`}>· {e.pontos} pontos{e.esparso ? " (poucos pontos de GPS)" : ""}</span>}</p>
        <div className="mb-4 grid grid-cols-5 gap-2 text-sm">
          <Info t="Distância" v={num(e.dist_km, " km")} />
          <Info t="Vel. média / máx." v={e.vel_media == null ? "—" : `${num(e.vel_media)} / ${num(e.vel_max)} km/h`} />
          <Info t="Parado" v={e.parado_min == null ? "—" : `${num(e.parado_min)} min · ${e.paradas} parada(s) >1 min${e.sem_sinal_min ? ` · ${num(e.sem_sinal_min)} min sem sinal/parado` : ""}`} />
          <Info t="Rota real × esperada" v={e.esperado_suspeito ? "— (endereço muito perto da loja)" : e.rota_esperada == null ? "—" : `${mmss(e.rota)} × ${mmss(e.rota_esperada)} (${e.delta_pct == null ? "—" : `${e.delta_pct > 0 ? "+" : ""}${e.delta_pct}%`})`} />
          <div title={e.esparso ? "poucos pontos de GPS" : ""}><Info t="Linha reta / desvio" v={e.reta_km == null ? "—" : `${num(e.reta_km)} km · ${e.desvio == null ? "—" : `${num(e.desvio)}x`}`} /></div>
        </div>

        {/* Espaços reservados para os próximos cartões */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Info t={`Clima · ${e.estacao}`} v={e.clima ? `${e.clima.icone} ${e.clima.rotulo} · ${e.clima.temp ?? "—"}°C · ${e.clima.chuva_mm.toLocaleString("pt-BR")} mm` : "— (carregando)"} />
          {/* Motivo provável: causa principal + explicação + até 2 fatores */}
          <div className="rounded-lg bg-white p-2 shadow-sm">
            <p className="text-xs text-gray-500">Motivo provável</p>
            <p><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${corMotivo(e.motivo.codigo)}`}>{e.motivo.rotulo}</span></p>
            <p className="mt-1 text-xs text-gray-600">{e.motivo.explicacao}</p>
            {e.motivo.fatores.length > 0 && <p className="mt-1 text-xs text-gray-500">Também: {e.motivo.fatores.join(" · ")}</p>}
            {/* Ocorrências avisadas pelo entregador, com horário */}
            {e.ocorrencias.length > 0 && (
              <ul className="mt-2 border-t pt-1 text-xs text-gray-700">
                {e.ocorrencias.map((o, i) => (
                  <li key={i}>🗣 {new Date(o.criado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })} · <b>{o.rotulo}</b>{o.texto ? ` — “${o.texto}”` : ""}{o.entregador ? ` (${o.entregador})` : ""}</li>))}
              </ul>)}
          </div>
        </div>
      </div>
      <div>
        {linha.length > 1 ? <Mapa pinos={pinos} linha={linha} className="h-64" />
          : <div className="flex h-64 items-center justify-center rounded-xl border bg-white text-sm text-gray-400">{rota ? "Sem trajeto de GPS para esta entrega" : "Carregando trajeto…"}</div>}
      </div>
    </div>);
}
