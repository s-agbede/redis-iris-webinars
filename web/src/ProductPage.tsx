import { useEffect, useState } from "react";
import { errorMessage, requestJSON, type ProductDetail } from "./api";
import { SiteHeader } from "./SiteHeader";
import { ProductPhotoView } from "./ProductPhoto";
import "./shop.css";
export function ProductPage({ id }: { id: string }) {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    requestJSON<ProductDetail>(`/products/${encodeURIComponent(id)}`, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setProduct(value); }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(errorMessage(cause)); });
    return () => controller.abort();
  }, [id]);
  return <div className="app-shell"><SiteHeader /><main className="shop-product-page"><a href="/">← Back to your adviser</a>{error && <p role="alert" className="shop-error">{error}</p>}{!product && !error && <p>Loading gear details…</p>}{product && <><span className="eyebrow">{product.product_brand || "From our catalogue"}</span><h1>{product.product_title}</h1><div className="product-detail-grid"><ProductPhotoView photo={product.photo} expanded /><div><h2>From the original listing</h2><p>{product.product_description || "No description supplied."}</p>{product.product_bullet_point && <p>{product.product_bullet_point}</p>}<p className="shop-small">Catalogue ID: {product.product_id}. This demo catalogue does not contain prices or stock availability. Confirm compatibility with the manufacturer.</p></div></div></>}</main></div>;
}
