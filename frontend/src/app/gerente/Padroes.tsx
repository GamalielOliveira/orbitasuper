"use client";
// Aba "Padrões": agrupa as entregas do período para mostrar onde os atrasos se concentram.
import { useCallback, useEffect, useMemo, useState } from "react";
import type { FiltroEntregas } from "./Entregas";

const API = "/api";
// Só os campos que usamos daqui (a lista vem de GET /gerente/entregas)
type E = { numero: string; entregador: string | null; bairro: string | null; faixa: string; dia_semana: string; chuva: boolean | null;
  rota: number | null; rota_esperada: number | null; delta_pct: number | null; total: number; no_prazo: boolean | null; em_rota: boolean;
  motivo: { rotulo: string; mostrar: boolean } };
type Grupo = { nome: string; n: number; pct: number | null; rota: number | null; delta: number | null; total: number | null; filtro?: FiltroEntregas };

const FAIXAS = ["manhã", "almoço", "tarde", "noite"];
const DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const mmss = (s: number | null) => s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const media = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
const ruim = (g: Grupo) => (g.pct != null && g.pct < 70) || (g.delta != null && g.delta > 20);   // destaque vermelho

// Δ do grupo vs esperado: (soma real - soma esperado) / soma esperado, só entregas com previsão válida
// (média de porcentagens distorce quando uma previsão é muito pequena)
function deltaGrupo(l: E[]) {
  const ok = l.filter(e => e.rota != null && e.rota_esperada != null);
  const esp = ok.reduce((a, e) => a + e.rota_esperada!, 0);
  return esp ? 100 * ok.reduce((a, e) => a + e.rota! - e.rota_esperada!, 0) / esp : null;
}
// Calcula os números de um grupo de entregas concluídas
function resumir(nome: string, l: E[], filtro?: FiltroEntregas): Grupo {
  const ok = l.filter(e => e.no_prazo).length;
  return { nome, n: l.length, pct: l.length ? Math.round(100 * ok / l.length) : null, rota: media(l.map(e => e.rota)),
    delta: deltaGrupo(l), total: media(l.map(e => e.total)), filtro };
}
// Agrupa por uma chave (entregas sem chave ficam de fora)
function agrupar(l: E[], chave: (e: E) => string | null, filtro: (k: string) => FiltroEntregas | undefined, ordem?: string[]) {
  const m = new Map<string, E[]>();
  l.forEach(e => { const k = chave(e); if (k) m.set(k, [...(m.get(k) ?? []), e]); });
  const g = [...m.entries()].map(([k, v]) => resumir(k, v, filtro(k)));
  return ordem ? g.sort((a, b) => ordem.indexOf(a.nome) - ordem.indexOf(b.nome)) : g.sort((a, b) => b.n - a.n);
}

