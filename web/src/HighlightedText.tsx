import { highlightPreviewSegments, highlightSegments } from "./learning";

export function HighlightedText({ text, ranges = [], preview = false }: {
  text: string;
  ranges?: { start: number; end: number }[];
  preview?: boolean;
}) {
  const segments = preview ? highlightPreviewSegments(text, ranges) : highlightSegments(text, ranges);
  return <>{segments.map((segment, index) => segment.matched
    ? <mark key={index}>{segment.text}</mark>
    : <span key={index}>{segment.text}</span>)}</>;
}
