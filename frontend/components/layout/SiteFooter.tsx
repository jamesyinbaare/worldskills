import Link from "next/link";
import { CrestLogo } from "@/components/brand/LogoMark";
import { Button } from "@/components/ui/button";

export function SiteFooter() {
  return (
    <footer className="mt-auto bg-primary text-primary-foreground">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.2fr_1fr]">
        <div className="flex gap-4">
          <CrestLogo className="h-14 w-auto shrink-0 object-contain brightness-0 invert" />
          <div>
            <p className="text-sm font-semibold tracking-wide">
              Commission for Technical and Vocational Education and Training
            </p>
            <p className="mt-2 max-w-md text-sm text-primary-foreground/85">
              Regulating, promoting and administering TVET for transformation
              and innovation — host of WorldSkills Ghana.
            </p>
          </div>
        </div>

        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-highlight">
              Connect
            </h2>
            <ul className="mt-3 space-y-1.5 text-sm text-primary-foreground/90">
              <li>CTVET, Trinity Avenue</li>
              <li>GA-416-9945</li>
              <li>
                <a
                  href="tel:+233303968039"
                  className="underline-offset-2 hover:underline"
                >
                  +233-303-968039
                </a>
              </li>
              <li>
                <a
                  href="mailto:info@ctvet.gov.gh"
                  className="underline-offset-2 hover:underline"
                >
                  info@ctvet.gov.gh
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h2 className="text-xs font-bold uppercase tracking-wider text-highlight">
              Quick links
            </h2>
            <ul className="mt-3 space-y-1.5 text-sm">
              <li>
                <Button
                  variant="link"
                  className="h-auto px-0 text-sm text-primary-foreground"
                  asChild
                >
                  <a
                    href="https://ctvet.gov.gh/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    About CTVET
                  </a>
                </Button>
              </li>
              <li>
                <Button
                  variant="link"
                  className="h-auto px-0 text-sm text-primary-foreground"
                  asChild
                >
                  <Link href="/">WorldSkills Ghana</Link>
                </Button>
              </li>
              <li>
                <Button
                  variant="link"
                  className="h-auto px-0 text-sm text-primary-foreground"
                  asChild
                >
                  <Link href="/login">Competition portal</Link>
                </Button>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div className="border-t border-primary-foreground/15 px-4 py-4 text-center text-xs text-primary-foreground/75 sm:px-6">
        © {new Date().getFullYear()} CTVET / WorldSkills Ghana. All rights
        reserved.
      </div>
    </footer>
  );
}
