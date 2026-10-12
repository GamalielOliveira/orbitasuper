import type { Metadata } from "next";
import "./globals.css";
import BarraInferior from "./BarraInferior";

export const metadata: Metadata = {
  title: "Mini Daki",
  description: "Réplica de dark store",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className="bg-gray-100 text-gray-900 antialiased">
        <div className="mx-auto min-h-screen max-w-[1280px] bg-white shadow-sm">{children}</div>
      </body>
    </html>
  );
}