import { Routes, Route, NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Search,
  Network,
  UserCircle,
  Clock,
  Radar,
  ChevronLeft,
  ChevronRight,
  Bug,
} from "lucide-react";
import { useState } from "react";

import Dashboard from "./pages/Dashboard";
import SearchPage from "./pages/Search";
import Profile from "./pages/Profile";
import Graph from "./pages/Graph";
import Timeline from "./pages/Timeline";
import Investigate from "./pages/Investigate";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/search", icon: Search, label: "Search" },
  { to: "/investigate", icon: Radar, label: "Investigate" },
];

function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-zinc-900 border-r border-zinc-800 z-50 flex flex-col transition-all duration-300 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-14 border-b border-zinc-800 shrink-0">
        <Bug className="w-6 h-6 text-sky-400 shrink-0" />
        {!collapsed && (
          <span className="text-lg font-bold text-zinc-100 tracking-tight">
            Spindeln
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 space-y-1 px-2 overflow-y-auto">
        {navItems.map((item) => {
          const isActive =
            item.to === "/"
              ? location.pathname === "/"
              : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group ${
                isActive
                  ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-transparent"
              }`}
            >
              <item.icon
                className={`w-5 h-5 shrink-0 ${
                  isActive
                    ? "text-sky-400"
                    : "text-zinc-500 group-hover:text-zinc-300"
                }`}
              />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center h-10 border-t border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <ChevronLeft className="w-4 h-4" />
        )}
      </button>
    </aside>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-56 min-h-screen">
        <div className="p-6 max-w-screen-2xl mx-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/investigate" element={<Investigate />} />
            <Route path="/profile/:id" element={<Profile />} />
            <Route path="/graph/:id" element={<Graph />} />
            <Route path="/timeline/:id" element={<Timeline />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
