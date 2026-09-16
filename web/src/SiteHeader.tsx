export function SiteHeader({ manage = false }: { manage?: boolean }) {
  return <header className="site-header">
      <a className="brand-link" href="/" aria-label="Camera Search Lab home">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true"><path d="M8 6l2-3h4l2 3h4a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z" /><circle cx="12" cy="13" r="4" /></svg>
        Camera Search Lab
      </a>
      <nav className="header-navigation" aria-label="Main navigation"><a href={manage ? "/?view=compare" : "/?view=manage"}>{manage ? "Search shop" : "Manage shop"}</a><span className="header-credit">Built with <span>Redis</span></span></nav>
    </header>;
}
