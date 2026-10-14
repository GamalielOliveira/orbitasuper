"use client";
// Aba "Vendas": faturamento e perdas (reembolsos, expirados, faltas) no período escolhido.
import { useCallback, useEffect, useState } from "react";

const API = "/api";
type Item = { sku: string; nome: string; qtd: number; valor: number };
type Falta = { sku: string; nome: string; vezes: number; unidades: number; valor: number };
type Dados = {
  cartoes: { faturamento: number; pedidos_pagos: number; ticket_medio: number | null; itens_pedido: number | null; reembolso_valor: number; reembolso_qtd: number;
    expirados_qtd: number; expirados_valor: number; taxa_expiracao: number | null };
  por_dia: { dia: string; pedidos: number; valor: number }[];
  top_vendidos: Item[]; top_falta: Falta[];
  por_categoria: { categoria: string; qtd: number; valor: number }[];
};

const brl = (v: number | null) => v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const num = (v: number | null) => v == null ? "—" : v.toLocaleString("pt-BR");

// Cartão pequeno com número grande
function Cartao({ titulo, valor, sub, ruim }: { titulo: string; valor: string; sub?: string; ruim?: boolean }) {
  return (
    <div className="rounded-xl bg-white p-3 shadow">
      <p className="text-xs text-gray-500">{titulo}</p>
      <p className={`text-xl font-bold ${ruim ? "text-red-700" : "text-slate-900"}`}>{valor}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>);
}

// Caixa com título para as tabelas do grid
function Caixa({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-white p-3 shadow">
      <h3 className="mb-2 font-bold">{titulo}</h3>
      {children}
    </section>);
}

export default function Vendas({ token, consulta, rotulo }: { token: string; consulta: string; rotulo: string }) {
  const [d, setD] = useState<Dados | null>(null);

  const carregar = useCallback(async () => {
    const r = await fetch(`${API}/gerente/vendas${consulta}`, { headers: { Authorization: `Bearer ${token}` } });
    if (r.ok) setD(await r.json());
  }, [token, consulta]);
  useEffect(() => { carregar(); const t = setInterval(carregar, 30000); return () => clearInterval(t); }, [carregar]);

  if (!d) return <p className="text-gray-500">Carregando…</p>;
  const k = d.cartoes;
  const maxDia = Math.max(1, ...d.por_dia.map(x => x.valor));
  const totCat = d.por_categoria.reduce((a, x) => a + x.valor, 0) || 1;
  const vazio = <p className="text-sm text-gray-400">Sem dados no período.</p>;

  return (
    <div className="space-y-4">
      {/* Linha de cartões */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Cartao titulo="Faturamento" valor={brl(k.faturamento)} sub={rotulo} />
        <Cartao titulo="Pedidos pagos" valor={num(k.pedidos_pagos)} />
        <Cartao titulo="Ticket médio" valor={brl(k.ticket_medio)} />
        <Cartao titulo="Itens/pedido" valor={num(k.itens_pedido)} />
        <Cartao titulo="Reembolsos" valor={brl(k.reembolso_valor)} sub={`${k.reembolso_qtd} pedido(s)`} ruim={k.reembolso_valor > 0} />
        <Cartao titulo="Expirados" valor={num(k.expirados_qtd)} sub="não pagos em 15 min" ruim={k.expirados_qtd > 0} />
        <Cartao titulo="Perdido c/ expirados" valor={brl(k.expirados_valor)} ruim={k.expirados_valor > 0} />
        <Cartao titulo="Taxa de expiração" valor={k.taxa_expiracao == null ? "—" : `${num(k.taxa_expiracao)}%`} ruim={(k.taxa_expiracao ?? 0) > 10} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Faturamento por dia: barras feitas só com CSS */}
        <Caixa titulo="Faturamento por dia">
          {d.por_dia.length ? (
            <div className="space-y-1 text-xs">
              {d.por_dia.map(x => (
                <div key={x.dia} className="flex items-center gap-2">
                  <span className="w-12 text-gray-500">{x.dia.slice(8, 10)}/{x.dia.slice(5, 7)}</span>
                  <div className="h-4 flex-1 rounded bg-gray-100">
                    <div className="h-4 rounded bg-slate-700" style={{ width: `${(100 * x.valor) / maxDia}%` }} />
                  </div>
                  <span className="w-24 text-right font-semibold">{brl(x.valor)}</span>
                  <span className="w-10 text-right text-gray-400">{x.pedidos} ped</span>
                </div>))}
            </div>) : vazio}
        </Caixa>

        {/* Faturamento por categoria, com % do total */}
        <Caixa titulo="Faturamento por categoria">
          {d.por_categoria.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-gray-500"><tr><th>Categoria</th><th className="text-right">Itens</th><th className="text-right">R$</th><th className="w-32 pl-3">%</th></tr></thead>
              <tbody>
                {d.por_categoria.map(x => (
                  <tr key={x.categoria} className="border-t">
                    <td className="py-1">{x.categoria}</td>
                    <td className="text-right">{x.qtd}</td>
                    <td className="text-right">{brl(x.valor)}</td>
                    <td className="pl-3">
                      <div className="flex items-center gap-1">
                        <div className="h-2 flex-1 rounded bg-gray-100"><div className="h-2 rounded bg-blue-600" style={{ width: `${(100 * x.valor) / totCat}%` }} /></div>
                        <span className="w-9 text-right text-xs">{Math.round((100 * x.valor) / totCat)}%</span>
                      </div>
                    </td>
                  </tr>))}
              </tbody>
            </table>) : vazio}
        </Caixa>

        {/* Top 10 mais vendidos */}
        <Caixa titulo="Top 10 mais vendidos">
          {d.top_vendidos.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-gray-500"><tr><th className="w-6">#</th><th>Produto</th><th className="text-right">Qtd</th><th className="text-right">R$</th></tr></thead>
              <tbody>
                {d.top_vendidos.map((x, i) => (
                  <tr key={x.sku} className="border-t">
                    <td className="py-1 text-gray-400">{i + 1}</td>
                    <td className="max-w-0 truncate" title={`${x.nome} (${x.sku})`}>{x.nome}</td>
                    <td className="text-right">{x.qtd}</td>
                    <td className="text-right">{brl(x.valor)}</td>
                  </tr>))}
              </tbody>
            </table>) : vazio}
        </Caixa>

        {/* Top 10 mais em falta: o que mais gerou reembolso */}
        <Caixa titulo="Top 10 mais em falta">
          {d.top_falta.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-gray-500"><tr><th className="w-6">#</th><th>Produto</th><th className="text-right">Vezes</th><th className="text-right">Unid.</th><th className="text-right">Reembolsado</th></tr></thead>
              <tbody>
                {d.top_falta.map((x, i) => (
                  <tr key={x.sku} className="border-t">
                    <td className="py-1 text-gray-400">{i + 1}</td>
                    <td className="max-w-0 truncate" title={`${x.nome} (${x.sku})`}>{x.nome}</td>
                    <td className="text-right font-semibold text-red-700">{x.vezes}</td>
                    <td className="text-right">{x.unidades}</td>
                    <td className="text-right">{brl(x.valor)}</td>
                  </tr>))}
              </tbody>
            </table>) : <p className="text-sm text-gray-400">Nenhuma falta no período. 🎉</p>}
        </Caixa>
      </div>
    </div>);
}
