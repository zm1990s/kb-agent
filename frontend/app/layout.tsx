import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import IntlProvider from "@/components/IntlProvider";
import DialogProvider from "@/components/DialogProvider";

export const metadata: Metadata = {
  title: "KB-Agent",
  description: "共享 Agent 知识平台",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body>
        <IntlProvider>
          <DialogProvider>{children}</DialogProvider>
        </IntlProvider>
      </body>
    </html>
  );
}
