import Link from "next/link"
import { ChevronLeftIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

type PageHeaderProps = {
  title: string
  description?: string
  /** Optional back link shown above the title. */
  backHref?: string
  backLabel?: string
  /** Primary / secondary actions rendered to the right of the title block. */
  actions?: React.ReactNode
  className?: string
  as?: "h1" | "h2"
}

export function PageHeader({
  title,
  description,
  backHref,
  backLabel = "Back",
  actions,
  className,
  as: Heading = "h1",
}: PageHeaderProps) {
  return (
    <header className={cn("mb-8 space-y-4", className)}>
      {backHref ? (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 min-h-9 gap-1 text-muted-foreground"
          asChild
        >
          <Link href={backHref}>
            <ChevronLeftIcon className="size-4" />
            {backLabel}
          </Link>
        </Button>
      ) : null}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1.5">
          <Heading className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            {title}
          </Heading>
          {description ? (
            <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  )
}
