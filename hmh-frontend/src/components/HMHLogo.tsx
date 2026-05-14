/**
 * HMH Group logo component.
 *
 * Tries to load /branding/hmh-logo.png (or hmh-logo-light.png for dark/sidebar
 * context). Falls back to a clean SVG text logo if the image fails to load.
 *
 * Usage:
 *   <HMHLogo />                     — standard (dark text, orange M)
 *   <HMHLogo variant="light" />     — light text (for dark sidebar/header)
 *   <HMHLogo size="sm" />           — small (28px height)
 *   <HMHLogo size="md" />           — medium (40px, default)
 *   <HMHLogo size="lg" />           — large (60px, login pages)
 *   <HMHLogo imageOnly />           — image only, no fallback text (hidden on error)
 */

import { useState } from "react";
import { cn } from "@/lib/utils";

interface HMHLogoProps {
  variant?: "dark" | "light";
  size?: "sm" | "md" | "lg";
  imageOnly?: boolean;
  className?: string;
}

const heights: Record<string, string> = {
  sm: "h-7",
  md: "h-10",
  lg: "h-14",
};

export function HMHLogo({
  variant = "dark",
  size = "md",
  imageOnly = false,
  className,
}: HMHLogoProps) {
  const [imgFailed, setImgFailed] = useState(false);

  const imgSrc = variant === "light"
    ? "/branding/hmh-logo-light.png"
    : "/branding/hmh-logo.png";

  const isLight = variant === "light";

  // If imageOnly and image failed, render nothing
  if (imageOnly && imgFailed) return null;

  if (!imgFailed) {
    return (
      <img
        src={imgSrc}
        alt="HMH Group"
        onError={() => setImgFailed(true)}
        className={cn(heights[size], "w-auto object-contain", className)}
      />
    );
  }

  // ── SVG text fallback ──────────────────────────────────────────────────────
  const textColor  = isLight ? "#FFFFFF" : "#111827";
  const subColor   = isLight ? "#9CA3AF" : "#6B7280";
  const orange     = "#F97316";

  const svgHeights: Record<string, number> = { sm: 28, md: 40, lg: 60 };
  const h = svgHeights[size];
  const scale = h / 40;

  return (
    <svg
      width={Math.round(160 * scale)}
      height={h}
      viewBox="0 0 160 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("shrink-0", className)}
      aria-label="HMH Group"
    >
      {/* H */}
      <text
        x="0" y="28"
        fontSize="28"
        fontWeight="900"
        fontFamily="Arial, sans-serif"
        fill={textColor}
        letterSpacing="-1"
      >H</text>
      {/* M — orange */}
      <text
        x="20" y="28"
        fontSize="28"
        fontWeight="900"
        fontFamily="Arial, sans-serif"
        fill={orange}
        letterSpacing="-1"
      >M</text>
      {/* H */}
      <text
        x="46" y="28"
        fontSize="28"
        fontWeight="900"
        fontFamily="Arial, sans-serif"
        fill={textColor}
        letterSpacing="-1"
      >H</text>
      {/* GROUP sub-label */}
      <text
        x="72" y="22"
        fontSize="11"
        fontWeight="700"
        fontFamily="Arial, sans-serif"
        fill={textColor}
        letterSpacing="1"
      >GROUP</text>
      {/* Construction OS */}
      <text
        x="72" y="34"
        fontSize="7.5"
        fontWeight="500"
        fontFamily="Arial, sans-serif"
        fill={subColor}
        letterSpacing="0.5"
      >Construction OS</text>
    </svg>
  );
}
