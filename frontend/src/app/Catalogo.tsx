"use client";
import { useState } from "react";

type Produto = { sku: string; nome: string; categoria: string; subcategoria: string | null; preco: string; preco_original: string | null;
  estoque: number; proxima_validade: string | null; conservacao: string | null; peso: string | null; imagem_url: string | null };

const VENCER = "⏰ Próximos a vencer";
const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;
const venceEmBreve = (p: Produto) => !!p.proxima_validade && (new Date(p.proxima_validade).getTime() - Date.now()) / 86400000 <= 3;

export default function Catalogo({ inicial }: { inicial: Produto[] }) {
  const [produtos, setProdutos] = useState(inicial);
  const [carrinho, setCarrinho] = useState<Record<string, number>>({});
  const [aberto, setAberto] = useState(false);
  const [cat, setCat] = useState<string>("Todos");
  const [busca, setBusca] = useState("");
  const [msg, setMsg] = useState("");
  const [checkout, setCheckout] = useState<null | { numero: string; total: number; etapa: "escolha" | "aguardando" | "aprovado" | "recusado"; pix?: string }>(null);
  const [cartao, setCartao] = useState("");

  const add = (p: Produto) => setCarrinho(c => ({ ...c, [p.sku]: Math.min((c[p.sku] || 0) + 1, p.estoque) }));
  const rem = (sku: string) => setCarrinho(c => { const n = { ...c }; n[sku] > 1 ? n[sku]-- : delete n[sku]; return n; });
  const qtdTotal = Object.values(carrinho).reduce((a, b) => a + b, 0);
  const total = Object.entries(carrinho).reduce((t, [sku, q]) => t + q * Number(produtos.find(p => p.sku === sku)!.preco), 0);

  async function finalizar() {
    const itens = Object.entries(carrinho).map(([sku, quantidade]) => ({ sku, quantidade }));
    const r = await fetch("http://localhost:8000/pedidos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cliente: "Gamaliel", itens }) });
    const d = await r.json();
    if (!r.ok) { setMsg(`❌ ${d.detail}`); return; }
    setCarrinho({});
    setCheckout({ numero: d.numero, total: Number(d.total), etapa: "escolha" });
  }

  async function pagar(metodo: "pix" | "cartao") {
    if (!checkout) return;
    const r = await fetch(`http://localhost:8000/pedidos/${checkout.numero}/pagamento`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metodo, cartao_final: metodo === "cartao" ? cartao.slice(-4) : null }) });
    const d = await r.json();
    setCheckout({ ...checkout, etapa: "aguardando", pix: d.pix_copia_cola });
    const timer = setInterval(async () => {
      const st = await (await fetch(`http://localhost:8000/pedidos/${checkout.numero}`)).json();
      if (st.pagamento === "aprovado" || st.pagamento === "recusado") {
        clearInterval(timer);
        setCheckout(c => c && { ...c, etapa: st.pagamento });
        setProdutos(await (await fetch("http://localhost:8000/produtos", { cache: "no-store" })).json());
      }
    }, 2000);
  }

  const categorias = [...new Set(produtos.map(p => p.categoria))];
  const visiveis = produtos.filter(p =>
    (cat === "Todos" || (cat === VENCER ? venceEmBreve(p) : p.categoria === cat)) &&
    p.nome.toLowerCase().includes(busca.toLowerCase()));
  const grupos = [...new Set(visiveis.map(p => (cat === "Todos" ? p.categoria : p.subcategoria || p.categoria)))];

  const Contador = ({ p }: { p: Produto }) => {
    const q = carrinho[p.sku] || 0;
    if (q === 0) return (
      <button onClick={() => add(p)} disabled={p.estoque === 0}
        className="mt-2 w-full rounded-md bg-gray-100 py-1.5 text-lg font-bold text-blue-600 transition active:scale-95 hover:bg-blue-50 disabled:text-gray-300">+</button>);
    return (
      <div className="mt-2 flex items-center justify-between rounded-md bg-blue-600 px-2 py-1 text-white">
        <button onClick={() => rem(p.sku)} className="px-2 text-lg transition active:scale-90">{q === 1 ? "🗑" : "−"}</button>
        <span className="font-semibold">{q}</span>
        <button onClick={() => add(p)} disabled={q >= p.estoque} className="px-2 text-lg transition active:scale-90 disabled:opacity-40">+</button>
      </div>);
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="sticky top-0 z-20 flex items-center gap-4 border-b bg-white px-6 py-3">
        <span className="text-2xl font-extrabold text-blue-600">daki</span>
        <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="🔍 Busque por um produto aqui"
          className="flex-1 rounded-full bg-gray-100 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-300" />
        <span className="hidden text-xs text-gray-600 md:block">📍 Belo Horizonte · <b className="text-blue-600">ALTERAR</b></span>
        <span className="rounded-full bg-blue-600 px-3 py-1 text-xs font-semibold text-white">⏱ 15-20 min</span>
        <button onClick={() => setAberto(true)} className="relative rounded-full bg-yellow-400 px-3 py-1 text-sm font-bold transition active:scale-95">
          🛒 {qtdTotal > 0 && <span className="ml-1">{qtdTotal}</span>}
        </button>
      </header>

      <div className="flex">
        <nav className="sticky top-14 h-[calc(100vh-56px)] w-60 shrink-0 overflow-y-auto border-r bg-white p-4">
          <h2 className="mb-3 text-lg font-bold text-blue-900">Lista de categorias</h2>
          {["Todos", VENCER, ...categorias].map(c => (
            <button key={c} onClick={() => setCat(c)}
              className={`mb-1 block w-full rounded-lg px-3 py-2 text-left text-sm transition ${cat === c ? "bg-blue-100 font-semibold text-blue-700" : "hover:bg-gray-100"}`}>{c}</button>
          )).flatMap((b, i, arr) => {
            const c = ["Todos", VENCER, ...categorias][i];
            if (c !== cat || c === "Todos" || c === VENCER) return [b];
            const subs = [...new Set(produtos.filter(p => p.categoria === c).map(p => p.subcategoria || c))];
            return [b, ...subs.map(sc => (
              <button key={c + sc} onClick={() => document.getElementById("sub-" + sc)?.scrollIntoView({ behavior: "smooth" })}
                className="mb-1 block w-full rounded-lg py-1 pl-8 pr-3 text-left text-xs text-gray-600 hover:bg-gray-100">{sc}</button>
            ))];
          })}
        </nav>

        <main className="flex-1 p-6">
          <h1 className="mb-4 border-b pb-3 text-2xl font-bold text-blue-900">{cat}</h1>
          {visiveis.length === 0 && <p className="text-gray-500">Nenhum produto encontrado.</p>}
          {grupos.map(g => (
            <section key={g} id={"sub-" + g} className="mb-8 scroll-mt-20">
              <h2 className="mb-3 text-lg font-bold text-blue-900">{g}</h2>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4 max-w-6xl">
                {visiveis.filter(p => (cat === "Todos" ? p.categoria : p.subcategoria || p.categoria) === g).map(p => {
                  const desc = p.preco_original ? Math.round((1 - Number(p.preco) / Number(p.preco_original)) * 100) : 0;
                  return (
                    <div key={p.sku} className="relative flex flex-col rounded-xl border border-gray-200 bg-white p-3 shadow-sm transition hover:shadow-md">
                      {desc > 0 && <span className="absolute right-2 top-2 rounded-full bg-yellow-400 px-2 text-xs font-bold">-{desc}%</span>}
                      <div className="flex h-24 items-center justify-center rounded-lg bg-gray-50 text-5xl">{p.imagem_url || "📦"}</div>
                      <p className="mt-2 line-clamp-2 text-sm font-medium">{p.nome}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {p.conservacao && p.conservacao !== "Ambiente" && <span className="rounded-full bg-blue-50 px-2 text-[10px] text-blue-700">❄ {p.conservacao}</span>}
                        {venceEmBreve(p) && <span className="rounded-full bg-orange-50 px-2 text-[10px] text-orange-700">⏰ Vence logo</span>}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">{p.peso}</p>
                      <div className="mt-auto pt-2">
                        {p.preco_original && <p className="text-xs text-gray-400 line-through">{brl(Number(p.preco_original))}</p>}
                        <p className="text-lg font-bold text-blue-900">{brl(Number(p.preco))}</p>
                        <p className={`text-[11px] ${p.estoque > 0 ? "text-green-600" : "text-red-600"}`}>{p.estoque > 0 ? `${p.estoque} em estoque` : "Esgotado"}</p>
                        <Contador p={p} />
                      </div>
                    </div>);
                })}
              </div>
            </section>
          ))}
          {msg && <p className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl bg-white px-4 py-3 text-sm shadow-lg">{msg}</p>}
        </main>
      </div>

      {aberto && <div onClick={() => setAberto(false)} className="fixed inset-0 z-30 bg-black/30" />}
      <aside className={`fixed right-0 top-0 z-40 flex h-full w-96 flex-col bg-white shadow-2xl transition-transform duration-300 ${aberto ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-bold">Minha lista na Daki</h2>
          <button onClick={() => setAberto(false)} className="text-xl text-blue-600">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {qtdTotal === 0 && <p className="text-sm text-gray-500">Sua lista está vazia.</p>}
          {Object.entries(carrinho).map(([sku, q]) => {
            const p = produtos.find(x => x.sku === sku)!;
            return (
              <div key={sku} className="mb-3 flex items-center gap-3 rounded-xl border border-gray-200 p-3">
                <span className="text-3xl">{p.imagem_url}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium">{p.nome}</p>
                  <p className="text-xs text-gray-500">{p.peso}</p>
                  <p className="font-bold text-blue-900">{brl(Number(p.preco) * q)}</p>
                </div>
                <div className="flex items-center gap-2 rounded-md bg-blue-600 px-2 py-1 text-white">
                  <button onClick={() => rem(sku)} className="active:scale-90">{q === 1 ? "🗑" : "−"}</button>
                  <span>{q}</span>
                  <button onClick={() => add(p)} className="active:scale-90">+</button>
                </div>
              </div>);
          })}
          {qtdTotal > 0 && <button onClick={() => setCarrinho({})} className="mx-auto block text-sm text-blue-600">Limpar lista 🗑</button>}
        </div>
        <div className="border-t bg-gray-50 p-4">
          <div className="flex justify-between font-semibold"><span>Subtotal</span><span>{brl(total)}</span></div>
          <button onClick={() => { finalizar(); setAberto(false); }} disabled={qtdTotal === 0}
            className="mt-3 w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95 disabled:bg-gray-300">Continuar para pagamento</button>
        </div>
      </aside>
      {checkout && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-[440px] rounded-2xl bg-white p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-xl font-bold text-blue-900">Pagamento · {checkout.numero}</h2>
              {checkout.etapa !== "aguardando" && <button onClick={() => setCheckout(null)} className="text-xl text-blue-600">✕</button>}
            </div>
            <p className="mb-4 text-2xl font-bold">{brl(checkout.total)}</p>

            {checkout.etapa === "escolha" && (<>
              <button onClick={() => pagar("pix")} className="mb-3 w-full rounded-xl border-2 border-blue-600 py-3 font-semibold text-blue-700 transition active:scale-95 hover:bg-blue-50">⚡ Pagar com Pix</button>
              <div className="rounded-xl border p-3">
                <input value={cartao} onChange={e => setCartao(e.target.value.replace(/\D/g, "").slice(0, 16))} placeholder="Número do cartão de teste"
                  className="mb-2 w-full rounded-lg bg-gray-100 px-3 py-2 text-sm outline-none" />
                <p className="mb-2 text-[11px] text-gray-500">Teste: qualquer número aprova; terminado em 0000 é recusado.</p>
                <button onClick={() => pagar("cartao")} disabled={cartao.length < 4} className="w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95 disabled:bg-gray-300">💳 Pagar com cartão</button>
              </div>
            </>)}

            {checkout.etapa === "aguardando" && (
              <div className="text-center">
                {checkout.pix && (<>
                  <div className="mx-auto mb-3 grid h-40 w-40 grid-cols-8 gap-0.5 rounded-lg bg-white p-2 ring-1 ring-gray-200">
                    {Array.from({ length: 64 }).map((_, i) => <div key={i} className={(i * 7 + checkout.numero.length * 3) % 3 ? "bg-black" : "bg-white"} />)}
                  </div>
                  <p className="mb-1 text-xs text-gray-500">Pix copia e cola (simulado)</p>
                  <p className="mb-3 break-all rounded bg-gray-100 p-2 text-[10px]">{checkout.pix}</p>
                </>)}
                <p className="animate-pulse font-semibold text-blue-700">⏳ Aguardando confirmação do banco…</p>
              </div>
            )}

            {checkout.etapa === "aprovado" && <p className="rounded-xl bg-green-50 p-4 text-center font-semibold text-green-700">✅ Pagamento aprovado! Seu pedido foi para a separação.</p>}
            {checkout.etapa === "recusado" && <p className="rounded-xl bg-red-50 p-4 text-center font-semibold text-red-700">❌ Pagamento recusado. Os itens voltaram para o estoque.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
