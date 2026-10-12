"use client";
import { useRef, ReactNode } from "react";
import Foto from "./Foto";

type P = { sku: string; nome: string; categoria: string; imagem_url: string | null; preco: string; preco_original: string | null; peso: string | null; proxima_validade: string | null };
const cores = ["bg-red-300","bg-green-300","bg-sky-300","bg-yellow-200","bg-purple-300","bg-orange-200","bg-pink-300","bg-teal-300"];

export default function Home({ produtos, categorias, abrir, acao }: { produtos: P[]; categorias: string[]; abrir: (c: string) => void; acao: (p: any) => ReactNode }) {
  const faixa = useRef<HTMLDivElement>(null);
  const rolar = (d: number) => faixa.current?.scrollBy({ left: d * 600, behavior: "smooth" });
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-10 flex items-center gap-8 rounded-full bg-gray-100 p-3">
        <div className="flex h-40 w-80 items-center justify-center rounded-full bg-blue-600 text-center text-3xl font-black leading-tight text-white">LEVE 2,<br/>PAGUE 1</div>
        <div>
          <p className="mb-4 text-2xl font-bold text-blue-900">Seu favorito: Leve 2, Pague 1!</p>
          <button onClick={() => abrir(categorias[0])} className="rounded-full bg-blue-600 px-10 py-2 font-semibold text-white">Comprar</button>
        </div>
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-blue-900">Categorias</h2>
        <div className="flex gap-3 text-xl text-blue-600">
          <button onClick={() => rolar(-1)}>‹</button><button onClick={() => rolar(1)}>›</button>
        </div>
      </div>
      <div ref={faixa} className="flex gap-2 overflow-x-auto pb-3 [scrollbar-width:none]">
        {categorias.map((c, i) => {
          const img = produtos.find(p => p.categoria === c && p.imagem_url?.startsWith("http"))?.imagem_url ?? null;
          return (
            <button key={c} onClick={() => abrir(c)} className="w-28 shrink-0 text-center">
              <div className="h-24 overflow-hidden rounded-t-xl bg-gray-100 p-2"><Foto src={img} className="h-full w-full" /></div>
              <div className={`h-2 rounded-b-xl ${cores[i % cores.length]}`} />
              <p className="mt-2 text-sm text-gray-600">{c}</p>
            </button>
          );
        })}
      </div>
      <Faixa titulo="Melhores Ofertas!" itens={produtos.filter(p => p.preco_original).slice(0, 20)} acao={acao} />
      <Faixa titulo="Próximos a vencer" itens={produtos.filter(p => p.proxima_validade).sort((a, b) => (a.proxima_validade! < b.proxima_validade! ? -1 : 1)).slice(0, 20)} acao={acao} />
      <Faixa titulo="Chocolates e Doces" itens={produtos.filter(p => p.categoria === "Chocolates e Doces").slice(0, 20)} acao={acao} />

      <h2 className="mb-3 mt-[80px] text-[24px] font-bold text-blue-900">Aproveite agora!</h2>
      <div className="flex gap-4 overflow-x-auto pb-3 [scrollbar-width:none]">
        {[["Dia das Crianças","bg-yellow-300","Biscoitos e Salgadinhos"],["Leve 3, Pague 2","bg-pink-300","Chocolates e Doces"],["Lava Roupa R$ 9,99","bg-sky-300","Limpeza"],["Da horta: 30% OFF","bg-green-300","Hortifruti"]].map(([t,c,cat]) => (
          <button key={t} onClick={() => abrir(cat)} className={`flex h-[180px] w-[300px] shrink-0 items-end rounded-2xl ${c} p-4 text-left text-2xl font-black text-blue-900`}>{t}</button>
        ))}
      </div>

      <p className="mb-2 mt-12 text-xs font-bold uppercase text-blue-600">Perguntas frequentes</p>
      {["Como funciona um supermercado online?","Como comprar na Daki?","Onde a Daki entrega no Brasil?","A Daki oferece promoções e cupons para compras?","Precisa de ajuda com seu pedido, e agora?"].map(q => (
        <details key={q} className="border-b py-3 text-sm text-blue-800"><summary className="cursor-pointer font-semibold">{q}</summary><p className="mt-2 text-gray-600">Em breve.</p></details>
      ))}
    </div>
  );
}

function Faixa({ titulo, itens, acao }: { titulo: string; itens: P[]; acao: (p: any) => ReactNode }) {
  const r = useRef<HTMLDivElement>(null);
  if (!itens.length) return null;
  return (
    <section className="mt-[80px]">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[24px] font-bold text-blue-900">{titulo}</h2>
        <div className="flex gap-3 text-xl text-blue-600"><button onClick={() => r.current?.scrollBy({ left: -600, behavior: "smooth" })}>‹</button><button onClick={() => r.current?.scrollBy({ left: 600, behavior: "smooth" })}>›</button></div>
      </div>
      <div ref={r} className="flex gap-6 overflow-x-auto pb-3 [scrollbar-width:none]">
        {itens.map(p => (
          <div key={p.sku} className="flex w-[154px] shrink-0 flex-col rounded-xl border border-gray-200 bg-white p-[1px]">
            <div className="h-[121px] rounded-t-xl bg-gray-50 p-2"><Foto src={p.imagem_url} className="h-full w-full" /></div>
            <p className="mt-2 line-clamp-2 h-[42px] px-2 text-[14px] leading-[21px] text-blue-900">{p.nome}</p>
            <p className="mt-1 px-2 text-[12px] text-gray-500">{p.peso}</p>
            {p.preco_original && <p className="text-xs text-gray-400 line-through">R$ {Number(p.preco_original).toFixed(2).replace(".", ",")}</p>}
            <p className="px-2 text-[17px] font-bold text-blue-900">R$ {Number(p.preco).toFixed(2).replace(".", ",")}</p>
            <div className="mt-auto px-2 pb-2">{acao(p)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
