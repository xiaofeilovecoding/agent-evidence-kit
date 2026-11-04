/** Original 24px evidence mark: two offset file corners converging into
 * three dots (input collapsing into an evidence card). Pure SVG/CSS, no
 * third-party logos. Color follows the active module accent. */
export default function EvidenceMark({
  accent,
  size = 24,
  busy = false,
  success = false,
}: {
  accent: string;
  size?: number;
  busy?: boolean;
  success?: boolean;
}) {
  return (
    <span
      className={busy ? "evidence-mark busy" : success ? "evidence-mark success" : "evidence-mark"}
      aria-hidden="true"
      style={{ width: size, height: size, ["--mark-accent" as string]: accent }}
    >
      <svg viewBox="0 0 24 24" width={size} height={size} focusable="false">
        <path
          className="mark-corner mark-corner-a"
          d="M6 4h8l4 4v12a0 0 0 0 0 0 0"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.9"
        />
        <path
          className="mark-corner mark-corner-b"
          d="M10 8h8l4 4v10"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.55"
        />
        <g className="mark-dots" fill={accent}>
          <circle cx="9" cy="16" r="1.6" />
          <circle cx="13.5" cy="16" r="1.6" />
          <circle cx="18" cy="16" r="1.6" />
        </g>
      </svg>
    </span>
  );
}
