import { useState } from "react";
import type { ProductPhoto } from "./api";

function PhotoPlaceholder({ unavailable }: { unavailable: boolean }) {
  return (
    <div className="photo-placeholder">
      <svg
        width="32"
        height="32"
        viewBox="0 0 32 32"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        aria-hidden="true"
      >
        <path d="M11 8l2-3h6l2 3h5a2 2 0 0 1 2 2v15a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2z" />
        <circle cx="16" cy="17" r="6" />
        <path d="M23 12h2" />
      </svg>
      <span>{unavailable ? "Photo unavailable" : "No verified photo yet"}</span>
    </div>
  );
}

export function ProductPhotoView({
  photo,
  expanded = false,
  compact = false,
}: {
  photo: ProductPhoto | null;
  expanded?: boolean;
  compact?: boolean;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const unavailable = Boolean(photo && failedUrl === photo.url);

  return (
    <figure className={`product-photo ${expanded ? "photo-expanded" : ""} ${compact ? "photo-compact" : ""} ${!photo ? "photo-missing" : ""}`}>
      <div className="photo-stage">
        {photo && !unavailable ? (
          <img
            src={photo.url}
            alt={photo.alt}
            loading={expanded ? "eager" : "lazy"}
            decoding="async"
            onError={() => setFailedUrl(photo.url)}
          />
        ) : (
          <PhotoPlaceholder unavailable={unavailable} />
        )}
      </div>
      <figcaption>
        {photo ? (
          <>
            <p className="photo-caption">{photo.caption}</p>
            <p className="photo-credit">
              <a href={photo.source_url} target="_blank" rel="noreferrer">
                Photo by {photo.author}
              </a>
              <span aria-hidden="true"> · </span>
              <a href={photo.license_url} target="_blank" rel="noreferrer">
                {photo.license}
              </a>
            </p>
          </>
        ) : (
          <p className="photo-caption">Product text is available to inspect.</p>
        )}
      </figcaption>
    </figure>
  );
}
