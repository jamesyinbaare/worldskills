import type { Metadata } from "next";
import { Montserrat } from "next/font/google";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { ConditionalSiteHeader } from "@/components/layout/ConditionalSiteChrome";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const montserrat = Montserrat({
  variable: "--font-montserrat",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "WorldSkills Ghana | SCMS",
    template: "%s | WorldSkills Ghana",
  },
  description:
    "Skills Competition Management System for WorldSkills Ghana — powered by CTVET.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${montserrat.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <AuthProvider>
          <TooltipProvider>
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
            >
              Skip to content
            </a>
            <ConditionalSiteHeader />
            <main id="main-content" className="flex-1" tabIndex={-1}>
              {children}
            </main>
          </TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
