// Proxy do Next: roda antes de repassar /api para o backend.
// Bloqueia, de fora, o que só pode ser chamado por dentro:
// - webhook de pagamento (o simulador chama por localhost dentro do backend; de fora alguém "aprovaria" pedido sem pagar)
// - documentação da API (/docs, /redoc, /openapi.json)
import { NextResponse } from "next/server";

export function proxy() {
  return new NextResponse("Não encontrado", { status: 404 });
}

export const config = {
  matcher: ["/api/webhooks/:path*", "/api/docs/:path*", "/api/docs", "/api/redoc", "/api/openapi.json"],
};
