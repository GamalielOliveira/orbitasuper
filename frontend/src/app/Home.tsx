"use client";
import { useRef, useState, ReactNode } from "react";
import Foto from "./Foto";

type P = { sku: string; nome: string; categoria: string; imagem_url: string | null; preco: string; preco_original: string | null; peso: string | null; proxima_validade: string | null };
const cores = ["bg-red-300", "bg-green-300", "bg-sky-300", "bg-yellow-200", "bg-purple-300", "bg-orange-200", "bg-pink-300", "bg-teal-300"];
const brl = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;

function Setas({ rolar }: { rolar: (d: number) => void }) {
  const b = "flex h-[32px] w-[32px] items-center justify-center rounded-full bg-blue-50 text-[22px] font-bold leading-none text-blue-600 transition hover:bg-blue-100";
  return (
    <div className="flex gap-[8px]">
      <button aria-label="Anterior" onClick={() => rolar(-1)} className={b}>‹</button>
      <button aria-label="Próximo" onClick={() => rolar(1)} className={b}>›</button>
    </div>
  );
}

function Titulo({ texto, rolar }: { texto: string; rolar?: (d: number) => void }) {
  return (
    <div className="mb-[16px] flex items-center justify-between">
      <h2 className="text-[32px] font-bold leading-[40px] text-blue-900">{texto}</h2>
      {rolar && <Setas rolar={rolar} />}
    </div>
  );
}

const slides = [
  { t: "Seu favorito:\nLeve 2, Pague 1!", bg: "bg-sky-100", selo: "LEVE 2, PAGUE 1", cor: "bg-blue-600" },
  { t: "Hortifruti\nfresquinho", bg: "bg-green-100", selo: "30% OFF", cor: "bg-green-600" },
  { t: "Chocolates\ncom desconto", bg: "bg-pink-100", selo: "LEVE 3, PAGUE 2", cor: "bg-pink-600" },
];

