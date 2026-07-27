"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

export default function ConsentGrantRetiredPage() {
  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-8 sm:px-6 sm:py-10">
      <Button variant="link" className="h-auto min-h-11 px-0" asChild>
        <Link href="/">← Home</Link>
      </Button>

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            Guardian link retired
          </h1>
          <CardDescription>
            Online guardian consent links are no longer used. Competitors must
            download the printed consent form, have a guardian sign it, and
            upload the signed PDF from the competitor portal.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 px-4 sm:px-6">
          <p className="text-sm text-muted-foreground">
            If you are the competitor, sign in and open Guardian consent from
            your dashboard.
          </p>
          <Button className="min-h-11 w-full" asChild>
            <Link href="/competitor" data-testid="consent-retired-portal-link">
              Go to competitor portal
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
