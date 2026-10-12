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
      <body className="bg-white text-gray-900 antialiased">
        <div className="pb-24">{children}</div>
      </body>
    </html>
  );
}