"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  loadRegistrationConfirmation,
  type RegistrationConfirmation,
} from "@/lib/registrationConfirmation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";

export default function InstitutionRegistrationConfirmationPage() {
  const params = useParams<{ competitionId: string }>();
  const competitionId = params.competitionId;
  const [data, setData] = useState<RegistrationConfirmation | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setData(loadRegistrationConfirmation(competitionId));
    setReady(true);
  }, [competitionId]);

  const duplicate =
    data?.flags?.includes("DUPLICATE_SUSPECTED") ||
    data?.message?.includes("DUPLICATE_SUSPECTED");

  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-8 sm:px-6 sm:py-10">
      <Button variant="link" className="h-auto min-h-11 px-0" asChild>
        <Link href={`/institution/competitions/${competitionId}/register`}>
          ← Register another
        </Link>
      </Button>

      <Card>
        <CardHeader className="px-4 sm:px-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            Registration submitted
          </h1>
          <CardDescription>
            Keep the competitor reference for your records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 px-4 sm:px-6">
          {!ready ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : !data ? (
            <Alert>
              <AlertTitle>No confirmation found</AlertTitle>
              <AlertDescription>
                Submit a registration to see the confirmation details here.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Reference</p>
                <p className="font-mono text-lg font-semibold">
                  {data.competitorRef}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{data.status}</Badge>
                {duplicate ? (
                  <Badge variant="destructive">DUPLICATE_SUSPECTED</Badge>
                ) : null}
              </div>
              {data.message ? (
                <p className="text-sm text-muted-foreground">{data.message}</p>
              ) : null}
            </>
          )}
          <Button className="min-h-11 w-full" asChild>
            <Link href="/institution">Back to institution portal</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
