import { Badge, badgeVariants } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { VariantProps } from "class-variance-authority"

type StatusVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>

const STATUS_MAP: Record<string, StatusVariant> = {
  draft: "outline",
  configured: "default",
  validated: "secondary",
  active: "success",
  locked: "warning",
  closed: "outline",
  archived: "outline",
  pending: "warning",
  pending_review: "warning",
  submitted: "default",
  approved: "success",
  verified: "success",
  registered: "success",
  rejected: "destructive",
  nominated: "highlight",
  eligible: "success",
  ineligible: "outline",
  open_category: "highlight",
  open: "highlight",
  competitive: "secondary",
  consent_pending: "warning",
  withdrawn: "outline",
  accepted: "success",
  late: "warning",
  accepted_pending_scan: "warning",
  blind: "highlight",
}

type StatusBadgeProps = {
  status: string
  className?: string
  label?: string
}

export function StatusBadge({ status, className, label }: StatusBadgeProps) {
  const key = status.trim().toLowerCase().replace(/\s+/g, "_")
  const variant = STATUS_MAP[key] ?? "outline"
  return (
    <Badge
      variant={variant}
      className={cn("capitalize", className)}
      data-status={key}
    >
      {label ?? status}
    </Badge>
  )
}
