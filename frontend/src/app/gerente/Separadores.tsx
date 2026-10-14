"use client";
// Aba "Separadores": desempenho de quem separa os pedidos, no período escolhido.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

const API = "/api";
type Ped = { numero: string; criado_em: string; itens: number; sep_seg: number | null; loja_seg: number | null; faltas: number; subs: number; reembolso: number };
type Sep = { matricula: string; nome: string; pedidos: number; itens: number; sep_medio: number | null; loja_medio: number | null; itens_min: number | null;
  faltas: number; subs: number; reembolso: number; loja_no_prazo_pct: number | null; em_andamento: string | null; lista: Ped[] };
type Dados = { meta_loja: number; separadores: Sep[]; top_faltas: { nome: string; sku: string; vezes: number; unidades: number }[] };
type Col = "nome" | "pedidos" | "itens" | "sep_medio" | "loja_medio" | "itens_min" | "faltas" | "subs" | "reembolso" | "loja_no_prazo_pct";

const mmss = (s: number | null) => s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const corLoja = (s: number | null, meta: number) => s == null ? "" : s <= meta ? "text-green-700" : s <= meta * 1.5 ? "text-yellow-700 font-semibold" : "text-red-700 font-bold";

export default function Separadores({ token, consulta, rotulo }: { token: string; consulta: string; rotulo: string }) {
  const [d, setD] = useState<Dados | null>(null);
  const [ordem, setOrdem] = useState<{ col: Col; asc: boolean }>({ col: "pedidos", asc: false });
  const [aberto, setAberto] = useState<string | null>(null);   // separador com a lista de pedidos aberta

  const carregar = useCallback(async () => {
    const r = await fetch(`${API}/gerente/separadores${consulta}`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) setD(await r.json());
  }, [token, consulta]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 15000); return () => clearInterval(t); }, [carregar]);

  const linhas = useMemo(() => !d ? [] : [...d.separadores].sort((a, b) => {
    const x = a[ordem.col], y = b[ordem.col];
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * (ordem.asc ? 1 : -1);
  }), [d, ordem]);

  if (!d) return <p className="text-gray-500">Carregando…</p>;
  const M = d.meta_loja;
  // Totais do rodapé: somas e médias ponderadas pelos pedidos
  const tot = linhas.reduce((a, s) => ({ pedidos: a.pedidos + s.pedidos, itens: a.itens + s.itens, faltas: a.faltas + s.faltas, subs: a.subs + s.subs, reembolso: a.reembolso + s.reembolso }),
    { pedidos: 0, itens: 0, faltas: 0, subs: 0, reembolso: 0 });
  const todos = linhas.flatMap(s => s.lista);
  const med = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const sepTot = todos.reduce((a, p) => a + (p.sep_seg ?? 0), 0);
  const lojaOk = todos.filter(p => p.loja_seg != null);
  const cab: [Col, string][] = [["nome", "Separador"], ["pedidos", "Pedidos"], ["itens", "Itens"], ["sep_medio", "Separação méd."], ["loja_medio", "Loja méd."],
    ["itens_min", "Itens/min"], ["faltas", "Faltas"], ["subs", "Substit."], ["reembolso", "Reembolsos"], ["loja_no_prazo_pct", `Loja ≤ ${M / 60} min`]];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_320px]">
      {/* Tabela principal: um separador por linha; clique abre os pedidos dele */}
      <div className="overflow-x-auto rounded-xl bg-white shadow">
        <h3 className="border-b p-3 font-bold">Separadores <span className="text-sm font-normal text-gray-500">· {rotulo} · clique numa linha para ver os pedidos</span></h3>
        <table className="w-full whitespace-nowrap text-sm">
          <thead className="bg-gray-50 text-left text-gray-500">
            <tr>
              {cab.map(([c, nome]) => (
                <th key={c} onClick={() => setOrdem(o => ({ col: c, asc: o.col === c ? !o.asc : c === "nome" }))} className="cursor-pointer select-none px-3 py-2 hover:text-gray-900">
                  {nome}{ordem.col === c ? (ordem.asc ? " ▲" : " ▼") : ""}
                </th>))}
              <th className="px-3 py-2">Agora</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map(s => (
              <Fragment key={s.matricula}>
                <tr onClick={() => setAberto(a => a === s.matricula ? null : s.matricula)} className={`cursor-pointer border-t hover:bg-blue-50 ${aberto === s.matricula ? "bg-blue-50" : ""}`}>
                  <td className="px-3 py-2 font-semibold">{aberto === s.matricula ? "▾" : "▸"} {s.nome} <span className="text-xs font-normal text-gray-400">{s.matricula}</span></td>
                  <td className="px-3 text-center">{s.pedidos}</td>
                  <td className="px-3 text-center">{s.itens}</td>
                  <td className="px-3 font-mono">{mmss(s.sep_medio)}</td>
                  <td className={`px-3 font-mono ${corLoja(s.loja_medio, M)}`}>{mmss(s.loja_medio)}</td>
                  <td className="px-3 text-center">{s.itens_min == null ? "—" : s.itens_min.toLocaleString("pt-BR")}</td>
                  <td className={`px-3 text-center ${s.faltas ? "font-semibold text-red-700" : ""}`}>{s.faltas}</td>
                  <td className={`px-3 text-center ${s.subs ? "text-yellow-700" : ""}`}>{s.subs}</td>
                  <td className="px-3 text-right">{s.reembolso ? brl(s.reembolso) : "—"}</td>
                  <td className={`px-3 text-center ${s.loja_no_prazo_pct != null && s.loja_no_prazo_pct < 70 ? "font-semibold text-red-700" : ""}`}>{s.loja_no_prazo_pct == null ? "—" : `${s.loja_no_prazo_pct}%`}</td>
                  <td className="px-3">{s.em_andamento
                    ? <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-yellow-800">📦 separando {s.em_andamento}</span>
                    : <span className="rounded-full bg-green-100 px-2 py-0.5 text-green-800">livre</span>}</td>
                </tr>
                {/* Lista de pedidos do separador */}
                {aberto === s.matricula && (
                  <tr><td colSpan={11} className="bg-gray-50 px-6 py-2">
                    {s.lista.length ? (
                      <table className="w-full text-xs">
                        <thead className="text-left text-gray-500"><tr><th className="py-1">Pedido</th><th>Data/hora</th><th className="text-center">Itens</th><th>Separação</th><th>Loja</th><th className="text-center">Faltas</th><th className="text-center">Substit.</th><th className="text-right">Reembolso</th></tr></thead>
                        <tbody>
                          {s.lista.map(p => (
                            <tr key={p.numero} className="border-t">
                              <td className="py-1 font-semibold">{p.numero}</td>
                              <td>{new Date(p.criado_em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })}</td>
                              <td className="text-center">{p.itens}</td>
                              <td className="font-mono">{mmss(p.sep_seg)}</td>
                              <td className={`font-mono ${corLoja(p.loja_seg, M)}`}>{mmss(p.loja_seg)}</td>
                              <td className="text-center">{p.faltas || "—"}</td>
                              <td className="text-center">{p.subs || "—"}</td>
                              <td className="text-right">{p.reembolso ? brl(p.reembolso) : "—"}</td>
                            </tr>))}
                        </tbody>
                      </table>) : <p className="text-xs text-gray-400">Nenhum pedido separado no período.</p>}
                  </td></tr>)}
              </Fragment>))}
            {!linhas.length && <tr><td colSpan={11} className="p-4 text-center text-gray-400">Nenhum separador cadastrado.</td></tr>}
          </tbody>
          {/* Rodapé: totais e médias do período */}
          {todos.length > 0 && (
            <tfoot className="border-t-2 bg-gray-50 font-semibold">
              <tr>
                <td className="px-3 py-2">Total / média</td>
                <td className="px-3 text-center">{tot.pedidos}</td>
                <td className="px-3 text-center">{tot.itens}</td>
                <td className="px-3 font-mono">{mmss(med(todos.map(p => p.sep_seg)))}</td>
                <td className={`px-3 font-mono ${corLoja(med(todos.map(p => p.loja_seg)), M)}`}>{mmss(med(todos.map(p => p.loja_seg)))}</td>
                <td className="px-3 text-center">{sepTot ? (tot.itens / (sepTot / 60)).toFixed(1).replace(".", ",") : "—"}</td>
                <td className="px-3 text-center">{tot.faltas}</td>
                <td className="px-3 text-center">{tot.subs}</td>
                <td className="px-3 text-right">{tot.reembolso ? brl(tot.reembolso) : "—"}</td>
                <td className="px-3 text-center">{lojaOk.length ? `${Math.round(100 * lojaOk.filter(p => p.loja_seg! <= M).length / lojaOk.length)}%` : "—"}</td>
                <td />
              </tr>
            </tfoot>)}
        </table>
      </div>

      {/* Lateral: produtos que mais faltaram (ajuda a corrigir estoque) */}
      <section className="h-fit rounded-xl bg-white p-3 shadow">
        <h3 className="mb-2 font-bold">Top produtos em falta <span className="text-xs font-normal text-gray-500">· {rotulo}</span></h3>
        {d.top_faltas.length ? (
          <ol className="space-y-1 text-sm">
            {d.top_faltas.map((f, i) => (
              <li key={f.sku} className="flex items-center gap-2 border-t pt-1 first:border-0">
                <span className="w-4 text-gray-400">{i + 1}</span>
                <span className="flex-1 truncate" title={`${f.nome} (${f.sku})`}>{f.nome}</span>
                <span className="text-xs text-red-700">{f.vezes}x · {f.unidades} un.</span>
              </li>))}
          </ol>) : <p className="text-sm text-gray-400">Nenhuma falta no período. 🎉</p>}
      </section>
    </div>);
}
