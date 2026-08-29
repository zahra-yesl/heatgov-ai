/**
 * Inline SVG icons.
 *
 * Hand-drawn rather than pulled from an icon package: the set is tiny, and one
 * more npm dependency is one more chance for an install to fail on the machine
 * that has to run the demo.
 */

import type { LayerId } from "@/lib/api";

type IconProps = { className?: string };

const BASE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
  "aria-hidden": true,
};

export function SunIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function MoonIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
    </svg>
  );
}

export function ThermometerIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M14 14.8V4a2 2 0 1 0-4 0v10.8a4 4 0 1 0 4 0Z" />
    </svg>
  );
}

export function ClockIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function ClipboardIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M9 4h6v3H9zM9 5.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.5a2 2 0 0 0-2-2h-2" />
      <path d="M9 12h6M9 16h4" />
    </svg>
  );
}

export function SparkIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="m12 3 2.1 5.4L19.5 10l-5.4 2.1L12 17.5l-2.1-5.4L4.5 10l5.4-1.6L12 3Z" />
    </svg>
  );
}

export function ChevronIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

const LAYER_ICONS: Record<LayerId, (props: IconProps) => React.JSX.Element> = {
  tcm_peak_22h: MoonIcon,
  tcm_peak_15h: SunIcon,
  exceedance: ThermometerIcon,
  persistence: ClockIcon,
};

export function LayerIcon({ id, className }: { id: LayerId; className?: string }) {
  const Icon = LAYER_ICONS[id];
  return Icon ? <Icon className={className} /> : null;
}
