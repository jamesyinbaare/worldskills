"use client";

import { FormEvent, ReactNode, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  ApiErrorAlert,
  FieldMessage,
  fieldErrorMap,
} from "@/components/forms/ApiErrorAlert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type ConfigOption = {
  id: string;
  label: string;
};

type ConfigEntityFieldProps = {
  id: string;
  label: string;
  description?: string;
  value: string;
  options: ConfigOption[];
  loading?: boolean;
  disabled?: boolean;
  error?: string;
  emptyTitle: string;
  emptyDescription: string;
  createLabel: string;
  onValueChange: (value: string) => void;
  onCreate: () => void;
};

export function ConfigEntityField({
  id,
  label,
  description,
  value,
  options,
  loading = false,
  disabled = false,
  error,
  emptyTitle,
  emptyDescription,
  createLabel,
  onValueChange,
  onCreate,
}: ConfigEntityFieldProps) {
  const errorId = `${id}-error`;
  const hasOptions = options.length > 0;

  if (loading) {
    return (
      <div className="space-y-2">
        <Label>{label}</Label>
        <Skeleton className="h-11 w-full" />
      </div>
    );
  }

  if (!hasOptions) {
    return (
      <div className="space-y-3 rounded-xl bg-muted/40 p-4 ring-1 ring-foreground/10">
        <div className="space-y-1">
          <p className="text-sm font-medium">{emptyTitle}</p>
          <p className="text-sm text-muted-foreground">{emptyDescription}</p>
        </div>
        <Button
          type="button"
          className="min-h-11"
          onClick={onCreate}
          disabled={disabled}
        >
          {createLabel}
        </Button>
        <FieldMessage id={errorId} message={error} />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <Label htmlFor={id}>{label}</Label>
          {description ? (
            <p className="text-xs text-muted-foreground">{description}</p>
          ) : null}
          <select
            id={id}
            className={cn(
              "flex h-11 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none",
              "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
              "disabled:cursor-not-allowed disabled:opacity-50",
              "aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20",
            )}
            value={value}
            disabled={disabled}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : undefined}
            onChange={(e) => onValueChange(e.target.value)}
          >
            <option value="">Select…</option>
            {options.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          variant="outline"
          className="min-h-11 shrink-0"
          onClick={onCreate}
          disabled={disabled}
        >
          Create new
        </Button>
      </div>
      <FieldMessage id={errorId} message={error} />
    </div>
  );
}

type NameCreateDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  nameLabel?: string;
  submitLabel: string;
  onSubmit: (name: string) => Promise<void>;
};

export function NameCreateDialog({
  open,
  onOpenChange,
  title,
  description,
  nameLabel = "Name",
  submitLabel,
  onSubmit,
}: NameCreateDialogProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  function reset() {
    setName("");
    setError(null);
    setFieldErrors({});
    setPending(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      await onSubmit(name.trim());
      reset();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not create",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="config-entity-name">{nameLabel}</Label>
            <Input
              id="config-entity-name"
              required
              maxLength={120}
              value={name}
              aria-invalid={Boolean(fieldErrors.name)}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <ApiErrorAlert error={error} />
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !name.trim()}>
              {pending ? "Saving…" : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type AgeRuleCreateDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: {
    name: string;
    maxAge: number;
    referenceDate: string | null;
    openCategoryEnabled: boolean;
  }) => Promise<void>;
};

export function AgeRuleCreateDialog({
  open,
  onOpenChange,
  onSubmit,
}: AgeRuleCreateDialogProps) {
  const [name, setName] = useState("");
  const [maxAge, setMaxAge] = useState("25");
  const [referenceDate, setReferenceDate] = useState("");
  const [openCategory, setOpenCategory] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);

  function reset() {
    setName("");
    setMaxAge("25");
    setReferenceDate("");
    setOpenCategory(false);
    setError(null);
    setFieldErrors({});
    setPending(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setFieldErrors({});
    setPending(true);
    try {
      const age = Number(maxAge);
      await onSubmit({
        name: name.trim(),
        maxAge: age,
        referenceDate: referenceDate.trim() || null,
        openCategoryEnabled: openCategory,
      });
      reset();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err);
        setFieldErrors(fieldErrorMap(err.fields));
      } else {
        setError(
          new ApiError(0, {
            error: {
              code: "HTTP_ERROR",
              message: "Could not create age rule",
              fields: [],
              traceId: "",
            },
          }),
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <DialogHeader>
            <DialogTitle>Create age rule</DialogTitle>
            <DialogDescription>
              Set the maximum age and optional reference date used for
              eligibility screening.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="age-rule-name">Name</Label>
            <Input
              id="age-rule-name"
              required
              maxLength={120}
              value={name}
              aria-invalid={Boolean(fieldErrors.name)}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. U25"
              autoFocus
            />
            <FieldMessage message={fieldErrors.name} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="age-rule-max">Maximum age</Label>
            <Input
              id="age-rule-max"
              type="number"
              min={1}
              max={120}
              required
              value={maxAge}
              aria-invalid={Boolean(fieldErrors.maxAge)}
              onChange={(e) => setMaxAge(e.target.value)}
            />
            <FieldMessage message={fieldErrors.maxAge} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="age-rule-ref">Reference date (optional)</Label>
            <Input
              id="age-rule-ref"
              type="date"
              value={referenceDate}
              aria-invalid={Boolean(fieldErrors.referenceDate)}
              onChange={(e) => setReferenceDate(e.target.value)}
            />
            <FieldMessage message={fieldErrors.referenceDate} />
          </div>
          <div className="flex items-center gap-3">
            <Checkbox
              id="age-rule-open"
              checked={openCategory}
              onCheckedChange={(checked) => setOpenCategory(checked === true)}
            />
            <Label htmlFor="age-rule-open" className="font-normal">
              Allow open category when over age
            </Label>
          </div>
          <ApiErrorAlert error={error} />
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={pending || !name.trim() || !maxAge.trim()}
            >
              {pending ? "Saving…" : "Create age rule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Small helper for list pages that only need a create button + children */
export function ConfigListEmpty({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action: ReactNode;
}) {
  return (
    <div className="space-y-4 px-6 py-8">
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}
