// Sessão da loja do cliente: o token fica no navegador (localStorage) para não pedir login a cada visita.
// Vale 8 h (igual aos funcionários); quando expira o backend responde 401 e voltamos para /login.
export type Sessao = { token: string; nome: string; funcao: string };
const CHAVE = "super_sessao";

export const lerSessao = (): Sessao | null => {
  try { return JSON.parse(localStorage.getItem(CHAVE) ?? "null"); } catch { return null; }
};
export const salvarSessao = (s: Sessao) => localStorage.setItem(CHAVE, JSON.stringify(s));
export const sair = () => { localStorage.removeItem(CHAVE); window.location.href = "/login"; };

// fetch com o token; se o login expirou, limpa e manda para /login
export async function api(caminho: string, init: RequestInit = {}) {
  const s = lerSessao();
  const r = await fetch(`/api${caminho}`, { ...init, headers: { ...(init.headers ?? {}), ...(s ? { Authorization: `Bearer ${s.token}` } : {}) } });
  if (r.status === 401) sair();
  return r;
}