export default function Padroes({ token, consulta, rotulo, abrir }: { token: string; consulta: string; rotulo: string; abrir: (f: FiltroEntregas) => void }) {
  const [lista, setLista] = useState<E[] | null>(null);
  const carregar = useCallback(async () => {
    const r = await fetch(`${API}/gerente/entregas${consulta}`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) setLista((await r.json()).entregas);
  }, [token, consulta]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 30000); return () => clearInterval(t); }, [carregar]);

  // Só entregas concluídas entram nos padrões (as em rota ainda não têm resultado)
  const feitas = useMemo(() => (lista ?? []).filter(e => !e.em_rota && e.no_prazo != null), [lista]);
  const secoes = useMemo(() => [
    { titulo: "Por faixa horária", g: agrupar(feitas, e => e.faixa, k => ({ faixa: k }), FAIXAS) },
    { titulo: "Por dia da semana", g: agrupar(feitas, e => e.dia_semana, k => ({ dia: k }), DIAS) },
    { titulo: "Por bairro (top 10)", g: agrupar(feitas, e => e.bairro, k => ({ bairro: k })).slice(0, 10) },
    { titulo: "Chuva × sem chuva", g: agrupar(feitas, e => e.chuva == null ? null : e.chuva ? "Com chuva" : "Sem chuva", k => ({ chuva: k === "Com chuva" ? "sim" : "nao" })) },
    { titulo: "Por motivo", g: agrupar(feitas, e => e.motivo.mostrar ? e.motivo.rotulo : "Sem atraso", k => k === "Sem atraso" ? undefined : { motivo: k }), motivo: true },
    { titulo: "Por entregador", g: agrupar(feitas, e => e.entregador, k => ({ entregador: k })) },
  ], [feitas]);

  if (!lista) return <p className="text-gray-500">Carregando…</p>;
  if (!feitas.length) return <p className="rounded-xl bg-white p-6 text-center text-gray-500 shadow">Nenhuma entrega concluída em {rotulo}.</p>;

  return (<>
    <p className="mb-3 text-sm text-gray-500">{feitas.length} entregas concluídas · {rotulo} · clique num grupo para ver as entregas · <span className="text-red-700">vermelho</span> = menos de 70% no prazo ou rota 20% acima do esperado</p>

    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
      {/* Mapa de calor: dia da semana × faixa horária (% no prazo e quantidade) */}
      <section className="rounded-xl bg-white p-3 shadow">
        <h3 className="mb-2 font-bold">Dia × faixa <span className="text-xs font-normal text-gray-500">% no prazo (entregas)</span></h3>
        <table className="w-full text-center text-xs">
          <thead><tr><th />{FAIXAS.map(f => <th key={f} className="pb-1 font-semibold text-gray-500">{f}</th>)}</tr></thead>
          <tbody>
            {DIAS.map(d => (
              <tr key={d}>
                <td className="pr-2 text-left font-semibold text-gray-500">{d}</td>
                {FAIXAS.map(f => {
                  const l = feitas.filter(e => e.dia_semana === d && e.faixa === f);
                  const p = l.length ? Math.round(100 * l.filter(e => e.no_prazo).length / l.length) : null;
                  const cor = p == null ? "bg-gray-50 text-gray-300" : p >= 90 ? "bg-green-200" : p >= 70 ? "bg-yellow-200" : "bg-red-300";
                  return <td key={f} className="p-0.5">
                    <button disabled={!l.length} onClick={() => abrir({ dia: d, faixa: f })} title={l.length ? `${l.length} entrega(s)` : "sem entregas"}
                      className={`w-full rounded py-1.5 ${cor} ${l.length ? "hover:ring-2 hover:ring-slate-500" : ""}`}>
                      {p == null ? "·" : <>{p}%<span className="ml-1 opacity-60">({l.length})</span></>}
                    </button></td>;
                })}
              </tr>))}
          </tbody>
        </table>
      </section>

      {/* Uma seção (tabela pequena) por tipo de agrupamento */}
      {secoes.map(s => (
        <section key={s.titulo} className="rounded-xl bg-white p-3 shadow">
          <h3 className="mb-2 font-bold">{s.titulo}</h3>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-gray-500">
              <tr><th className="pb-1">Grupo</th><th className="text-right">Entr.</th>{s.motivo && <th className="text-right">Part.</th>}<th className="text-right">No prazo</th><th className="text-right">Rota</th><th className="text-right">Δ esp.</th><th className="text-right">Total</th></tr>
            </thead>
            <tbody>
              {s.g.map(g => (
                <tr key={g.nome} onClick={() => g.filtro && abrir(g.filtro)}
                  className={`border-t ${g.filtro ? "cursor-pointer hover:bg-blue-50" : ""} ${ruim(g) ? "bg-red-50 text-red-800" : ""}`}>
                  <td className="max-w-[160px] truncate py-1" title={g.nome}>
                    {g.nome}{g.n < 5 && <span className="ml-1 text-[10px] text-gray-400">amostra pequena</span>}
                  </td>
                  <td className="text-right">{g.n}</td>
                  {s.motivo && <td className="text-right">{Math.round(100 * g.n / feitas.length)}%</td>}
                  <td className={`text-right font-semibold ${g.pct != null && g.pct < 70 ? "text-red-700" : ""}`}>{g.pct == null ? "—" : `${g.pct}%`}</td>
                  <td className="text-right font-mono">{mmss(g.rota)}</td>
                  <td className={`text-right ${g.delta != null && g.delta > 20 ? "font-semibold text-red-700" : ""}`}>{g.delta == null ? "—" : `${g.delta > 0 ? "+" : ""}${Math.round(g.delta)}%`}</td>
                  <td className="text-right font-mono">{mmss(g.total)}</td>
                </tr>))}
            </tbody>
          </table>
        </section>))}
    </div>
  </>);
}