export default function Home({ produtos, categorias, abrir, acao }: { produtos: P[]; categorias: string[]; abrir: (c: string) => void; acao: (p: any) => ReactNode }) {
  const faixa = useRef<HTMLDivElement>(null);
  const banner = useRef<HTMLDivElement>(null);
  const [slide, setSlide] = useState(0);
  const irPara = (i: number) => {
    const n = (i + slides.length) % slides.length;
    setSlide(n);
    banner.current?.scrollTo({ left: n * 446, behavior: "smooth" });
  };
  const alvos = [categorias[0], "Hortifruti", "Chocolates e Doces"];

  return (
    <div className="mx-auto w-full max-w-[1232px] px-0 py-[32px]">
      {/* Banner */}
      <div className="relative">
        <div ref={banner} className="flex h-[280px] gap-[16px] overflow-x-auto [scrollbar-width:none]">
          {slides.map((s, i) => (
            <div key={i} className={`flex h-[280px] w-[430px] shrink-0 flex-col justify-between overflow-hidden rounded-[24px] ${s.bg} p-[24px]`}>
              <div>
                <span className={`inline-block rounded-full ${s.cor} px-[12px] py-[4px] text-[14px] font-black text-white`}>{s.selo}</span>
                <p className="mt-[12px] whitespace-pre-line text-[36px] font-bold leading-[42px] text-blue-900">{s.t}</p>
              </div>
              <button onClick={() => abrir(alvos[i] ?? categorias[0])} className="h-[56px] w-[270px] rounded-full bg-blue-600 text-[18px] font-semibold text-white transition hover:bg-blue-700">Comprar</button>
            </div>
          ))}
        </div>
        <button aria-label="Anterior" onClick={() => irPara(slide - 1)} className="absolute left-[-16px] top-[124px] flex h-[40px] w-[40px] items-center justify-center rounded-full bg-white text-[24px] text-blue-600 shadow-md">‹</button>
        <button aria-label="Próximo" onClick={() => irPara(slide + 1)} className="absolute right-[-16px] top-[124px] flex h-[40px] w-[40px] items-center justify-center rounded-full bg-white text-[24px] text-blue-600 shadow-md">›</button>
        <div className="mt-[12px] flex justify-center gap-[8px]">
          {slides.map((_, i) => (
            <button key={i} aria-label={`Slide ${i + 1}`} onClick={() => irPara(i)} className={`h-[8px] rounded-full transition-all ${i === slide ? "w-[24px] bg-blue-600" : "w-[8px] bg-gray-300"}`} />
          ))}
        </div>
      </div>

      {/* Categorias */}
      <section className="mt-[60px]">
        <Titulo texto="Categorias" rolar={(d) => faixa.current?.scrollBy({ left: d * 720, behavior: "smooth" })} />
        <div ref={faixa} className="flex gap-[8px] overflow-x-auto pb-[12px] [scrollbar-width:none]">
          {categorias.map((c, i) => {
            const img = produtos.find(p => p.categoria === c && p.imagem_url?.startsWith("http"))?.imagem_url ?? null;
            return (
              <button key={c} onClick={() => abrir(c)} className="w-[136px] shrink-0 text-left">
                <div className="relative h-[136px] w-[136px] overflow-hidden rounded-2xl bg-gray-100">
                  {img ? <img src={img} alt="" loading="lazy" className="h-full w-full object-cover" />
                       : <span className="flex h-full w-full items-center justify-center text-[48px]">📦</span>}
                  <div className={`absolute bottom-0 left-0 h-[16px] w-full ${cores[i % cores.length]}`} />
                </div>
                <p className="mt-[8px] truncate text-[18px] font-semibold leading-[24px] text-gray-600">{c}</p>
              </button>
            );
          })}
        </div>
      </section>

      <Faixa titulo="Melhores Ofertas!" itens={produtos.filter(p => p.preco_original).slice(0, 20)} acao={acao} />
      <Faixa titulo="Próximos a vencer" itens={produtos.filter(p => p.proxima_validade).sort((a, b) => (a.proxima_validade! < b.proxima_validade! ? -1 : 1)).slice(0, 20)} acao={acao} />
      <Faixa titulo="Chocolates e Doces" itens={produtos.filter(p => p.categoria === "Chocolates e Doces").slice(0, 20)} acao={acao} />

      <section className="mt-[60px]">
        <Titulo texto="Aproveite agora!" />
        <div className="flex gap-[16px] overflow-x-auto pb-[12px] [scrollbar-width:none]">
          {[["Dia das Crianças", "bg-yellow-200", "Biscoitos e Salgadinhos"], ["Leve 3, Pague 2", "bg-pink-200", "Chocolates e Doces"], ["Lava Roupa R$ 9,99", "bg-sky-200", "Limpeza"], ["Da horta: 30% OFF", "bg-green-200", "Hortifruti"]].map(([t, c, cat]) => (
            <button key={t} onClick={() => abrir(cat)} className={`flex h-[230px] w-[317px] shrink-0 items-end rounded-[24px] ${c} p-[20px] text-left text-[28px] font-black leading-[32px] text-blue-900`}>{t}</button>
          ))}
        </div>
      </section>

      <p className="mb-[8px] mt-[48px] text-[12px] font-bold uppercase text-blue-600">Perguntas frequentes</p>
      {["Como funciona um supermercado online?", "Como comprar na Daki?", "Onde a Daki entrega no Brasil?", "A Daki oferece promoções e cupons para compras?", "Precisa de ajuda com seu pedido, e agora?"].map(q => (
        <details key={q} className="border-b py-[12px] text-[14px] text-blue-800"><summary className="cursor-pointer font-semibold">{q}</summary><p className="mt-[8px] text-gray-600">Em breve.</p></details>
      ))}
    </div>
  );
}

function Faixa({ titulo, itens, acao }: { titulo: string; itens: P[]; acao: (p: any) => ReactNode }) {
  const r = useRef<HTMLDivElement>(null);
  if (!itens.length) return null;
  return (
    <section className="mt-[60px]">
      <Titulo texto={titulo} rolar={(d) => r.current?.scrollBy({ left: d * 712, behavior: "smooth" })} />
      <div ref={r} className="flex gap-[26px] overflow-x-auto pb-[12px] [scrollbar-width:none]">
        {itens.map(p => {
          const desc = p.preco_original ? Math.round((1 - Number(p.preco) / Number(p.preco_original)) * 100) : 0;
          return (
            <div key={p.sku} className="relative flex h-[300px] w-[152px] shrink-0 flex-col bg-white">
              {desc > 0 && <span className="absolute right-[4px] top-[4px] z-10 rounded-full bg-yellow-400 px-[8px] py-[2px] text-[12px] font-bold text-blue-900">-{desc}%</span>}
              <div className="flex h-[121px] w-[152px] items-center justify-center overflow-hidden rounded-[12px] bg-gray-100 p-[8px] text-[48px]">
                <Foto src={p.imagem_url} className="h-full w-full object-contain" />
              </div>
              <p className="mt-[8px] line-clamp-2 h-[40px] text-[14px] font-semibold leading-[20px] text-gray-800">{p.nome}</p>
              <p className="mt-[4px] text-[12px] leading-[16px] text-gray-500">{p.peso}</p>
              <div className="mt-auto">
                {p.preco_original && <p className="text-[12px] leading-[16px] text-gray-400 line-through">{brl(Number(p.preco_original))}</p>}
                <p className="text-[18px] font-bold leading-[24px] text-blue-900">{brl(Number(p.preco))}</p>
                <div className="w-[136px]">{acao(p)}</div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

