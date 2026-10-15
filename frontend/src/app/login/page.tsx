"use client";
// Login da loja do cliente (mesmo visual das telas de separação/entrega).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { lerSessao, salvarSessao } from "../sessao";

export default function Login() {
  const router = useRouter();
  const [mat, setMat] = useState(""); const [pin, setPin] = useState(""); const [erro, setErro] = useState("");
  useEffect(() => { if (lerSessao()) router.replace("/"); }, [router]);   // já logado: vai direto para a loja

  async function entrar() {
    const r = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matricula: mat, pin }) });
    const d = await r.json();
    if (!r.ok) return setErro(d.detail);
    // loja aceita cliente e gerente (separador/entregador usam as próprias telas)
    if (d.funcao !== "cliente" && d.funcao !== "gerente") return setErro("Este login não tem acesso à loja.");
    salvarSessao({ token: d.token, nome: d.nome, funcao: d.funcao });
    router.replace("/");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-blue-900 text-gray-900">
      <div className="w-80 rounded-2xl bg-white p-6 shadow-2xl">
        <p className="text-2xl font-extrabold text-blue-600">super</p>
        <p className="mb-5 text-sm text-gray-500">Entre para fazer suas compras</p>
        <input value={mat} onChange={e => setMat(e.target.value)} placeholder="Login" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        <input value={pin} onChange={e => setPin(e.target.value)} onKeyDown={e => e.key === "Enter" && entrar()} placeholder="Senha" type="password" className="mb-3 w-full rounded-lg bg-gray-100 px-3 py-3 outline-none" />
        {erro && <p className="mb-2 text-sm text-red-600">{erro}</p>}
        <button onClick={entrar} className="w-full rounded-xl bg-blue-600 py-3 font-semibold text-white transition active:scale-95">Entrar</button>
      </div>
    </main>);
}
