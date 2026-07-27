"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  type RegionOut,
  type ZoneOut,
  createCycleZone,
  getRegionZoneMap,
  listCycleZones,
  listRegions,
  putRegionZoneMap,
} from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageShell } from "@/components/layout/PageShell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function CycleZonesPage() {
  const params = useParams<{ id: string }>();
  const competitionId = params.id;

  const [zones, setZones] = useState<ZoneOut[]>([]);
  const [regions, setRegions] = useState<RegionOut[]>([]);
  const [mapByRegion, setMapByRegion] = useState<Record<string, string>>({});
  const [zoneName, setZoneName] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [z, r, m] = await Promise.all([
      listCycleZones(competitionId),
      listRegions(),
      getRegionZoneMap(competitionId),
    ]);
    setZones(z);
    setRegions(r.filter((x) => x.active));
    const next: Record<string, string> = {};
    for (const row of m.mappings) {
      next[row.regionId] = row.zoneId;
    }
    setMapByRegion(next);
  }, [competitionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await reload();
      } catch (err) {
        if (!cancelled && err instanceof ApiError) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  async function onCreateZone(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    setPending(true);
    try {
      await createCycleZone(competitionId, { name: zoneName.trim() });
      setZoneName("");
      await reload();
      setSavedMessage("Zone created");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  async function onSaveMap() {
    setError(null);
    setFieldErrors({});
    setSavedMessage(null);
    setPending(true);
    try {
      const mappings = Object.entries(mapByRegion)
        .filter(([, zoneId]) => zoneId)
        .map(([regionId, zoneId]) => ({ regionId, zoneId }));
      await putRegionZoneMap(competitionId, mappings);
      await reload();
      setSavedMessage("Region→zone map saved");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <PageShell className="space-y-6">
      <PageHeader
        title="Zones & Regions"
        description="Create competition zones and map catalog regions so registration can derive competitor zones."
        backHref={`/admin/competitions/${competitionId}`}
        backLabel="Competition"
      />

      <ApiErrorAlert error={error} />

      {savedMessage ? (
        <Alert>
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{savedMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card data-testid="zones-list">
        <CardHeader>
          <CardTitle>Zones</CardTitle>
          <CardDescription>
            Named geographic buckets for this competition (e.g. Zone A, Zone B).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : zones.length === 0 ? (
            <p className="text-sm text-muted-foreground">No zones yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>ID</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {zones.map((z) => (
                  <TableRow key={z.zoneId}>
                    <TableCell className="font-medium">{z.name}</TableCell>
                    <TableCell>{z.active ? "Active" : "Inactive"}</TableCell>
                    <TableCell className="font-mono text-xs">{z.zoneId}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          <form
            onSubmit={onCreateZone}
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            noValidate
          >
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="zoneName">New zone name</Label>
              <Input
                id="zoneName"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                placeholder="Zone A"
                className="min-h-11"
                required
              />
              <FieldMessage message={fieldErrors.name} />
            </div>
            <Button type="submit" disabled={pending || !zoneName.trim()}>
              {pending ? "Saving…" : "Create zone"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card data-testid="region-zone-map">
        <CardHeader>
          <CardTitle>Region → zone map</CardTitle>
          <CardDescription>
            Each catalog region maps to exactly one zone for this competition.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {regions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No regions in catalog.</p>
          ) : (
            <div className="space-y-3">
              {regions.map((region) => (
                <div
                  key={region.regionId}
                  className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] sm:items-center"
                >
                  <Label className="text-sm font-medium">{region.name}</Label>
                  <Select
                    value={mapByRegion[region.regionId] || undefined}
                    onValueChange={(v) =>
                      setMapByRegion((prev) => ({
                        ...prev,
                        [region.regionId]: v ?? "",
                      }))
                    }
                  >
                    <SelectTrigger className="min-h-11 w-full">
                      <SelectValue placeholder="Select zone" />
                    </SelectTrigger>
                    <SelectContent>
                      {zones
                        .filter((z) => z.active)
                        .map((z) => (
                          <SelectItem key={z.zoneId} value={z.zoneId}>
                            {z.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          )}
          <Button
            type="button"
            disabled={pending || zones.length === 0}
            onClick={() => void onSaveMap()}
          >
            {pending ? "Saving…" : "Save map"}
          </Button>
        </CardContent>
      </Card>
    </PageShell>
  );
}
