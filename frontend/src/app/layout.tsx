import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Super",
  description: "Réplica de dark store",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className="bg-gray-100 text-gray-900 antialiased">
        <div className="min-h-screen w-full">{children}</div>
      </body>
    </html>
  );
}

