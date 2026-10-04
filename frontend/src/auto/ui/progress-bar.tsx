import { cn } from "@/utils/cn";

// -- Components ---------------------------------------------------------------

/** A thin bar: filled to `fraction`, or a sliding stripe while a step cannot tell how far it is. */
const ProgressBar: React.FC<{ fraction: number | null; label: string; className?: string }> = ({
  fraction,
  label,
  className,
}) => {
  const percent = fraction === null ? null : Math.round(fraction * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? undefined}
      className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-composer-border", className)}
    >
      {percent === null ? (
        <div className="progress-indeterminate absolute inset-y-0 w-1/3 rounded-full bg-composer-accent" />
      ) : (
        <div
          className="h-full rounded-full bg-composer-accent transition-[width] duration-300 ease-out"
          style={{ width: `${percent}%` }}
        />
      )}
    </div>
  );
};

// -- Exports ------------------------------------------------------------------

export { ProgressBar };
