import { SiteHeader } from "./SiteHeader";
import { ProductionLab } from "./ProductionLab";
import { TrafficLab } from "./TrafficLab";
import { DeploymentLab } from "./DeploymentLab";

export function ManageShop() {
  function searchProduct(query: string) {
    const params = new URLSearchParams({ view: "compare", q: query });
    window.open(`/?${params}`, "_blank", "noopener,noreferrer");
  }

  return <div className="app-shell">
    <SiteHeader manage />
    <main className="manage-page">
      <header className="search-intro">
        <h1>Manage shop.</h1>
        <p>Update the catalogue. Keep search ready for your customers.</p>
      </header>
      <p className="manage-help">Search buttons open the customer view in a new tab. Keep both tabs open to see how catalogue changes reach search.</p>
      <ProductionLab initiallyOpen onSearch={searchProduct} />
      <TrafficLab />
      <DeploymentLab />
    </main>
  </div>;
}
