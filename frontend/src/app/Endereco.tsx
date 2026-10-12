"use client";
import { useMemo, useState } from "react";
import Mapa from "./Mapa";

const API = "/api";
export type EnderecoForm = { cep: string; rua: string; numero_end: string; complemento: string; bairro: string; cidade: string; uf: string; referencia: string; lat: number | null; lon: number | null };
const vazio: EnderecoForm = { cep: "", rua: "", numero_end: "", complemento: "", bairro: "", cidade: "", uf: "", referencia: "", lat: null, lon: null };

export default function Endereco({ onConfirmar, onFechar, enviando }: { onConfirmar: (e: EnderecoForm) => void; onFechar: () => void; enviando: boolean }) {
  const [e, setE] = useState<EnderecoForm>(vazio);
  const [msg, setMsg] = useState("");
  const [buscando, setBuscando] = useState(false);
  const set = (k: keyof EnderecoForm, v: string) => setE(x => ({ ...x, [k]: v }));

  async function buscarCep(valor: string) {
    const cep = valor.replace(/\D/g, "").slice(0, 8);
    set("cep", cep.length > 5 ? `${cep.slice(0, 5)}-${cep.slice(5)}` : cep);
    if (cep.length !== 8) return;
    setBuscando(true); setMsg("");
    try {
      const d = await (await fetch(`https://viacep.com.br/ws/${cep}/json/`)).json();
      if (d.erro) { setMsg("CEP não encontrado. Preencha o endereço."); return; }
      setE(x => ({ ...x, rua: d.logradouro || x.rua, bairro: d.bairro || x.bairro, cidade: d.localidade || x.cidade, uf: d.uf || x.uf, lat: null, lon: null }));
    } catch { setMsg("Não consegui consultar o CEP. Preencha manualmente."); }
    finally { setBuscando(false); }
  }

  async function localizar() {
    if (!e.rua || !e.cidade || !e.uf) return setMsg("Preencha rua, cidade e UF.");
    setBuscando(true); setMsg("");
    const q = new URLSearchParams({ rua: e.rua, cidade: e.cidade, uf: e.uf, ...(e.numero_end ? { numero: e.numero_end } : {}) });
    const r = await fetch(`${API}/geo/geocode?${q}`);
    setBuscando(false);
    if (!r.ok) return setMsg("Não achei no mapa. Confira rua e número.");
    const d = await r.json(); setE(x => ({ ...x, lat: d.lat, lon: d.lon }));
  }

  const faltando = [!/^\d{5}-?\d{3}$/.test(e.cep) && "CEP", !e.rua.trim() && "rua", !e.numero_end.trim() && "número",
    !e.bairro.trim() && "bairro", !e.cidade.trim() && "cidade", !/^[A-Za-z]{2}$/.test(e.uf) && "UF"].filter(Boolean) as string[];
  const pinos = useMemo(() => e.lat != null && e.lon != null ? [{ lat: e.lat, lon: e.lon, cor: "#2563eb", rotulo: "Entrega aqui" }] : [], [e.lat, e.lon]);
  const campo = "w-full rounded-lg bg-gray-100 px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[95vh] w-[880px] overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold text-blue-900">📍 Endereço de entrega</h2>
          <button onClick={onFechar} className="text-xl text-blue-600">✕</button>
        </div>
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <input value={e.cep} onChange={x => buscarCep(x.target.value)} placeholder="CEP *" inputMode="numeric" className={campo} autoFocus />
              {buscando && <span className="animate-pulse text-xs text-gray-500">buscando…</span>}
            </div>
            <input value={e.rua} onChange={x => set("rua", x.target.value)} placeholder="Rua *" className={campo} />
            <div className="grid grid-cols-2 gap-3">
              <input value={e.numero_end} onChange={x => setE(y => ({ ...y, numero_end: x.target.value, lat: null, lon: null }))} placeholder="Número *" className={campo} />
              <input value={e.complemento} onChange={x => set("complemento", x.target.value)} placeholder="Complemento" className={campo} />
            </div>
            <input value={e.bairro} onChange={x => set("bairro", x.target.value)} placeholder="Bairro *" className={campo} />
            <div className="grid grid-cols-[1fr_80px] gap-3">
              <input value={e.cidade} onChange={x => set("cidade", x.target.value)} placeholder="Cidade *" className={campo} />
              <input value={e.uf} onChange={x => set("uf", x.target.value.toUpperCase().slice(0, 2))} placeholder="UF *" className={campo} />
            </div>
            <input value={e.referencia} onChange={x => set("referencia", x.target.value)} placeholder="Ponto de referência" className={campo} />
            {msg && <p className="text-sm text-red-600">{msg}</p>}
          </div>
          <div>
            {pinos.length ? (<>
              <Mapa pinos={pinos} arrastavel={0} onMover={(lat, lon) => setE(x => ({ ...x, lat, lon }))} className="h-72" />
              <p className="mt-2 text-xs text-gray-500">Arraste o pino azul até a porta, se precisar.</p>
            </>) : (
              <div className="flex h-72 flex-col items-center justify-center rounded-xl border-2 border-dashed text-center text-sm text-gray-500">
                <p className="mb-3">Preencha o endereço e localize no mapa.</p>
                <button onClick={localizar} disabled={!e.rua || !e.cidade || buscando} className="rounded-xl border-2 border-blue-600 px-4 py-2 font-semibold text-blue-700 disabled:opacity-40">🗺 Localizar no mapa</button>
              </div>)}
          </div>
        </div>
        <button onClick={() => onConfirmar(e)} disabled={faltando.length > 0 || enviando}
          className="mt-5 w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95 disabled:bg-gray-300">
          {enviando ? "Criando pedido…" : faltando.length ? `Falta: ${faltando.join(", ")}` : "Confirmar endereço e ir para o pagamento"}
        </button>
      </div>
    </div>);
}
