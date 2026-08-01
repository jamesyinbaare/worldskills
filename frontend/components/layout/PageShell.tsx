import { cn } from "@/lib/utils"

type PageShellProps = {
  children: React.ReactNode
  className?: string
  /** Wider content for dense admin lists; default is standard app width. */
  width?: "default" | "narrow" | "wide" | "full"
}

const widthClass = {
  narrow: "max-w-xl",
  default: "max-w-3xl",
  wide: "max-w-6xl",
  full: "max-w-none",
} as const

export function PageShell({
  children,
  className,
  width = "default",
}: PageShellProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 py-8 sm:px-6 sm:py-10",
        widthClass[width],
        className
      )}
    >
      {children}
    </div>
  )
}
