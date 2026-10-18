import { useCallback, useEffect, useState } from "react";
import { createHashRouter, NavLink, Outlet, RouterProvider } from "react-router-dom";
import { api } from "./api";
import type { Me } from "./api/types";
import { DataProvider, useData } from "./data";
import { relativeTime } from "./format";
import { AccessPage } from "./pages/AccessPage";
import { ComparePage } from "./pages/ComparePage";
import { DetailPage } from "./pages/DetailPage";
import { EventsPage } from "./pages/EventsPage";
import { ListPage } from "./pages/ListPage";
import { LoginPage } from "./pages/LoginPage";
import { MapPage } from "./pages/MapPage";
import { PreferencesPage } from "./pages/PreferencesPage";

function Shell() {
  const { lastRunAt, isOwner, loading, refresh } = useData();
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">🏠 Mieszkania</div>
        <button className="ghost small" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Ładuję…" : `Odświeżone ${relativeTime(lastRunAt)}`}
        </button>
      </header>
      {api.demo && (
        <div className="demo-banner">Tryb demo – przykładowe dane, nic nie jest zapisywane.</div>
      )}
      <main className="content">
        <Outlet />
      </main>
      <nav className="tabbar">
        <NavLink to="/" end>📋<span>Oferty</span></NavLink>
        <NavLink to="/mapa">🗺️<span>Mapa</span></NavLink>
        <NavLink to="/wydarzenia">📅<span>Wydarzenia</span></NavLink>
        <NavLink to="/preferencje">⚙️<span>Preferencje</span></NavLink>
        {isOwner && <NavLink to="/dostep">👥<span>Dostęp</span></NavLink>}
      </nav>
    </div>
  );
}

const router = createHashRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <ListPage /> },
      { path: "oferta/:id", element: <DetailPage /> },
      { path: "mapa", element: <MapPage /> },
      { path: "porownaj", element: <ComparePage /> },
      { path: "wydarzenia", element: <EventsPage /> },
      { path: "preferencje", element: <PreferencesPage /> },
      { path: "dostep", element: <AccessPage /> },
    ],
  },
]);

export function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const load = useCallback(() => {
    api.currentUser().then(setMe).catch(() => setMe(null));
  }, []);
  useEffect(load, [load]);

  if (me === undefined) return <div className="center muted">Ładuję…</div>;
  if (me === null) return <LoginPage onSignedIn={load} />;
  if (!me.member) {
    return (
      <div className="center card narrow">
        <h1>Brak dostępu</h1>
        <p>
          Zalogowałeś się jako <b>{me.email}</b>, ale ten adres nie jest na liście osób z
          dostępem. Poproś właściciela aplikacji o dodanie go.
        </p>
        <button onClick={() => void api.signOut().then(load)}>Wyloguj</button>
      </div>
    );
  }
  return (
    <DataProvider me={me}>
      <RouterProvider router={router} />
    </DataProvider>
  );
}
