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

export default function RegistrationConfirmationPage() {
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
        <Link href={`/competitor/competitions/${competitionId}/register`}>
          ← Back to form
        </Link>
      </Button>

      <Card data-testid="registration-confirmation">
        <CardHeader className="px-4 sm:px-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            Registration received
          </h1>
          <CardDescription>
            Keep your competitor reference safe for follow-up and consent steps.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 px-4 sm:px-6">
          {!ready ? (
            <p className="text-sm text-muted-foreground" role="status">
              Loading…
            </p>
          ) : !data ? (
            <Alert variant="destructive" role="alert">
              <AlertTitle>No confirmation found</AlertTitle>
              <AlertDescription>
                Submit the registration form again to obtain a reference.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">
                  Competitor reference
                </p>
                <p
                  className="text-xl font-semibold tracking-tight"
                  data-testid="competitor-ref"
                >
                  {data.competitorRef}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary" data-testid="registration-status">
                  {data.status}
                </Badge>
                {data.flags?.map((flag) => (
                  <Badge key={flag} variant="outline">
                    {flag}
                  </Badge>
                ))}
              </div>
              {duplicate ? (
                <Alert data-testid="duplicate-pending-alert" role="status">
                  <AlertTitle>Check pending</AlertTitle>
                  <AlertDescription>
                    Your registration was recorded with a{" "}
                    <strong>DUPLICATE_SUSPECTED</strong> flag. An administrator
                    will review it; no further action is needed right now.
                  </AlertDescription>
                </Alert>
              ) : null}
              {data.message && !duplicate ? (
                <p className="text-sm text-muted-foreground">{data.message}</p>
              ) : null}
              <Button className="min-h-11 w-full" variant="outline" asChild>
                <Link
                  href={`/competitor/competitors/${data.competitorId}/consent`}
                >
                  Manage guardian consent
                </Link>
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
