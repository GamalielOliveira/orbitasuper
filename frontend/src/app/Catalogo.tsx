"use client";
import { useState } from "react";

type Produto = { sku: string; nome: string; categoria: string; preco: string; estoque: number };

export default function Catalogo({ inicial }: { inicial: Produto[] }) {
  const [produtos, setProdutos] = useState(inicial);
  const [carrinho, setCarrinho] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState("");

  const add = (p: Produto) => setCarrinho(c => ({ ...c, [p.sku]: Math.min((c[p.sku] || 0) + 1, p.estoque) }));
  const rem = (sku: string) => setCarrinho(c => { const n = { ...c }; n[sku] > 1 ? n[sku]-- : delete n[sku]; return n; });
  const total = Object.entries(carrinho).reduce((t, [sku, q]) => t + q * Number(produtos.find(p => p.sku === sku)!.preco), 0);
  const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;

  async function finalizar() {
    const itens = Object.entries(carrinho).map(([sku, quantidade]) => ({ sku, quantidade }));
    const r = await fetch("http://localhost:8000/pedidos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cliente: "Gamaliel", itens }) });
    const d = await r.json();
    if (!r.ok) { setMsg(`❌ ${d.detail}`); return; }
    setMsg(`✅ Pedido ${d.numero} criado! Total ${brl(Number(d.total))}. Aguardando pagamento.`);
    setCarrinho({});
    setProdutos(await (await fetch("http://localhost:8000/produtos", { cache: "no-store" })).json());
  }

  const categorias = [...new Set(produtos.map(p => p.categoria))];
  return (
    <div className="flex gap-6">
      <div className="flex-1">
        {categorias.map(cat => (
          <section key={cat} className="mb-8">
            <h2 className="mb-3 text-lg font-semibold text-gray-800">{cat}</h2>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              {produtos.filter(p => p.categoria === cat).map(p => (
                <div key={p.sku} className="rounded-xl bg-white p-4 shadow-sm">
                  <p className="font-medium text-gray-900">{p.nome}</p>
                  <p className="mt-1 text-lg font-bold text-purple-700">{brl(Number(p.preco))}</p>
                  <p className={`mt-1 text-xs ${p.estoque > 0 ? "text-green-600" : "text-red-600"}`}>{p.estoque > 0 ? `${p.estoque} em estoque` : "Esgotado"}</p>
                  <button onClick={() => add(p)} disabled={p.estoque === 0 || (carrinho[p.sku] || 0) >= p.estoque}
                    className={`mt-3 w-full rounded-lg py-2 text-sm text-white transition-all duration-150 active:scale-95 hover:brightness-110 disabled:bg-gray-300 disabled:active:scale-100 ${carrinho[p.sku] ? "bg-green-600" : "bg-purple-600"}`}>{carrinho[p.sku] ? `✓ ${carrinho[p.sku]} no carrinho` : "Adicionar"}</button>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      <aside className="sticky top-6 h-fit w-80 rounded-xl bg-white p-4 text-gray-900 shadow-md">
        <h2 className="mb-3 text-lg font-bold">🛒 Carrinho</h2>
        {Object.keys(carrinho).length === 0 && <p className="text-sm text-gray-500">Vazio</p>}
        {Object.entries(carrinho).map(([sku, q]) => {
          const p = produtos.find(x => x.sku === sku)!;
          return (
            <div key={sku} className="mb-2 flex items-center justify-between text-sm">
              <span>{q}x {p.nome}</span>
              <button onClick={() => rem(sku)} className="text-red-500">−</button>
            </div>
          );
        })}
        <p className="mt-4 border-t pt-3 font-bold">Total: {brl(total)}</p>
        <button onClick={finalizar} disabled={total === 0} className="mt-3 w-full rounded-lg bg-green-600 py-2 text-white disabled:bg-gray-300">Finalizar pedido</button>
        {msg && <p className="mt-3 text-sm">{msg}</p>}
      </aside>
    </div>
  );
}
